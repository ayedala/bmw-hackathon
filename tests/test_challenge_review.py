"""No-network challenge retrieval, deterministic scoring and atomic PM review."""
from datetime import date
import sqlite3

import pytest

from bmw_pm.contracts import AcceptanceProposal, CriterionInput, RequirementRevision, RequirementScope
from bmw_pm.review.canonical import build_score, evidence_reference, import_canonical
from bmw_pm.review.challenge import ChallengeService
from bmw_pm.review.service import ReviewService
from bmw_pm.storage import Database
from bmw_pm.storage.database import RevisionConflict, WorkflowError
from bmw_pm.utils import canonical_json, content_hash, utc_now


def evidence(identity, **overrides):
    text = "Charging speed improves long distance journeys."
    return {"evidence_id": identity, "source_url": f"https://example.invalid/{identity}",
        "source_title": "Synthetic test source", "source_family": "independent_test_org",
        "claim": text, "evidence_text": text, "source_start_char": 0, "source_end_char": len(text),
        "market": "DE", "brand": "BMW", "vehicle": "BMW 5 Series", "topic": "charging",
        "subtopic": "charging_speed", "source_quality": 90, "independence_group": identity,
        "retrieved_at": "2026-10-10", "duplicate_of": None, **overrides}


@pytest.fixture
def seeded(tmp_path):
    database = Database(tmp_path / "review.sqlite")
    rows = [evidence("support-1"), evidence("support-2"),
        evidence("duplicate-1", duplicate_of="support-1", independence_group="support-1"),
        evidence("opposition-1", stance="opposes", market="US", brand="Mercedes"),
        evidence("context-1", market="EU")]
    requirement = RequirementRevision(requirement_id="REQ-TEST-CHARGING", revision=1,
        title="Charging speed for long distance journeys", customer_outcome="Charge reliably on long journeys.",
        topic="charging", planning_horizon="2030", scope=RequirementScope(models=["BMW 5 Series"], countries=["DE"], powertrains=[]),
        use_conditions=[], acceptance_proposal=AcceptanceProposal(method="Measured charging task"),
        target_status="pending_engineering_review", supporting_signal_ids=[], counter_signal_ids=[],
        evidence_references=[evidence_reference(row, "supports", "test-corpus") for row in rows[:3]],
        alternatives=[], assumptions=[], missing_evidence=["No controlled DE journey measurement"],
        feasibility="unknown", lifecycle_status="needs_review", created_by="test", created_at=utc_now(),
        denominator_feedback_records=0, processed_feedback_records=0, support_count=3, counter_count=0)
    database.ensure_requirement(requirement, request_id="create", run_id="test")
    baseline = build_score(requirement, rows[:3], [], run_id="baseline", corpus_hash="test-corpus",
        today=date(2026, 10, 11), customer_impact=CriterionInput(value=3, basis="Synthetic PM test input"))
    database.persist_score(baseline, request_id="baseline")
    with database.connect() as connection:
        docs = [("evidence", row["evidence_id"], row) for row in rows]
        docs.extend([("findings", "finding-1", {"finding_id": "finding-1", "topic": "charging", "summary": "Charging speed for long distance journeys", "evidence_ids": ["support-1"]}),
            ("needs", "need-1", {"need_id": "need-1", "topic": "charging", "statement": "Reliable charging speed for long journeys"}),
            ("requirements", requirement.requirement_id, {"requirement_id": requirement.requirement_id, "topic": "charging", "title": requirement.title}),
            # A score sharing the requirement ID must never overwrite the searchable requirement.
            ("scores", requirement.requirement_id, {"requirement_id": requirement.requirement_id, "weighted_score": 3})])
        for kind, identity, payload in docs:
            connection.execute("INSERT INTO canonical_artifacts VALUES (?,?,?,?,?,?)",
                (f"{kind}:{identity}", "test-corpus", kind, identity, canonical_json(payload), content_hash(payload)))
        connection.commit()
    return database, ChallengeService(database, root=tmp_path), requirement, baseline


def challenge(service, **overrides):
    return service.challenge(**{"requirement_id": "REQ-TEST-CHARGING", "expected_revision": 1,
        "hypothesis": "Charging speed may not be supported for long distance journeys",
        "rationale": "Review duplicate and opposing evidence before approving", "actor_id": "pm.test",
        "request_id": "challenge-1", **overrides})


