"""Persistence: JSONL append, the local page cache and the visited-URL ledger.

Every write lands under ``src/bmw_pm/data_pipeline/web_research/data/``. JSON files are
replaced atomically (temp file + ``os.replace``) so an interrupted run cannot
leave a half-written ledger behind.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterator

from pydantic import BaseModel

import config
from models import ProcessedEvidence, RawPage, ResearchRun
from utils import cache_filename, canonicalize_url, get_logger, utc_now_iso


# --------------------------------------------------------------------------- #
# Generic JSON / JSONL helpers
# --------------------------------------------------------------------------- #


def read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    """Yield each JSON object in *path*, skipping blank and unparsable lines.

    A truncated final line (an interrupted previous run) is logged and skipped
    rather than raising, so a damaged store never blocks a new run.
    """
    if not path.is_file():
        return
    log = get_logger()
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                log.warning("skipping unparsable line %s:%d (%s)", path.name, line_number, exc)


def append_jsonl(path: Path, rows: list[dict[str, Any]]) -> int:
    """Append *rows* to *path* as one JSON object per line. Returns rows written."""
    if not rows:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=False))
            handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    return len(rows)


def append_models(path: Path, models: list[BaseModel]) -> int:
    """Append pydantic *models* to *path*, preserving declared field order."""
    return append_jsonl(path, [model.model_dump(mode="json") for model in models])


def load_json(path: Path, default: Any) -> Any:
    """Read a JSON file, returning *default* when missing or unparsable."""
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        get_logger().warning("could not read %s (%s); using default", path, exc)
        return default


def save_json_atomic(path: Path, payload: Any) -> None:
    """Write *payload* to *path* atomically via a temp file in the same directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
    )
    try:
        with handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(handle.name, path)
    except BaseException:
        Path(handle.name).unlink(missing_ok=True)
        raise


# --------------------------------------------------------------------------- #
# Typed stores
# --------------------------------------------------------------------------- #


def append_raw_pages(pages: list[RawPage]) -> int:
    """Append scraped pages to ``data/raw/raw_pages.jsonl``."""
    return append_models(config.RAW_PAGES_PATH, list(pages))


def existing_evidence_ids(path: Path | None = None) -> set[str]:
    """Return the ``evidence_id`` values already in an evidence store.

    Because ids are derived from canonical URL plus normalized claim, this set
    is what makes re-running the pipeline idempotent.
    """
    return {
        row["evidence_id"]
        for row in read_jsonl(path or config.PROCESSED_EVIDENCE_PATH)
        if isinstance(row.get("evidence_id"), str)
    }


def append_processed_evidence(
    records: list[ProcessedEvidence], *, path: Path | None = None
) -> int:
    """Append processed evidence, skipping ids already present on disk.

    Returns the number of records actually written.
    """
    if not records:
        return 0
    target = path or config.PROCESSED_EVIDENCE_PATH
    known = existing_evidence_ids(target)
    fresh = [record for record in records if record.evidence_id not in known]
    skipped = len(records) - len(fresh)
    if skipped:
        get_logger().info("skipped %d evidence record(s) already in %s", skipped, target.name)
    return append_models(target, list(fresh))


def rebuild_processed_evidence(
    records: list[ProcessedEvidence],
    *,
    path: Path,
    replace_source_urls: set[str],
) -> tuple[int, int]:
    """Replace the rows for *replace_source_urls* in *path* with *records*.

    Append-only storage is right for a scrape run, where each page is fetched
    once. It is wrong for reprocessing, which re-derives evidence for pages that
    already have rows: appending would grow the file on every pass, and
    id-based skipping would not catch it because a model that rewords a claim
    produces a new ``evidence_id``.

    So rows belonging to the reprocessed pages are dropped and rewritten. Rows
    from any other page are preserved untouched. Running twice over the same
    cache therefore yields the same file.

    The write is atomic: a temp file in the same directory is moved into place,
    so an interrupted rebuild cannot truncate the store.

    Returns:
        ``(rows_preserved, rows_written)``.
    """
    log = get_logger()
    preserved = [
        row for row in read_jsonl(path)
        if row.get("source_url") not in replace_source_urls
    ]
    fresh = [record.model_dump(mode="json") for record in records]

    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
    )
    try:
        with handle:
            for row in preserved + fresh:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=False))
                handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(handle.name, path)
    except BaseException:
        Path(handle.name).unlink(missing_ok=True)
        raise

    log.info(
        "rebuilt %s: %d row(s) preserved, %d row(s) written for %d reprocessed page(s)",
        path.name, len(preserved), len(fresh), len(replace_source_urls),
    )
    return len(preserved), len(fresh)


