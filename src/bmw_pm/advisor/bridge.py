"""Local JSON/NDJSON adapter for the web frontend. The advisor remains the engine."""
from __future__ import annotations

import json
import math
import os
import sqlite3
import sys
from decimal import Decimal
from pathlib import Path
from typing import Callable, Literal

from pydantic import Field, ValidationError

from ..contracts import Contract
from ..data_pipeline.video_memory import TranscriptInput, save_transcript, video_id
from ..intelligence.fusion import import_youtube_run
from ..intelligence.provider import ProviderError
from ..storage import Database
from ..storage.config import StorageError, database_target
from ..utils import sha256_bytes
from .contracts import AdvisorRequest
from .evidence import ROOT
from .finance import ScenarioInput, scenario_results
from .provider import AdvisorProvider
from .service import run_advisor
from .settings import environment_credentials, project_credentials


class ScenarioRequest(Contract):
    rows: list[ScenarioInput] = Field(min_length=3, max_length=3)
    years: int = Field(ge=1, le=10)
    discount_rate: Decimal = Field(ge=0, lt=1, allow_inf_nan=False)
    source: str = Field(min_length=1, max_length=500)


class ScopeCoverage(Contract):
    model_code: str
    market: str
    powertrain: str
    feedback_records: int


class SourceCatalog(Contract):
    database_available: bool
    database_backend: Literal['sqlite', 'postgres'] = 'sqlite'
    connection_configured: bool
    scopes: list[ScopeCoverage]
    youtube_findings: int
    youtube_videos: int
    saved_youtube_runs: int
    video_memories: int = 0


class SyncResult(Contract):
    runs: int = 0
    inserted: int = 0
    accepted: int = 0
    rejected: int = 0
    failed_runs: int = 0
    memories_inserted: int = 0


def saved_youtube_runs(root: Path = ROOT) -> list[Path]:
    return sorted({path.parent for directory in (
        root / "src/bmw_pm/data_pipeline/youtube_research/output",
        root / "youtube_research_agent/output",
    ) for path in directory.glob("*/evidence.json")})


def source_catalog(database: str | Path, root: Path = ROOT) -> SourceCatalog:
    credentials = project_credentials(root) or environment_credentials()
    storage = Database(database)
    result = dict(database_available=storage.exists(), database_backend='postgres' if storage.is_postgres else 'sqlite', connection_configured=bool(credentials),
                  scopes=[], youtube_findings=0, youtube_videos=0, saved_youtube_runs=len(saved_youtube_runs(root)), video_memories=0)
    if storage.exists():
        with storage.connect(readonly=True) as connection:
            tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            result["database_available"] = "feedback_records" in tables
            if "feedback_records" in tables:
                result["scopes"] = [dict(model_code=r[0], market=r[1], powertrain=r[2], feedback_records=r[3])
                    for r in connection.execute("SELECT model_code,country,powertrain,count(*) FROM feedback_records GROUP BY model_code,country,powertrain ORDER BY model_code,country,powertrain")]
            if "youtube_findings" in tables:
                result["youtube_findings"], result["youtube_videos"] = connection.execute(
                    "SELECT count(*),count(DISTINCT json_extract(payload_json,'$.video_id')) FROM youtube_findings").fetchone()
            if "video_memories" in tables:
                result["video_memories"] = connection.execute("SELECT count(DISTINCT video_id) FROM video_memories").fetchone()[0]
    return SourceCatalog.model_validate(result)


