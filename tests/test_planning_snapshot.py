"""The web data bridge must expose only source-verified, immutable records."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3

import pytest


SPEC = importlib.util.spec_from_file_location(
    "planning_snapshot", Path(__file__).resolve().parents[1] / "scripts" / "export_planning_snapshot.py"
)
assert SPEC and SPEC.loader
snapshot_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(snapshot_module)


def stored(value: dict) -> tuple[str, str]:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    canonical = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return payload, hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def test_readonly_snapshot_requires_source_hash_and_payload_hash(tmp_path, monkeypatch):
    root = tmp_path
    (root / "configs").mkdir()
    (root / "configs" / "successor_proposals_v1.json").write_text(
        json.dumps({"proposals": [{"anchor_ids": ["G60-0001"]}]}), encoding="utf-8"
    )
    db_file = root / "evidence.db"
    with sqlite3.connect(db_file) as db:
        db.executescript(
            "CREATE TABLE sources (source_id TEXT, sha256 TEXT);"
            "CREATE TABLE feedback_records (record_id TEXT, source_record_id TEXT, model_code TEXT, country TEXT, payload_json TEXT, payload_hash TEXT);"
            "CREATE TABLE signals (signal_id TEXT, feedback_record_id TEXT, payload_json TEXT, payload_hash TEXT);"
        )
        source_hash = "a" * 64
        db.execute("INSERT INTO sources VALUES (?,?)", ("source-1", source_hash))
        feedback = {
            "record_id": "record-1", "source_record_id": "G60-0001", "source_id": "source-1",
            "redacted_text": "The control is hard to find.", "powertrain": "ICE",
            "row_locators": [{"source_id": "source-1", "source_hash": source_hash, "sheet": "Feedback_Explorer", "cell_range": "I2"}],
        }
        db.execute("INSERT INTO feedback_records VALUES (?,?,?,?,?,?)", ("record-1", "G60-0001", "G60", "US", *stored(feedback)))
        signal = {"signal_id": "signal-1", "need_domain": "controls_usability", "feedback_record_id": "record-1"}
        db.execute("INSERT INTO signals VALUES (?,?,?,?)", ("signal-1", "record-1", *stored(signal)))
    monkeypatch.setattr(snapshot_module, "ROOT", root)
    monkeypatch.setenv("BMW_PM_DB_PATH", str(db_file))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    result = snapshot_module.snapshot()
    assert result["available"] and result["eligible_feedback_records"] == 1
    assert len(result["feedback"]) == len(result["signals"]) == 1

    with sqlite3.connect(db_file) as db:
        db.execute("UPDATE sources SET sha256=?", ("b" * 64,))
    assert snapshot_module.snapshot()["feedback"] == []

    with sqlite3.connect(db_file) as db:
        db.execute("UPDATE feedback_records SET payload_hash=?", ("0" * 64,))
    with pytest.raises(ValueError, match="payload hash mismatch"):
        snapshot_module.snapshot()
