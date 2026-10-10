from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from bmw_pm.contracts import AcceptanceProposal, DecisionAction, RequirementRevision, RequirementScope
from bmw_pm.review import ReviewService
from bmw_pm.storage import Database, RevisionConflict
from bmw_pm.utils import utc_now


def _requirement() -> RequirementRevision:
    return RequirementRevision(
        requirement_id="req-synthetic-audit",
        revision=1,
        title="Synthetic audit candidate",
        customer_outcome="Complete a synthetic task.",
        scope=RequirementScope(models=["X99"], countries=["ZZ"], powertrains=["ICE"]),
        use_conditions=[],
        acceptance_proposal=AcceptanceProposal(method="Synthetic test"),
        target_status="pending_engineering_review",
        supporting_signal_ids=[],
        counter_signal_ids=[],
        alternatives=[],
        assumptions=["Synthetic fixture"],
        missing_evidence=["Synthetic gap"],
        feasibility="unknown",
        lifecycle_status="needs_review",
        created_by="test",
        created_at=utc_now(),
        denominator_feedback_records=0,
        processed_feedback_records=0,
        support_count=0,
        counter_count=0,
    )


def test_review_revision_idempotency_stale_conflict_and_replay(tmp_path: Path) -> None:
    database = Database(tmp_path / "audit.db")
    requirement = database.ensure_requirement(
        _requirement(), request_id="create-1", run_id="run-test"
    )
    service = ReviewService(database)
    with pytest.raises(ValueError, match="explicit acknowledgement"):
        service.decide(
            requirement_id=requirement.requirement_id,
            expected_revision=1,
            action=DecisionAction.APPROVE,
            rationale="Synthetic PM acknowledgement of remaining uncertainty.",
            actor_id="pm-test",
            request_id="approve-without-ack",
        )
    first = service.decide(
        requirement_id=requirement.requirement_id,
        expected_revision=1,
        action=DecisionAction.APPROVE,
        rationale="Synthetic PM acknowledgement of remaining uncertainty.",
        actor_id="pm-test",
        request_id="approve-1",
        uncertainty_acknowledged=True,
    )
    duplicate = service.decide(
        requirement_id=requirement.requirement_id,
        expected_revision=1,
        action=DecisionAction.APPROVE,
        rationale="Synthetic PM acknowledgement of remaining uncertainty.",
        actor_id="pm-test",
        request_id="approve-1",
        uncertainty_acknowledged=True,
    )
    assert first.decision_id == duplicate.decision_id
    assert first.uncertainty_acknowledged

    _, edited = service.edit(
        requirement_id=requirement.requirement_id,
        expected_revision=1,
        changes={"title": "Edited synthetic audit candidate"},
        rationale="Test immutable revision behavior.",
        actor_id="pm-test",
        request_id="edit-1",
    )
    assert edited.revision == 2
    assert edited.supersedes_revision == 1
    assert database.requirement(requirement.requirement_id, 1).title == requirement.title

    with pytest.raises(RevisionConflict, match="Stale review"):
        service.decide(
            requirement_id=requirement.requirement_id,
            expected_revision=1,
            action=DecisionAction.REJECT,
            rationale="This stale intention must not overwrite revision 2.",
            actor_id="pm-two",
            request_id="stale-1",
        )

    replay = database.replay_requirement(requirement.requirement_id)
    assert replay["audit_valid"] is True
    assert [item["revision"] for item in replay["revisions"]] == [1, 2]
    assert [item["action"] for item in replay["decisions"]] == ["approve", "edit"]
    assert any(event.result == "failure" for event in database.audit_events())


def test_audit_is_append_only_and_tamper_is_detected(tmp_path: Path) -> None:
    path = tmp_path / "tamper.db"
    database = Database(path)
    database.ensure_requirement(_requirement(), request_id="create-1", run_id="run-test")
    with database.connect() as connection:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("UPDATE audit_events SET action='tampered'")

    with database.connect() as connection:
        connection.execute("DROP TRIGGER audit_events_no_update")
        row = connection.execute(
            "SELECT monotonic_sequence,payload_json FROM audit_events ORDER BY monotonic_sequence LIMIT 1"
        ).fetchone()
        payload = json.loads(row["payload_json"])
        payload["reason"] = "tampered in disposable test"
        connection.execute(
            "UPDATE audit_events SET payload_json=? WHERE monotonic_sequence=?",
            (json.dumps(payload), row["monotonic_sequence"]),
        )
        connection.commit()
    valid, message = database.verify_audit_chain()
    assert valid is False
    assert "event hash mismatch" in message
