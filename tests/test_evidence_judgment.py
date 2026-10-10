"""Synthetic evidence-review transactions; these do not measure model quality."""

from pathlib import Path

import pytest

from bmw_pm.contracts import (
    AcceptanceProposal, EvidenceSpan, Polarity, RequirementRevision,
    RequirementScope, Signal, SourceLocator,
)
from bmw_pm.review import ReviewService
from bmw_pm.storage import Database, RevisionConflict, WorkflowError
from bmw_pm.utils import content_hash, utc_now


def _seed(database: Database) -> RequirementRevision:
    database.initialize()
    locator = SourceLocator(
        source_id="synthetic-source", source_hash="0" * 64,
        locator_type="sheet_range", sheet="Synthetic", cell_range="A2:L2",
        exact_quote="Synthetic complaint.",
    )
    signal = Signal(
        signal_id="signal-synthetic", feedback_record_id="record-synthetic",
        need_domain="synthetic_need", atomic_claim="Synthetic complaint.",
        customer_outcome="Complete a synthetic task.", polarity=Polarity.COMPLAINT,
        vehicle_scope={"model": "X99"},
        evidence_spans=[EvidenceSpan(
            record_id="record-synthetic", locator=locator,
            text="Synthetic complaint.", start=0, end=20,
        )],
        run_id="run-synthetic", provider_mode="baseline_no_ai",
    )
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO sources VALUES (?,?,?,?)",
            ("synthetic-source", "0" * 64, "{}", "synthetic-source-hash"),
        )
        connection.execute(
            """INSERT INTO feedback_records
               (record_id,source_id,source_record_id,model_code,country,powertrain,payload_json,payload_hash)
               VALUES (?,?,?,?,?,?,?,?)""",
            ("record-synthetic", "synthetic-source", "X-1", "X99", "ZZ", "ICE", "{}", "synthetic-record-hash"),
        )
        connection.execute(
            """INSERT INTO signals
               (signal_id,feedback_record_id,need_domain,polarity,run_id,payload_json,payload_hash)
               VALUES (?,?,?,?,?,?,?)""",
            (signal.signal_id, signal.feedback_record_id, signal.need_domain,
             signal.polarity.value, signal.run_id, signal.model_dump_json(), content_hash(signal)),
        )
        connection.commit()
    requirement = RequirementRevision(
        requirement_id="req-synthetic", revision=1, title="Synthetic candidate",
        customer_outcome="Complete a synthetic task.",
        scope=RequirementScope(models=["X99"], countries=["ZZ"], powertrains=["ICE"]),
        use_conditions=[], acceptance_proposal=AcceptanceProposal(method="Synthetic review"),
        target_status="pending_engineering_review", supporting_signal_ids=[signal.signal_id],
        counter_signal_ids=[], alternatives=[], assumptions=["Synthetic fixture"],
        missing_evidence=[], feasibility="unknown", lifecycle_status="needs_review",
        created_by="test", created_at=utc_now(), denominator_feedback_records=1,
        processed_feedback_records=1, support_count=1, counter_count=0,
    )
    return database.ensure_requirement(requirement, request_id="create-synthetic", run_id="run-synthetic")


def test_evidence_judgment_is_audited_idempotent_and_revision_scoped(tmp_path: Path) -> None:
    database = Database(tmp_path / "judgment.db")
    requirement = _seed(database)
    service = ReviewService(database)
    judgment = service.judge_evidence_link(
        requirement_id=requirement.requirement_id, expected_revision=1,
        signal_id="signal-synthetic", verdict="does_not_support",
        rationale="The wording does not establish the proposed outcome.",
        actor_id="reviewer-test", request_id="judge-1",
    )
    duplicate = service.judge_evidence_link(
        requirement_id=requirement.requirement_id, expected_revision=1,
        signal_id="signal-synthetic", verdict="does_not_support",
        rationale="The wording does not establish the proposed outcome.",
        actor_id="reviewer-test", request_id="judge-1",
    )
    assert judgment.judgment_id == duplicate.judgment_id
    assert database.latest_evidence_judgments(requirement.requirement_id, 1)["signal-synthetic"].verdict == "does_not_support"
    assert database.replay_requirement(requirement.requirement_id)["evidence_judgments"][0]["verdict"] == "does_not_support"
    assert database.verify_audit_chain()[0]
    assert [event.action for event in database.audit_events()].count("review_evidence_link") == 1

    with pytest.raises(WorkflowError, match="not linked"):
        service.judge_evidence_link(
            requirement_id=requirement.requirement_id, expected_revision=1,
            signal_id="other-signal", verdict="supports", rationale="Wrong link",
            actor_id="reviewer-test", request_id="judge-wrong",
        )
    _, new_revision = service.edit(
        requirement_id=requirement.requirement_id, expected_revision=1,
        changes={"title": "Revised synthetic candidate"}, rationale="New review cycle",
        actor_id="reviewer-test", request_id="edit-synthetic",
    )
    assert new_revision.revision == 2
    with pytest.raises(RevisionConflict, match="Stale evidence review"):
        service.judge_evidence_link(
            requirement_id=requirement.requirement_id, expected_revision=1,
            signal_id="signal-synthetic", verdict="supports", rationale="Now stale",
            actor_id="reviewer-test", request_id="judge-stale",
        )
    assert database.latest_evidence_judgments(requirement.requirement_id, 2) == {}
    assert database.verify_audit_chain()[0]
