"""Real canonical requirements must cross the same review boundary as feedback."""
from __future__ import annotations

import json
import shutil
import sqlite3
import pytest
from pydantic import ValidationError

from bmw_pm.contracts import EvidenceReference
from bmw_pm.review import bridge
from bmw_pm.review.canonical import ARTIFACT_FILES, PROCESSED_PATH, ROOT, canonical_view, import_canonical
from bmw_pm.storage import Database
from bmw_pm.storage.database import RevisionConflict, WorkflowError

RID = "REQ-005-CHG-SUSTAINED-POWER"


@pytest.fixture
def canonical_db(tmp_path):
    database = Database(tmp_path / "canonical.db")
    imported = import_canonical(database, actor_id="pm.test", request_id="import-1",
                                rationale="Import the real Germany 2030 corpus for review.")
    return database, imported


def test_read_only_canonical_preview_does_not_create_database(tmp_path):
    path = tmp_path / "must-not-exist.db"
    events = []
    bridge.execute("canonical", {}, path, events.append)
    assert not path.exists()
    assert events[0]["type"] == "canonical"
    assert events[0]["counts"] == {"evidence": 979, "findings": 20, "needs": 15,
                                  "requirements": 14, "scores": 14}
    assert len(events[0]["requirements"]) == 14


def test_imports_real_requirements_without_false_internal_provenance(canonical_db):
    database, imported = canonical_db
    assert len(imported["created"]) == 14
    for item in database.requirement_summaries():
        requirement = item["requirement"]
        assert requirement.requirement_id.startswith("REQ-")
        assert not requirement.supporting_signal_ids
        assert not requirement.evidence_links
        assert requirement.evidence_references
        assert requirement.scope.countries == ["DE"]
        assert requirement.planning_horizon == "2030"
        assert requirement.need_ids and requirement.finding_ids
        for ref in requirement.evidence_references:
            assert ref.evidence_kind == "external_web"
            assert ref.provenance["origin"] == "canonical_web_research"
            assert ref.exact_text == ref.provenance["source_record"]["evidence_text"]
            assert ref.source_end_char - ref.source_start_char == len(ref.exact_text)
            assert ref.source_url == ref.provenance["source_record"]["source_url"]
            assert ref.semantic_entailment == "unreviewed"
    with database.connect() as connection:
        assert connection.execute("SELECT count(*) FROM signals").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM canonical_artifacts WHERE artifact_kind='evidence'").fetchone()[0] == 979


def test_import_is_idempotent_and_does_not_overwrite_pm_revision(canonical_db):
    database, _ = canonical_db
    bridge.execute("edit", {"requirement_id": RID, "expected_revision": 1,
        "changes": {"title": "PM clarified sustained charging"}, "rationale": "Clarify wording.",
        "actor_id": "pm.test", "request_id": "edit-1"}, database.path, lambda event: None)
    before_events = len(database.audit_events())
    replay = import_canonical(database, actor_id="pm.test", request_id="import-1",
                               rationale="Import the real Germany 2030 corpus for review.")
    assert replay["replayed"]
    assert len(database.audit_events()) == before_events
    again = import_canonical(database, actor_id="pm.test", request_id="import-2", rationale="Recheck import.")
    assert not again["created"]
    assert database.latest_requirement(RID).revision == 2
    assert database.latest_requirement(RID).title == "PM clarified sustained charging"
    assert database.requirement(RID, 1).title != "PM clarified sustained charging"
    with pytest.raises(WorkflowError, match="different input"):
        import_canonical(database, actor_id="different", request_id="import-1", rationale="Changed input.")


def test_scores_are_python_crps_with_unknown_prevalence(canonical_db):
    database, _ = canonical_db
    score = database.latest_score(RID, 1)
    assert score.policy_id == "crps_v1"
    assert len(score.criterion_inputs) == 7
    assert score.criterion_inputs["frequency"].value is None
    assert score.criterion_inputs["strategic_fit"].value is None
    assert score.lower_bound < score.upper_bound
    assert score.coverage["crps"]["result"]["crps_100_lower"] == score.lower_bound
    assert score.coverage["crps"]["factor_evidence_ids"]["evidence_strength"]
    assert score.coverage["crps"]["confidence"]["value_0_to_100"] >= 0


