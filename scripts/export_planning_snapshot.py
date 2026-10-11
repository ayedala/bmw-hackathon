"""Read-only, bounded data bridge for the local Next.js planning workbench.

Emits no credentials and never creates or mutates a database. The output is
served only by the loopback-bound local app; do not publish it as a static file.
"""
from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import sqlite3
import sys


ROOT = Path(__file__).resolve().parents[1]


def verified_payload(row) -> dict:
    payload = json.loads(row[0])
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    if hashlib.sha256(canonical.encode("utf-8")).hexdigest() != row[1]:
        raise ValueError("Database payload hash mismatch")
    return payload


def setting(name: str) -> str | None:
    if os.environ.get(name):
        return os.environ[name].strip()
    for file in (ROOT / ".env.local", ROOT / ".env"):
        if not file.is_file():
            continue
        for line in file.read_text(encoding="utf-8-sig").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() == name and value.strip():
                return value.strip().strip("\"'")
    return None


def snapshot() -> dict:
    target = (
        os.environ.get("DATABASE_URL")
        or os.environ.get("BMW_PM_DB_PATH")
        or os.environ.get("BMW_PM_DATABASE")
        or setting("DATABASE_URL")
        or setting("BMW_PM_DB_PATH")
        or setting("BMW_PM_DATABASE")
    )
    if not target:
        target = str(ROOT / "data" / "processed" / "bmw_pm.db")
    if target.startswith(("postgresql://", "postgres://")):
        import psycopg

        connection = psycopg.connect(target, connect_timeout=10, sslmode="require")
        connection.read_only = True
        connection.execute("SET search_path = bmw_pm, pg_catalog")
        backend = "postgres"
    else:
        file = Path(target).resolve()
        if not file.is_file():
            return {"available": False, "reason": "No imported evidence database is configured."}
        connection = sqlite3.connect(file.as_uri() + "?mode=ro", uri=True)
        connection.execute("PRAGMA query_only=ON")
        backend = "sqlite"
    try:
        proposals = json.loads((ROOT / "configs" / "successor_proposals_v1.json").read_text(encoding="utf-8"))
        anchor_ids = {anchor for proposal in proposals["proposals"] for anchor in proposal["anchor_ids"]}
        eligible = connection.execute(
            "SELECT count(*) FROM feedback_records WHERE model_code='G60' AND country='US'"
        ).fetchone()[0]
        bind = "%s" if backend == "postgres" else "?"
        feedback = (
            connection.execute(
                "SELECT payload_json,payload_hash FROM feedback_records WHERE model_code='G60' AND country='US' "
                f"AND source_record_id IN ({','.join([bind] * len(anchor_ids))}) ORDER BY record_id",
                tuple(sorted(anchor_ids)),
            ).fetchall()
            if anchor_ids else []
        )
        records = [verified_payload(row) for row in feedback]
        source_hashes = dict(connection.execute("SELECT source_id, sha256 FROM sources").fetchall())
        records = [
            item for item in records
            if item.get("row_locators")
            and all(
                locator.get("source_id") == item.get("source_id")
                and locator.get("source_hash") == source_hashes.get(item.get("source_id"))
                for locator in item["row_locators"]
            )
        ]
        signals = connection.execute(
            "SELECT s.payload_json,s.payload_hash FROM signals s JOIN feedback_records f ON f.record_id=s.feedback_record_id "
            "WHERE f.model_code='G60' AND f.country='US' ORDER BY s.signal_id"
        ).fetchall()
        return {
            "available": True,
            "backend": backend,
            "eligible_feedback_records": eligible,
            "feedback": [
                {
                    "record_id": item["record_id"],
                    "source_record_id": item["source_record_id"],
                    "redacted_text": item["redacted_text"],
                    "powertrain": item.get("powertrain"),
                    "row_locators": item.get("row_locators", []),
                }
                for item in records if item["source_record_id"] in anchor_ids
            ],
            "signals": [verified_payload(row) for row in signals],
        }
    finally:
        connection.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        print(json.dumps(snapshot(), ensure_ascii=False, separators=(",", ":")))
    except Exception as error:
        if os.environ.get("BMW_PM_DEBUG_SNAPSHOT") == "1":
            print(type(error).__name__, file=sys.stderr)
        print(json.dumps({"available": False, "reason": "The evidence database could not be read. Check the local database connection and schema."}))
        sys.exit(1)
