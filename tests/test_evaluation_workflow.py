import json

import pytest

from bmw_pm.contracts import FeedbackRecord, SourceLocator
from bmw_pm.evaluation import build_manifest, freeze_evaluation
from bmw_pm.evaluation_workflow import load_frozen, load_labels, run_extraction, score_extraction
from bmw_pm.evaluation_review import ReviewInputError, review_snapshot, save_review
from bmw_pm.intelligence.baseline import BaselineExtractionProvider
from bmw_pm.storage import Database


@pytest.fixture
def frozen(tmp_path, monkeypatch):
    import bmw_pm.evaluation as evaluation

    records = []
    for model in ("G60", "F70", "G70"):
        for i in range(8):
            text = f"The touchscreen is a problem on {model} example {i}."
            records.append(FeedbackRecord(
                record_id=f"{model}-{i}", source_id=model, source_record_id=str(i),
                raw_text_ref="fixture", cleaned_text=text, redacted_text=text,
                raw_country="US", country="US", raw_model=model, model_code=model,
                raw_brand="BMW", raw_sales_description=model, raw_derivative=model,
                powertrain_raw="ICE", powertrain="ICE", powertrain_mapping_status="exact",
                source_label="A", row_locators=[SourceLocator(source_id=model,
                    source_hash="0" * 64, locator_type="sheet_range", sheet="Synthetic",
                    cell_range=f"I{i+2}")], transformation_ids=[]))
    original = build_manifest
    monkeypatch.setattr(evaluation, "build_manifest", lambda items, seed: original(items, seed=seed, sizes=(2, 2, 2, 2)))
    db = Database(tmp_path / "evaluation.db")
    db.initialize()
    monkeypatch.setattr(db, "feedback_records", lambda: records)
    root = tmp_path / "frozen"
    freeze_evaluation(db, root)
    return root