def append_research_run(run: ResearchRun) -> None:
    """Append a run record to ``data/metadata/research_runs.jsonl``."""
    append_models(config.RESEARCH_RUNS_PATH, [run])


def write_run_checkpoint(run: ResearchRun, *, pages_done: int, pages_total: int) -> None:
    """Rewrite the in-progress checkpoint atomically.

    Called after every page so an interrupted run leaves a truthful record of
    how far it got. A single JSON file rewritten in place, rather than a row
    per page, keeps ``research_runs.jsonl`` free of partial records.
    """
    payload = run.model_dump(mode="json")
    payload["checkpoint_written_at"] = utc_now_iso()
    payload["pages_done"] = pages_done
    payload["pages_total"] = pages_total
    save_json_atomic(config.RUN_CHECKPOINT_PATH, payload)


def clear_run_checkpoint() -> None:
    """Remove the checkpoint once the final run record is durable."""
    config.RUN_CHECKPOINT_PATH.unlink(missing_ok=True)


# --------------------------------------------------------------------------- #
# Local page cache
# --------------------------------------------------------------------------- #


class PageCache:
    """Content-addressed cache of scraped pages under ``data/cache/``.

    The filename is a SHA-256 of the canonical URL, so the same page always maps
    to the same file across runs and machines. A cache hit means no Firecrawl
    scrape call and therefore no credit spend.
    """

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or config.CACHE_DIR
        self.directory.mkdir(parents=True, exist_ok=True)

    def path_for(self, url: str) -> Path:
        """Deterministic cache path for *url*."""
        return self.directory / cache_filename(url)

    def has(self, url: str) -> bool:
        """Whether a cached payload exists for *url*."""
        return self.path_for(url).is_file()

    def get(self, url: str) -> dict[str, Any] | None:
        """Return the cached payload for *url*, or ``None`` if absent/unreadable."""
        path = self.path_for(url)
        if not path.is_file():
            return None
        payload = load_json(path, default=None)
        return payload if isinstance(payload, dict) else None

    def put(self, url: str, payload: dict[str, Any]) -> Path:
        """Store *payload* for *url* and return the file path."""
        path = self.path_for(url)
        record = dict(payload)
        record.setdefault("canonical_url", canonicalize_url(url))
        record.setdefault("cached_at", utc_now_iso())
        save_json_atomic(path, record)
        return path


# --------------------------------------------------------------------------- #
# Visited-URL ledger
# --------------------------------------------------------------------------- #