def resolve(service, record, **overrides):
    return service.reassess(**{"challenge_id": record["challenge_id"], "requirement_id": record["requirement_id"],
        "expected_revision": 1, "accept": True, "rationale": "Reviewed the retrieved exact evidence and accept its bounded score",
        "actor_id": "pm.test", "request_id": "resolution-1", **overrides})


def test_retrieves_real_roles_keeps_context_and_unchanged_factors(seeded):
    database, service, _, baseline = seeded
    record = challenge(service)
    assert record["before"] == baseline.coverage["crps"]
    assert {item["item_id"] for item in record["retrieval"]["opposing"]} == {"opposition-1"}
    assert "context-1" in {item["item_id"] for item in record["retrieval"]["context"]}
    assert "context-1" not in record["evidence_ids"]
    assert record["retrieval"]["opposing"][0]["applicability"] == "context_market_unconfirmed"
    assert record["after"]["evidence_strength"]["duplicate_rows_excluded"] == 1
    assert record["after"]["evidence_strength"]["supporting_groups"] == 2
    assert record["after"]["evidence_strength"]["contradicting_groups"] == 1
    for name in ("customer_impact", "frequency", "strategic_fit"):
        assert record["proposed_score"]["criterion_inputs"][name] == baseline.criterion_inputs[name].model_dump(mode="json")
    assert {"evidence", "findings", "needs", "requirements"} <= record["retrieval"]["searched_counts"].keys()
    assert database.latest_score(record["requirement_id"], 1) == baseline
    assert database.verify_audit_chain()[0]
    assert record["retrieval"]["supporting"][0]["payload"]["source_url"].startswith("https://")


def test_accept_is_atomic_audited_idempotent_and_replayable(seeded):
    database, service, requirement, baseline = seeded
    record = challenge(service)
    assert challenge(service) == record
    resolution = resolve(service, record)
    assert resolve(service, record) == resolution
    score = database.latest_score(requirement.requirement_id, 1)
    assert score.score_snapshot_id != baseline.score_snapshot_id
    assert score.coverage["crps"] == record["after"]
    assert score.coverage["evidence_ids"] == record["evidence_ids"]
    assert service.history(requirement.requirement_id)[0]["resolution"] == resolution
    replay = database.replay_requirement(requirement.requirement_id)
    assert replay["challenges"][0]["resolution"] == resolution
    assert replay["score_snapshots"][-1]["score_snapshot_id"] == score.score_snapshot_id
    assert database.verify_audit_chain()[0]
    assert [event.action for event in database.audit_events()][-2:] == ["challenge_requirement", "accept_reassessment"]
    with pytest.raises(WorkflowError):
        resolve(service, record, request_id="another-resolution")


def test_rejection_does_not_change_score(seeded):
    database, service, requirement, baseline = seeded
    record = challenge(service)
    resolution = resolve(service, record, accept=False)
    assert not resolution["accepted"]
    assert database.latest_score(requirement.requirement_id, 1) == baseline
    assert database.audit_events()[-1].action == "reject_reassessment"


def test_request_ids_cannot_be_reused_with_different_input(seeded):
    _, service, _, _ = seeded
    record = challenge(service)
    with pytest.raises(WorkflowError):
        challenge(service, hypothesis="A different challenge")
    resolve(service, record)
    with pytest.raises(WorkflowError):
        resolve(service, record, accept=False)


def test_judgments_change_proposal_and_make_pending_results_stale(seeded):
    database, service, requirement, baseline = seeded
    record = challenge(service)
    judgment = database.record_evidence_judgment(requirement_id=requirement.requirement_id, expected_revision=1,
        signal_id="support-2", verdict="does_not_support", rationale="Claim does not entail the requirement",
        actor_id="pm.test", request_id="judge-1")
    assert database.latest_evidence_judgments(requirement.requirement_id, 1)["support-2"] == judgment
    with pytest.raises(RevisionConflict):
        resolve(service, record)
    assert database.audit_events()[-1].result == "failure"
    assert database.audit_events()[-1].action == "challenge_revision_conflict"
    revised = challenge(service, request_id="challenge-2")
    assert "support-2" in revised["retrieval"]["excluded_evidence_ids"]
    assert "support-2" not in revised["evidence_ids"]
    assert revised["after"]["confidence"]["value_0_to_100"] < baseline.coverage["crps"]["confidence"]["value_0_to_100"]
    assert database.replay_requirement(requirement.requirement_id)["evidence_judgments"][0]["signal_id"] == "support-2"


