"""Import allowlisted foreign evidence as unreviewed context, preserving its original lineage."""

from __future__ import annotations

import json
from contextlib import closing
import shutil
import sqlite3
from uuid import uuid4
from pathlib import Path
from typing import Any

from ..contracts import ImportedEvidenceRow
from ..pipeline import ingest_supplied_data
from ..storage import Database
from ..utils import content_hash, sha256_file

# Explicit evidence allowlist: never execute the foreign database's SQL or triggers.
TABLES = (
    "source_document", "source_locator", "ingestion_batch", "transformation",
    "sales_observation", "equipment_fact", "external_claim", "source_registry",
    "benchmark_vehicle", "benchmark_cohort_member", "benchmark_review", "web_research_seed",
)


def copy_immutable(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if sha256_file(source) != sha256_file(destination):
            raise ValueError(f"Refusing to overwrite different local evidence: {destination}")
    else:
        shutil.copy2(source, destination)
    if sha256_file(source) != sha256_file(destination):
        raise ValueError(f"Copy hash mismatch: {destination}")


def import_workspace(*, database: Database, source_root: Path, local_root: Path,
                     profile: dict[str, Any]) -> dict[str, Any]:
    source_root = source_root.resolve()
    local_root = local_root.resolve()
    if source_root == local_root:
        raise ValueError("Source and destination workspaces must differ")
    source_db = source_root / "data/processed/bmw_product_lab.db"
    if not source_db.is_file():
        raise FileNotFoundError(source_db)
    # Online backup includes committed WAL content and never modifies the source.
    archive_dir = local_root / "data/processed/imports"
    archive_dir.mkdir(parents=True, exist_ok=True)
    temporary = archive_dir / "incoming.sqlite"
    if temporary.exists():
        raise ValueError(f"Unfinished import exists: {temporary}")
    with closing(sqlite3.connect(source_db.as_uri() + "?mode=ro", uri=True)) as original:
        with closing(sqlite3.connect(temporary)) as snapshot:
            original.backup(snapshot)
            if snapshot.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Source database integrity check failed")
            if snapshot.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise ValueError("Source database contains unresolved references")
    archive_hash = sha256_file(temporary)
    archive = archive_dir / f"{archive_hash}.db"
    copy_immutable(temporary, archive)
    temporary.unlink()
    copied = []
    for relative in ("data/raw", "research/local"):
        folder = source_root / relative
        if not folder.exists():
            continue
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                destination = local_root / path.relative_to(source_root)
                copy_immutable(path, destination)
                copied.append({"path": str(path.relative_to(source_root)),
                               "sha256": sha256_file(destination)})
    normalized = ingest_supplied_data(database=database,
        input_dir=local_root / "data/raw/provided", profile=profile)
    database.initialize()
    counts = {}
    with closing(sqlite3.connect(archive.as_uri() + "?mode=ro", uri=True)) as legacy:
        legacy.row_factory = sqlite3.Row
        available = {r[0] for r in legacy.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"source_document", "source_locator", "feedback_record"} <= available:
            raise ValueError("Unsupported source database schema")
        with database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("""CREATE TABLE IF NOT EXISTS imported_evidence (
                archive_sha256 TEXT NOT NULL, table_name TEXT NOT NULL, row_key TEXT NOT NULL,
                payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL,
                PRIMARY KEY (archive_sha256, table_name, row_key))""")
            connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_imported_row_key ON imported_evidence(row_key)")
            for table in TABLES:
                if table not in available:
                    continue
                count = 0
                for row in legacy.execute(f'SELECT * FROM "{table}"'):
                    payload = dict(row)
                    key = content_hash({"archive": archive_hash, "table": table, "payload": payload})
                    item = ImportedEvidenceRow(archive_sha256=archive_hash,
                        table_name=table, row_key=key, payload=payload)
                    database._insert_immutable(connection, "imported_evidence", "row_key", key,
                        {"archive_sha256": archive_hash, "table_name": table, "row_key": key,
                         "payload_json": item.model_dump_json(), "payload_hash": content_hash(item)})
                    count += 1
                counts[table] = count
            # Reconciliation against canonical source IDs, without counting labels as records.
            foreign_counts = dict(legacy.execute("SELECT model_code, COUNT(*) FROM feedback_record GROUP BY model_code"))
            for model, count in foreign_counts.items():
                if normalized["feedback"].get(model, {}).get("accepted_feedback_ids") != count:
                    raise ValueError(f"Foreign/canonical feedback mismatch: {model}")
            database._append_audit(connection, actor_id="workspace-import", actor_type="pipeline",
                action="import_evidence_archive", object_type="database_archive", object_id=archive_hash,
                object_revision=None, before_hash=None, after_hash=archive_hash,
                reason="Preserved foreign evidence and locators; rebuilt canonical feedback/studies. Claims remain unreviewed.",
                request_id=f"workspace-import:{archive_hash}", result="success")
            connection.commit()
    report = {"archive_sha256": archive_hash, "archive_path": str(archive),
              "copied_files": copied, "normalized": normalized, "context_rows": counts,
              "limitations": ["Foreign approvals and rankings are not promoted into active decisions.",
                               "Context claims require scope and entailment review before affecting scores."]}
    (archive_dir / f"{archive_hash}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def evidence_context(database: Database, table: str, limit: int = 100) -> list[ImportedEvidenceRow]:
    if table not in TABLES or not 1 <= limit <= 1000:
        raise ValueError("Unsupported evidence table or limit")
    with database.connect() as connection:
        exists = connection.execute("SELECT 1 FROM sqlite_master WHERE name='imported_evidence'").fetchone()
        if not exists:
            return []
        rows = connection.execute("SELECT payload_json FROM imported_evidence WHERE table_name=? ORDER BY row_key LIMIT ?",
                                  (table, limit)).fetchall()
        database._append_audit(connection, actor_id="local-evidence-reader", actor_type="pipeline",
            action="read_imported_evidence", object_type="evidence_table", object_id=table,
            object_revision=None, before_hash=None, after_hash=None, reason=f"Read {len(rows)} imported context rows",
            request_id=uuid4().hex, result="success")
        connection.commit()
        return [ImportedEvidenceRow.model_validate_json(row[0]) for row in rows]