def sync_youtube(database: str | Path, root: Path = ROOT) -> SyncResult:
    if not Database(database).exists():
        raise ValueError("Import the supplied database before syncing saved research.")
    runs = saved_youtube_runs(root)
    if len(runs) > 100:
        raise ValueError("More than 100 saved research runs were found. Import them with the research workbench first.")
    counts = dict(runs=len(runs), inserted=0, accepted=0, rejected=0, failed_runs=0, memories_inserted=0)
    if runs:
        storage = Database(database)
        storage.initialize()
        for directory in runs:
            try:
                result = import_youtube_run(storage, directory)
                counts["inserted"] += result["inserted"]
                counts["accepted"] += result["accepted"]
                counts["rejected"] += len(result["rejected"])
                # Findings and reusable source text have separate acceptance rules.
                # A retrieved transcript remains useful when extraction was empty or failed.
                with storage.connect() as connection:
                    findings = [json.loads(row[0]) for row in connection.execute(
                        "SELECT payload_json FROM youtube_findings WHERE json_extract(payload_json,'$.bundle_sha256')=?",
                        (result["bundle_sha256"],))]
                memory_sources = {}
                for finding in findings:
                    identity = (finding["video_id"], finding["generation"])
                    memory_sources[identity] = finding["payload"].get("source", {})
                for source in json.loads((directory / "sources.json").read_text(encoding="utf-8")):
                    if not isinstance(source, dict):
                        continue
                    generation = source.get("research_generation")
                    if source.get("retrieval_status") == "retrieved" and generation in {"F70", "G60", "G70"}:
                        memory_sources[(source["video_id"], generation)] = source
                for (identifier, generation), source in memory_sources.items():
                    url = f"https://www.youtube.com/watch?v={identifier}"
                    video_id(url)  # Validate before constructing a transcript path.
                    raw_bytes = (directory / "transcripts" / f"{identifier}.json").read_bytes()
                    raw = raw_bytes.decode("utf-8")
                    segments = json.loads(raw)
                    if not isinstance(segments, list) or not all(isinstance(segment, dict)
                            and isinstance(segment.get("text"), str)
                            and isinstance(segment.get("start"), (int, float))
                            and math.isfinite(segment["start"]) and segment["start"] >= 0 for segment in segments):
                        raise ValueError("Invalid saved transcript segments")
                    transcript = "\n".join(f"[{segment['start']}s] {segment['text']}" for segment in segments)
                    if len(transcript.strip()) < 50:
                        continue
                    memory = save_transcript(database, TranscriptInput(
                        video_url=url, title=source.get("title") or "Saved video transcript",
                        model_code=generation, transcript=transcript),
                        source_kind="retrieved_transcript", source_locator={"bundle_sha256": result["bundle_sha256"],
                            "original_transcript_sha256": sha256_bytes(raw_bytes),
                            "scope_basis": "collector research generation; market not established",
                            "transformation": "Joined saved segment text with supplied start times."},
                        original_transcript_json=raw)
                    counts["memories_inserted"] += int(memory["inserted"])
            except (OSError, ValueError, KeyError, TypeError):
                counts["failed_runs"] += 1
    return SyncResult(**counts)


def execute(action: str, payload: dict, database: str | Path, emit: Callable[[dict], None], *,
            root: Path = ROOT, provider_factory=AdvisorProvider) -> None:
    if action == "catalog":
        emit({"type": "catalog", "catalog": source_catalog(database, root).model_dump(mode="json")})
    elif action == "sync":
        emit({"type": "sync", "sync": sync_youtube(database, root).model_dump(mode="json"),
              "catalog": source_catalog(database, root).model_dump(mode="json")})
    elif action == "scenarios":
        request = ScenarioRequest.model_validate(payload)
        emit({"type": "scenarios", "rows": scenario_results(
            [row.model_dump() for row in request.rows], years=request.years,
            discount_rate=request.discount_rate, source=request.source)})
    elif action == "memory":
        emit({"type": "memory", "memory": save_transcript(database, TranscriptInput.model_validate(payload)),
              "catalog": source_catalog(database, root).model_dump(mode="json")})
    elif action == "analyze":
        request = AdvisorRequest.model_validate(payload)
        credentials = project_credentials(root) or environment_credentials()
        if not credentials:
            raise ProviderError("Add OPENAI_API_KEY to the repository's local .env.local file, then retry.")
        provider = provider_factory(api_key=credentials.api_key, project_id=credentials.project_id)
        emit({"type": "progress", "message": "Checking saved YouTube findings against their source transcripts."})
        imported = sync_youtube(database, root)
        emit({"type": "progress", "message": f"Saved video evidence: {imported.inserted} new findings, {imported.rejected} rejected, {imported.failed_runs} unreadable runs. Video evidence stays separate from customer counts."})
        result = run_advisor(request, database, provider,
            progress=lambda message: emit({"type": "progress", "message": message}))
        emit({"type": "result", "result": result.model_dump(mode="json")})
    else:
        raise ValueError("Unsupported operation.")


def main() -> int:
    def emit(event: dict) -> None:
        print(json.dumps(event, ensure_ascii=False), flush=True)

    try:
        raw = sys.stdin.read(1048577)
        if len(raw) > 1048576:
            raise ValueError("The request is too large.")
        payload = json.loads(raw or "{}")
        database = database_target(root=ROOT)
        execute(sys.argv[1] if len(sys.argv) > 1 else "catalog", payload, database, emit)
        return 0
    except ValidationError as exc:
        messages = [f"{'.'.join(str(part) for part in error['loc']) or 'request'}: {error['msg']}"
                    for error in exc.errors(include_input=False, include_url=False)]
        emit({"type": "error", "message": "Check the decision inputs. " + "; ".join(messages)})
    except ProviderError as exc:
        emit({"type": "error", "message": str(exc)})
    except StorageError as exc:
        emit({"type": "error", "message": str(exc)})
    except (ValueError, OSError, sqlite3.Error):
        emit({"type": "error", "message": "The local request or evidence could not be loaded. Check the database and saved research configuration."})
    except Exception:
        emit({"type": "error", "message": "Research could not finish. No completed recommendation was generated."})
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