def test_stale_revision_cannot_be_reassessed(seeded):
    database, service, requirement, _ = seeded
    record = challenge(service)
    ReviewService(database).edit(requirement_id=requirement.requirement_id, expected_revision=1,
        changes={"title": "Edited charging title"}, rationale="Clarify title", actor_id="pm.test", request_id="edit")
    with pytest.raises(RevisionConflict):
        resolve(service, record)


def test_another_accepted_proposal_makes_a_pending_score_stale(seeded):
    _, service, _, _ = seeded
    first = challenge(service)
    pending = challenge(service, request_id="challenge-2")
    resolve(service, first)
    with pytest.raises(RevisionConflict):
        resolve(service, pending, request_id="resolution-2")


def test_existing_youtube_planning_and_feedback_are_searchable_context(seeded):
    database, service, _, _ = seeded
    with database.connect() as connection:
        connection.execute("CREATE TABLE youtube_findings (evidence_id TEXT PRIMARY KEY,payload_json TEXT NOT NULL)")
        youtube = {"evidence_id": "YT-TEST", "topic": "charging", "source_statement": "Charging speed for long journeys",
            "supporting_excerpt": "Charging speed for long journeys", "timestamp_seconds": 32,
            "transcript_segment": {"text": "Charging speed for long journeys", "start": 32}}
        connection.execute("INSERT INTO youtube_findings VALUES (?,?)", ("YT-TEST", canonical_json(youtube)))
        planning = {"context_id": "planning-test", "topic": "charging", "observation": "Charging speed matters on long journeys"}
        connection.execute("INSERT INTO report_context VALUES (?,?,?,?)", ("planning-test", "report-test", canonical_json(planning), content_hash(planning)))
        connection.execute("INSERT INTO sources VALUES (?,?,?,?)", ("source-test", "0" * 64, "{}", "test"))
        feedback = {"record_id": "feedback-test", "country": "DE", "text_customer": "Charging speed for long journeys"}
        connection.execute("INSERT INTO feedback_records VALUES (?,?,?,?,?,?,?,?)",
            ("feedback-test", "source-test", "record-1", "G60", "DE", "BEV", canonical_json(feedback), content_hash(feedback)))
        connection.commit()
    record = challenge(service)
    context_ids = {item["item_id"] for item in record["retrieval"]["context"]}
    assert {"YT-TEST", "planning-test", "feedback-test"} <= context_ids
    assert {"youtube", "planning_context", "internal_feedback"} <= record["retrieval"]["searched_counts"].keys()
    assert record["retrieval"]["searched_counts"]["internal_feedback"] == 1
    youtube_hit = next(item for item in record["retrieval"]["context"] if item["item_id"] == "YT-TEST")
    assert youtube_hit["payload"]["transcript_segment"] == youtube["transcript_segment"]


@pytest.mark.parametrize("table", ["canonical_artifacts", "requirement_challenges", "challenge_resolutions", "heterogeneous_evidence_judgments"])
def test_new_records_are_immutable(seeded, table):
    database, service, requirement, _ = seeded
    record = challenge(service)
    resolve(service, record)
    database.record_evidence_judgment(requirement_id=requirement.requirement_id, expected_revision=1,
        signal_id="support-1", verdict="supports", rationale="Exact quote checked", actor_id="pm.test", request_id="judge")
    with database.connect() as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute(f"UPDATE {table} SET payload_json='{{}}'")


def test_blank_hypothesis_is_rejected(seeded):
    _, service, _, _ = seeded
    with pytest.raises(ValueError):
        challenge(service, hypothesis="  ")


def test_actual_canonical_requirement_can_be_challenged_and_reassessed(tmp_path):
    database = Database(tmp_path / "canonical.sqlite")
    imported = import_canonical(database, actor_id="pm.test", request_id="canonical-import", rationale="Import existing real artifacts for review")
    assert len(imported["requirement_ids"]) == 14
    identity = imported["requirement_ids"][0]
    service = ChallengeService(database)
    record = challenge(service, requirement_id=identity, hypothesis="Physical controls may still require visual attention")
    assert record["retrieval"]["searched_counts"]["evidence"] == 979
    assert record["retrieval"]["searched_counts"]["findings"] == 20
    assert record["retrieval"]["searched_counts"]["needs"] == 15
    assert record["retrieval"]["searched_counts"]["requirements"] == 14
    resolution = resolve(service, record)
    assert resolution["accepted"]
    assert database.latest_score(identity, 1).coverage["challenge_id"] == record["challenge_id"]
    assert database.verify_audit_chain()[0]