def _label_first(root, *, reviewer="reviewer-a"):
    rows = [json.loads(line) for line in (root / "human_labels.jsonl").read_text(encoding="utf-8").splitlines()]
    record_id = rows[0]["record_id"]
    _, packets = load_frozen(root)
    text = packets[record_id].text
    signal = {"need_domain": "controls_usability", "atomic_claim": "The touchscreen is a problem",
              "customer_outcome": "Controls are usable", "polarity": "complaint",
              "evidence_text": "touchscreen is a problem", "evidence_start": text.index("touchscreen"),
              "evidence_end": text.index("touchscreen") + len("touchscreen is a problem"),
              "use_context": None, "uncertainties": []}
    rows[0].update(reviewer_id=reviewer, review_status="labelled", signals=[signal])
    (root / "human_labels.jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    return rows, signal


def test_frozen_hash_and_human_span_validation(frozen):
    manifest, packets = load_frozen(frozen)
    _, _, report = load_labels(frozen, manifest, packets)
    assert report == {"total": 8, "unlabelled": 8, "provisional": 0,
                      "gold_ready": 0, "second_reviewed": 0}
    rows, _ = _label_first(frozen)
    rows[0]["signals"][0]["evidence_text"] = "unsupported text"
    (frozen / "human_labels.jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="span does not match"):
        load_labels(frozen, manifest, packets)
    packet_file = frozen / "development.jsonl"
    packet_file.write_text(packet_file.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        load_frozen(frozen)


def test_double_review_requires_independence_and_adjudication(frozen):
    rows, signal = _label_first(frozen)
    manifest, packets = load_frozen(frozen)
    _, _, report = load_labels(frozen, manifest, packets)
    assert report["provisional"] == 1 and report["gold_ready"] == 0
    second = {**rows[0], "adjudication": None}
    secondary_path = frozen / "second_review.jsonl"
    secondary_path.write_text(json.dumps(second) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="independent"):
        load_labels(frozen, manifest, packets, second_review=secondary_path)
    second["reviewer_id"] = "reviewer-b"
    secondary_path.write_text(json.dumps(second) + "\n", encoding="utf-8")
    rows[0]["adjudication"] = {"reviewer_id": "adjudicator", "reason": "Both reviewers agree",
                                 "signals": [signal], "abstention_reason": None}
    (frozen / "human_labels.jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    _, _, report = load_labels(frozen, manifest, packets, second_review=secondary_path)
    assert report["gold_ready"] == 1 and report["second_reviewed"] == 1


def test_resumable_baseline_and_scoring_without_gold(frozen, tmp_path):
    provider = BaselineExtractionProvider.from_file("configs/baseline_taxonomy_v1.json")
    output = tmp_path / "baseline-development"
    first = run_extraction(frozen, output, provider)
    assert first["attempted"] == 2 and first["success"] == 2
    assert run_extraction(frozen, output, provider)["reused"] == 2
    changed = BaselineExtractionProvider({**provider.config, "label": "changed configuration"})
    with pytest.raises(ValueError, match="identity changed"):
        run_extraction(frozen, output, changed)
    assert score_extraction(frozen, output)["metrics"] is None
    rows, signal = _label_first(frozen)
    secondary_path = frozen / "second_review.jsonl"
    second = {**rows[0], "reviewer_id": "reviewer-b", "adjudication": None}
    secondary_path.write_text(json.dumps(second) + "\n", encoding="utf-8")
    rows[0]["adjudication"] = {"reviewer_id": "adjudicator", "reason": "Reviewed",
                                 "signals": [signal], "abstention_reason": None}
    (frozen / "human_labels.jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    result = score_extraction(frozen, output, second_review=secondary_path)
    assert result["metrics"]["records"] == 1
    assert result["metrics"]["true_positive"] == 1
    assert result["gold_ready_in_split"] == result["scored_records"] == 1
    assert result["citation_entailment"] == "unmeasured_human_review_required"


def test_review_screen_preserves_blind_second_review_and_requires_adjudication(frozen, tmp_path, monkeypatch):
    import bmw_pm.evaluation_review as review
    monkeypatch.setattr(review, "_root", lambda _: frozen)
    initial = review_snapshot(tmp_path)
    case = initial["case"]
    assert initial["counts"]["gold_ready"] == 0
    quote = "touchscreen is a problem"
    signal = {"need_domain": "controls_usability", "atomic_claim": "The touchscreen is a problem",
              "customer_outcome": "Controls are usable", "polarity": "complaint", "evidence_text": quote}
    primary = save_review(tmp_path, {"role": "primary", "record_id": case["record_id"],
        "file_version": initial["file_version"], "reviewer_id": "reviewer-a", "signals": [signal]})
    assert primary["counts"]["provisional"] == 1
    assert primary["case"]["review"]["reviewed_at"]
    with pytest.raises(ReviewInputError, match="Reload"):
        save_review(tmp_path, {"role": "primary", "record_id": case["record_id"],
            "file_version": initial["file_version"], "reviewer_id": "reviewer-a", "signals": [signal]})
    blind = review_snapshot(tmp_path, record_id=case["record_id"], role="secondary")
    assert "primary" not in blind["case"] and blind["case"]["review"] is None
    with pytest.raises(ReviewInputError, match="different"):
        save_review(tmp_path, {"role": "secondary", "record_id": case["record_id"],
            "file_version": blind["file_version"], "reviewer_id": "reviewer-a", "signals": [signal]})
    second = save_review(tmp_path, {"role": "secondary", "record_id": case["record_id"],
        "file_version": blind["file_version"], "reviewer_id": "reviewer-b", "signals": [signal]})
    assert second["counts"]["gold_ready"] == 0
    adjudicator = review_snapshot(tmp_path, record_id=case["record_id"], role="adjudicator")
    resolved = save_review(tmp_path, {"role": "adjudicator", "record_id": case["record_id"],
        "file_version": adjudicator["file_version"], "reviewer_id": "reviewer-c",
        "reason": "Both reviewers identified the same supported need.", "signals": [signal]})
    assert resolved["counts"]["gold_ready"] == 1
    assert resolved["case"]["primary"]["adjudication"]["reviewer_id"] == "reviewer-c"
    assert resolved["case"]["primary"]["adjudication"]["reviewed_at"]
    assert case["text"] == review_snapshot(tmp_path, record_id=case["record_id"])["case"]["text"]


def test_review_rejects_unsupported_quote_and_allows_explained_abstention(frozen, tmp_path, monkeypatch):
    import bmw_pm.evaluation_review as review
    monkeypatch.setattr(review, "_root", lambda _: frozen)
    initial = review_snapshot(tmp_path)
    case = initial["case"]
    with pytest.raises(ReviewInputError, match="exactly once"):
        save_review(tmp_path, {"role": "primary", "record_id": case["record_id"],
            "file_version": initial["file_version"], "reviewer_id": "reviewer-a",
            "signals": [{"need_domain": "controls_usability", "atomic_claim": "False claim",
                         "customer_outcome": "False outcome", "polarity": "complaint",
                         "evidence_text": "not present in the frozen packet"}]})
    saved = save_review(tmp_path, {"role": "primary", "record_id": case["record_id"],
        "file_version": initial["file_version"], "reviewer_id": "reviewer-a", "signals": [],
        "abstention_reason": "Cannot support an atomic need from this text."})
    assert saved["case"]["review"]["signals"] == []
    assert saved["case"]["review"]["abstention_reason"]