class VisitedUrlStore:
    """Ledger of canonical URLs the pipeline has already handled.

    Backed by ``data/metadata/visited_urls.json``. Entries record the outcome so
    a URL that failed can be retried on a later run while successful ones are
    skipped unless ``--force`` is passed.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or config.VISITED_URLS_PATH
        raw = load_json(self.path, default={})
        self._entries: dict[str, dict[str, Any]] = raw if isinstance(raw, dict) else {}

    # -- reads -------------------------------------------------------------- #

    def __contains__(self, url: str) -> bool:
        return canonicalize_url(url) in self._entries

    def __len__(self) -> int:
        return len(self._entries)

    def get(self, url: str) -> dict[str, Any] | None:
        """Return the ledger entry for *url*, if any."""
        return self._entries.get(canonicalize_url(url))

    #: Outcomes that will not change on a later run, so the URL should stop
    #: competing for a page-budget slot. Deliberately short: an extraction
    #: failure, a zero-evidence page or a temporary provider error may all
    #: succeed next time and are never terminal. An off-topic verdict is not
    #: terminal either, because the relevance vocabulary keeps evolving.
    TERMINAL_STATUSES: frozenset[str] = frozenset({"thin", "unsupported"})

    def is_terminal(self, url: str) -> bool:
        """Whether *url* was deterministically judged not worth fetching again.

        Keyed on a sticky ``terminal`` flag rather than the current ``status``:
        a later cache hit rewrites ``status`` to ``cached``, and that must not
        erase the record that the page was already judged unusable.
        """
        entry = self.get(url)
        if not entry:
            return False
        if entry.get("terminal"):
            return True
        return entry.get("status") in self.TERMINAL_STATUSES

    def was_scraped(self, url: str) -> bool:
        """Whether *url* has ever been scraped successfully.

        Keyed on ``last_scraped_at`` rather than the current ``status``: a later
        cache hit updates the status to ``cached``, and that must not erase the
        record that the page was already paid for.
        """
        entry = self.get(url)
        return bool(entry and entry.get("last_scraped_at"))

    # -- writes ------------------------------------------------------------- #

    def mark(
        self,
        url: str,
        *,
        status: str,
        title: str = "",
        topic: str = "",
        query: str = "",
        detail: str = "",
        terminal: bool | None = None,
    ) -> None:
        """Record an outcome for *url*.

        *status* is one of ``scraped``, ``cached``, ``failed``, ``filtered``,
        ``thin`` or ``unsupported``. First-seen time is preserved across
        updates.

        *terminal* marks the URL as not worth fetching again. The flag is
        sticky: once set it survives every later update, so a cache hit that
        rewrites ``status`` cannot clear it. Pass it only for deterministic
        verdicts - never for a transient failure.
        """
        key = canonicalize_url(url)
        existing = self._entries.get(key, {})
        now = utc_now_iso()
        entry: dict[str, Any] = {
            "first_seen_at": existing.get("first_seen_at", now),
            "last_seen_at": now,
            "status": status,
            "attempts": int(existing.get("attempts", 0)) + 1,
            "original_url": existing.get("original_url", url),
        }
        for field, value in (("title", title), ("topic", topic), ("query", query), ("detail", detail)):
            chosen = value or existing.get(field) or ""
            if chosen:
                entry[field] = chosen
        was_terminal = bool(existing.get("terminal")) or existing.get("status") in self.TERMINAL_STATUSES
        if terminal or was_terminal or status in self.TERMINAL_STATUSES:
            entry["terminal"] = True
        if status == "scraped":
            entry["last_scraped_at"] = now
            entry["cache_file"] = cache_filename(url)
        elif existing.get("last_scraped_at"):
            entry["last_scraped_at"] = existing["last_scraped_at"]
            entry["cache_file"] = existing.get("cache_file", cache_filename(url))
        self._entries[key] = entry

    def save(self) -> None:
        """Persist the ledger atomically."""
        save_json_atomic(self.path, self._entries)


def load_processed_in_groups(
    groups: set[str], *, path: Path | None = None
) -> list[ProcessedEvidence]:
    """Load stored evidence belonging to any of *groups*.

    Used so that a second run over the same forum thread marks new near-
    duplicates against the records already on disk instead of appending them
    again. Rows that no longer validate are skipped with a warning rather than
    aborting the run.
    """
    if not groups:
        return []
    log = get_logger()
    loaded: list[ProcessedEvidence] = []
    for row in read_jsonl(path or config.PROCESSED_EVIDENCE_PATH):
        if row.get("independence_group") not in groups:
            continue
        try:
            loaded.append(ProcessedEvidence.model_validate(row))
        except Exception as exc:  # noqa: BLE001 - tolerate older/odd rows
            log.warning("skipping stored record %s: %s", row.get("evidence_id"), exc)
    return loaded
