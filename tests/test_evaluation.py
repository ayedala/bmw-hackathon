from pathlib import Path
import json
import pytest

from bmw_pm.contracts import FeedbackRecord, SourceLocator
from bmw_pm.evaluation import build_manifest, freeze_evaluation


def records():
    result = []
    for model in ("G60", "F70", "G70"):
        for i in range(8):
            result.append(FeedbackRecord(record_id=f"{model}-{i}", source_id=model,
                source_record_id=str(i), raw_text_ref="synthetic", cleaned_text=f"{model} text {i}",
                redacted_text=f"{model} text {i}", raw_country="ZZ", country="ZZ", raw_model=model,
                model_code=model, raw_brand="BMW", raw_sales_description=model, raw_derivative=model,
                powertrain_raw="ICE", powertrain="ICE", powertrain_mapping_status="exact",
                source_label="A", row_locators=[SourceLocator(source_id=model, source_hash="0"*64,
                    locator_type="sheet_range", sheet="Synthetic", cell_range=f"I{i+2}")], transformation_ids=[]))
    return result


def test_deterministic_grouped_split_and_insufficient_input():
    data = records()
    duplicate = data[0].model_copy(update={"record_id": "duplicate", "source_record_id": "duplicate"})
    first = build_manifest(data + [duplicate], sizes=(2,2,2,2))
    assert first == build_manifest(list(reversed(data + [duplicate])), sizes=(2,2,2,2))
    assert len(first.records) == 8
    assert len({r.group_hash for r in first.records}) == 8
    with pytest.raises(ValueError, match="insufficient"):
        build_manifest(data)


def test_no_cross_model_duplicate_group_leakage():
    data = records()
    data[8] = data[8].model_copy(update={"redacted_text": data[0].redacted_text})
    manifest = build_manifest(data, sizes=(2,2,2,2))
    assert not {"G60-0", "F70-0"}.intersection(r.record_id for r in manifest.records)


def test_freeze_retry_preserves_human_labels_and_rejects_tampering(tmp_path, monkeypatch):
    import bmw_pm.evaluation as evaluation
    from bmw_pm.storage import Database
    data = records()
    original = build_manifest
    monkeypatch.setattr(evaluation, "build_manifest", lambda records, seed: original(records,seed=seed,sizes=(2,2,2,2)))
    db = Database(tmp_path / "test.db")
    db.initialize()
    monkeypatch.setattr(db, "feedback_records", lambda: data)
    output = tmp_path / "frozen"
    assert freeze_evaluation(db,output)["status"] == "created"
    labels = output / "human_labels.jsonl"
    labels.write_text('human work preserved',encoding="utf-8")
    assert freeze_evaluation(db,output)["status"] == "unchanged"
    assert labels.read_text() == 'human work preserved'
    packet = json.loads((output / "development.jsonl").read_text().splitlines()[0])
    assert "legacy_annotations" not in packet and "signals" not in packet
    assert db.verify_audit_chain()[0]
    (output / "development.jsonl").write_text('tampered',encoding="utf-8")
    with pytest.raises(ValueError, match="differs"):
        freeze_evaluation(db,output)