def test_semantic_edit_is_reassessable_but_does_not_keep_stale_impact(canonical_db):
    database, _ = canonical_db
    payload = {"requirement_id": RID, "expected_revision": 1,
               "changes": {"customer_outcome": "The driver shall see reliable charging predictions in cold weather."},
               "actor_id": "pm.test", "request_id": "semantic-edit", "rationale": "Clarify winter use conditions."}
    bridge.execute("edit", payload, database.path, lambda event: None)
    score = database.latest_score(RID, 2)
    assert score is not None
    assert score.criterion_inputs["customer_impact"].value is None
    bridge.execute("edit", payload, database.path, lambda event: None)
    assert database.latest_score(RID, 2).score_snapshot_id == score.score_snapshot_id
    events = []
    bridge.execute("challenge", {"requirement_id": RID, "expected_revision": 2,
        "hypothesis": "Winter charging predictions may not be supported by Germany evidence.",
        "actor_id": "pm.test", "request_id": "challenge-edited", "rationale": "Test the revised outcome."},
        database.path, events.append)
    assert events[0]["challenge"]["requirement_revision"] == 2


def test_real_external_link_can_be_judged_and_audited(canonical_db):
    database, _ = canonical_db
    ref = database.latest_requirement(RID).evidence_references[0]
    payload = {"requirement_id": RID, "expected_revision": 1, "signal_id": ref.evidence_id,
               "verdict": "does_not_support", "rationale": "Not matched to the target use condition.",
               "actor_id": "pm.test", "request_id": "external-judgment-1"}
    events = []
    bridge.execute("judge_link", payload, database.path, events.append)
    state = events[0]["state"]
    assert state["judgments"][ref.evidence_id]["verdict"] == "does_not_support"
    assert state["revisions"][0]["requirement_id"] == RID
    assert state["evidence_judgments"][0]["signal_id"] == ref.evidence_id
    assert database.verify_audit_chain()[0]
    with pytest.raises(RevisionConflict):
        bridge.execute("judge_link", {**payload, "expected_revision": 9, "request_id": "stale-link"},
                       database.path, lambda event: None)


def test_import_audit_preserves_lineage_and_full_history(canonical_db):
    database, _ = canonical_db
    actions = {event.action for event in database.audit_events()}
    assert {"evidence_import", "finding_generation_import", "need_derivation_import",
            "create_requirement_candidate", "score_requirement", "import_canonical"} <= actions
    events = []
    bridge.execute("audit", {}, database.path, events.append)
    assert len(events[0]["events"]) == len(database.audit_events())
    assert len(events[0]["events"]) > 200
    assert events[0]["valid"]
    with database.connect() as connection:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute("UPDATE canonical_artifacts SET payload_json='{}'")


def test_incomplete_real_corpus_fails_without_demo_fallback(tmp_path):
    target = tmp_path / PROCESSED_PATH
    target.mkdir(parents=True)
    for filename, _ in ARTIFACT_FILES.values():
        shutil.copyfile(ROOT / PROCESSED_PATH / filename, target / filename)
    rows = [json.loads(line) for line in (target / "requirements.jsonl").read_text().splitlines()]
    rows[0]["evidence_ids"].append("MISSING-REAL-EVIDENCE")
    (target / "requirements.jsonl").write_text("\n".join(json.dumps(row) for row in rows))
    with pytest.raises(ValueError, match="Dangling canonical"):
        canonical_view(tmp_path)


@pytest.mark.parametrize("kind", ["internal_feedback", "external_web", "youtube", "study", "planning_context"])
def test_additive_reference_accepts_explicit_kinds_without_erasing_locator(kind):
    ref = EvidenceReference(evidence_id="channel-evidence", evidence_kind=kind, role="context",
                            claim="A traceable claim.", exact_text="Exact span", source_start_char=1,
                            source_end_char=11, source_locator={"timestamp_seconds": 10},
                            provenance={"run_id": "known-run"})
    assert ref.evidence_kind == kind
    assert ref.source_locator["timestamp_seconds"] == 10
    assert ref.provenance["run_id"] == "known-run"


def test_reference_rejects_broken_exact_span():
    with pytest.raises(ValidationError, match="span length"):
        EvidenceReference(evidence_id="bad", evidence_kind="external_web", role="supports",
                          claim="Claim", exact_text="Quote", source_start_char=10, source_end_char=12)
