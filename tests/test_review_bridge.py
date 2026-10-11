"""Tests for the web frontend's review bridge.

The point of the bridge is that PM actions become backend-backed: the browser
stops being the authority. So these tests check the things that only hold if
the backend really is in charge - that a stale revision is refused, that a
replayed request_id does not produce a second decision, that every write lands
in the audit chain, and that failures come back as typed codes rather than as
an excuse for the frontend to trust local state.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bmw_pm.contracts import (
    AcceptanceProposal,
    EvidenceSpan,
    Polarity,
    RequirementRevision,
    RequirementScope,
    Signal,
    SourceLocator,
)
from bmw_pm.review import bridge
from bmw_pm.storage import Database
from bmw_pm.utils import content_hash, utc_now

REQUIREMENT_ID = "req-synthetic-bridge"


def _requirement(revision: int = 1) -> RequirementRevision:
    return RequirementRevision(
        requirement_id=REQUIREMENT_ID,
        revision=revision,
        title="Synthetic bridge candidate",
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


SIGNAL_ID = "signal-synthetic-bridge"


def _seed_signal(database: Database) -> None:
    """A judgment may only be made on a signal genuinely linked to the revision,
    so the signal has to exist in the database for that path to be testable."""
    database.initialize()
    locator = SourceLocator(
        source_id="synthetic-source", source_hash="0" * 64,
        locator_type="sheet_range", sheet="Synthetic", cell_range="A2:L2",
        exact_quote="Synthetic complaint.",
    )
    signal = Signal(
        signal_id=SIGNAL_ID, feedback_record_id="record-synthetic-bridge",
        need_domain="synthetic_need", atomic_claim="Synthetic complaint.",
        customer_outcome="Complete a synthetic task.", polarity=Polarity.COMPLAINT,
        vehicle_scope={"model": "X99"},
        evidence_spans=[EvidenceSpan(
            record_id="record-synthetic-bridge", locator=locator,
            text="Synthetic complaint.", start=0, end=20,
        )],
        run_id="run-test", provider_mode="baseline_no_ai",
    )
    with database.connect() as connection:
        connection.execute("INSERT INTO sources VALUES (?,?,?,?)",
                           ("synthetic-source", "0" * 64, "{}", "synthetic-source-hash"))
        connection.execute(
            """INSERT INTO feedback_records
               (record_id,source_id,source_record_id,model_code,country,powertrain,payload_json,payload_hash)
               VALUES (?,?,?,?,?,?,?,?)""",
            ("record-synthetic-bridge", "synthetic-source", "X-1", "X99", "ZZ", "ICE",
             "{}", "synthetic-record-hash"))
        connection.execute(
            """INSERT INTO signals
               (signal_id,feedback_record_id,need_domain,polarity,run_id,payload_json,payload_hash)
               VALUES (?,?,?,?,?,?,?)""",
            (signal.signal_id, signal.feedback_record_id, signal.need_domain,
             signal.polarity.value, signal.run_id, signal.model_dump_json(),
             content_hash(signal)))
        connection.commit()


@pytest.fixture
def seeded(tmp_path: Path) -> tuple[Path, Database]:
    path = tmp_path / "review.db"
    database = Database(path)
    _seed_signal(database)
    requirement = _requirement().model_copy(
        update={"supporting_signal_ids": [SIGNAL_ID], "support_count": 1,
                "denominator_feedback_records": 1, "processed_feedback_records": 1})
    database.ensure_requirement(requirement, request_id="create-1", run_id="run-test")
    return path, database


def run(action: str, payload: dict, path: Path) -> list[dict]:
    """Invoke the dispatcher directly, collecting emitted events."""
    events: list[dict] = []
    bridge.execute(action, payload, path, events.append)
    return events


def only(events: list[dict], event_type: str) -> dict:
    matches = [e for e in events if e.get("type") == event_type]
    assert len(matches) == 1, f"expected one {event_type!r}, got {[e.get('type') for e in events]}"
    return matches[0]


# --------------------------------------------------------------------------- #

class TestState:
    def test_reports_the_authoritative_revision(self, seeded):
        path, _ = seeded
        state = only(run("state", {"requirement_ids": [REQUIREMENT_ID]}, path), "state")
        entry = state["requirements"][0]
        assert entry["present"] is True
        assert entry["revision"] == 1
        assert entry["lifecycle_status"] == "needs_review"

    def test_absent_requirement_is_reported_not_invented(self, seeded):
        path, _ = seeded
        state = only(run("state", {"requirement_ids": ["req-does-not-exist"]}, path), "state")
        entry = state["requirements"][0]
        assert entry["present"] is False
        assert "review database" in entry["detail"]

    def test_empty_id_list_returns_everything_present(self, seeded):
        path, _ = seeded
        state = only(run("state", {}, path), "state")
        assert [e["requirement_id"] for e in state["requirements"]] == [REQUIREMENT_ID]

    def test_unused_database_is_empty_not_broken(self, tmp_path):
        """An empty review database must not look like an unavailable backend."""
        state = only(run("state", {}, tmp_path / "never-used.db"), "state")
        assert state["requirements"] == []

    def test_readiness_is_reported_with_its_blockers(self, seeded):
        path, _ = seeded
        entry = only(run("state", {}, path), "state")["requirements"][0]
        # The repository policy is unapproved on purpose, so readiness must
        # exist and must not be clear.
        assert entry["readiness"] is not None, entry["readiness_note"]
        assert entry["readiness"]["blockers"]


class TestDecide:
    def _payload(self, **overrides) -> dict:
        base = {
            "requirement_id": REQUIREMENT_ID,
            "expected_revision": 1,
            "action": "defer",
            "rationale": "Waiting on engineering feasibility input.",
            "actor_id": "pm.test",
            "request_id": "req-decide-1",
        }
        base.update(overrides)
        return base

    def test_records_a_decision(self, seeded):
        path, _ = seeded
        events = run("decide", self._payload(), path)
        decision = only(events, "decision")["decision"]
        assert decision["action"] == "defer"
        assert decision["expected_revision"] == 1

    def test_decision_is_persisted_and_visible_in_state(self, seeded):
        path, _ = seeded
        run("decide", self._payload(), path)
        entry = only(run("state", {}, path), "state")["requirements"][0]
        assert entry["decision"]["action"] == "defer"

    def test_decision_lands_in_the_audit_chain(self, seeded):
        path, database = seeded
        before = len(database.audit_events())
        run("decide", self._payload(), path)
        after = database.audit_events()
        assert len(after) > before
        valid, _ = database.verify_audit_chain()
        assert valid

    def test_replaying_a_request_id_does_not_decide_twice(self, seeded):
        """Idempotency belongs to the backend, not to a browser guard."""
        path, database = seeded
        first = only(run("decide", self._payload(), path), "decision")["decision"]
        second = only(run("decide", self._payload(), path), "decision")["decision"]
        assert first["decision_id"] == second["decision_id"]
        decisions = [
            item for item in database.audit_events()
            if item.request_id == "req-decide-1"
        ]
        assert len(decisions) == 1

    def test_stale_revision_is_refused(self, seeded):
        from bmw_pm.storage import RevisionConflict
        path, _ = seeded
        with pytest.raises(RevisionConflict):
            run("decide", self._payload(expected_revision=7, request_id="stale-1"), path)

    def test_approval_requires_acknowledging_uncertainty(self, seeded):
        path, _ = seeded
        with pytest.raises(ValueError, match="acknowledgement"):
            run("decide", self._payload(action="approve", request_id="ack-1"), path)

    def test_approval_succeeds_once_acknowledged(self, seeded):
        path, _ = seeded
        events = run("decide", self._payload(
            action="approve", request_id="ack-2", uncertainty_acknowledged=True), path)
        assert only(events, "decision")["decision"]["action"] == "approve"

    def test_blank_rationale_is_rejected_by_validation(self, seeded):
        from pydantic import ValidationError
        path, _ = seeded
        with pytest.raises(ValidationError):
            run("decide", self._payload(rationale="", request_id="blank-1"), path)

    def test_edit_action_is_not_reachable_through_decide(self, seeded):
        """decide() refuses EDIT; the bridge must not offer a way around it."""
        from pydantic import ValidationError
        path, _ = seeded
        with pytest.raises(ValidationError):
            run("decide", self._payload(action="edit", request_id="edit-via-decide"), path)


class TestEdit:
    def _payload(self, **overrides) -> dict:
        base = {
            "requirement_id": REQUIREMENT_ID,
            "expected_revision": 1,
            "changes": {"title": "Synthetic bridge candidate, retitled"},
            "rationale": "Clarified the customer wording.",
            "actor_id": "pm.test",
            "request_id": "req-edit-1",
        }
        base.update(overrides)
        return base

    def test_edit_creates_an_immutable_new_revision(self, seeded):
        path, database = seeded
        event = only(run("edit", self._payload(), path), "edit")
        assert event["revision"]["revision"] == 2
        # The original revision must still be readable unchanged.
        assert database.requirement(REQUIREMENT_ID, 1).title == "Synthetic bridge candidate"

    def test_state_follows_the_new_revision(self, seeded):
        path, _ = seeded
        run("edit", self._payload(), path)
        entry = only(run("state", {}, path), "state")["requirements"][0]
        assert entry["revision"] == 2
        assert entry["requirement"]["title"] == "Synthetic bridge candidate, retitled"

    def test_unsupported_field_is_refused(self, seeded):
        path, _ = seeded
        with pytest.raises(ValueError, match="unsupported edit fields"):
            run("edit", self._payload(
                changes={"feasibility": "feasible_reviewed"},
                request_id="bad-field-1"), path)

    def test_empty_changes_is_refused_by_validation(self, seeded):
        from pydantic import ValidationError
        path, _ = seeded
        with pytest.raises(ValidationError):
            run("edit", self._payload(changes={}, request_id="empty-1"), path)

    def test_editing_a_stale_revision_is_refused(self, seeded):
        from bmw_pm.storage import RevisionConflict
        path, _ = seeded
        run("edit", self._payload(), path)
        with pytest.raises(RevisionConflict):
            run("edit", self._payload(request_id="second-edit-1"), path)


class TestJudgeLink:
    def test_judgment_is_recorded_against_the_revision(self, seeded):
        path, _ = seeded
        events = run("judge_link", {
            "requirement_id": REQUIREMENT_ID,
            "expected_revision": 1,
            "signal_id": SIGNAL_ID,
            "verdict": "supports",
            "rationale": "The quote states the same outcome.",
            "actor_id": "pm.test",
            "request_id": "judge-1",
        }, path)
        judgment = only(events, "judgment")["judgment"]
        assert judgment["signal_id"] == SIGNAL_ID
        assert judgment["verdict"] == "supports"
        state = only(events, "judgment")["state"]
        assert state["judgments"][SIGNAL_ID]["verdict"] == "supports"

    def test_judging_an_unlinked_signal_is_refused(self, seeded):
        """A judgment must attach to evidence genuinely linked to the revision."""
        from bmw_pm.storage import WorkflowError
        path, _ = seeded
        with pytest.raises(WorkflowError, match="not linked"):
            run("judge_link", {
                "requirement_id": REQUIREMENT_ID, "expected_revision": 1,
                "signal_id": "signal-never-linked", "verdict": "supports",
                "rationale": "Should not be accepted.", "actor_id": "pm.test",
                "request_id": "judge-unlinked-1",
            }, path)

    def test_unknown_verdict_is_refused(self, seeded):
        from pydantic import ValidationError
        path, _ = seeded
        with pytest.raises(ValidationError):
            run("judge_link", {
                "requirement_id": REQUIREMENT_ID,
                "expected_revision": 1,
                "signal_id": SIGNAL_ID,
                "verdict": "looks_fine",
                "rationale": "x",
                "actor_id": "pm.test",
                "request_id": "judge-bad-1",
            }, path)


class TestAudit:
    def test_audit_action_reports_a_verifiable_chain(self, seeded):
        path, _ = seeded
        run("decide", {
            "requirement_id": REQUIREMENT_ID, "expected_revision": 1, "action": "defer",
            "rationale": "Deferred pending input.", "actor_id": "pm.test",
            "request_id": "audit-decide-1",
        }, path)
        event = only(run("audit", {}, path), "audit")
        assert event["valid"] is True
        assert event["events"]
        assert any(e["request_id"] == "audit-decide-1" for e in event["events"])


class TestDispatch:
    def test_unknown_action_is_refused(self, seeded):
        path, _ = seeded
        with pytest.raises(ValueError, match="Unsupported review operation"):
            run("delete_everything", {}, path)


class TestNoReviewLogicInTheBridge:
    """The bridge must stay a transport, so the rules live in one place."""

    def test_bridge_does_not_reimplement_the_editable_field_list(self):
        source = (Path(bridge.__file__)).read_text()
        assert "EDITABLE_FIELDS" not in source
        assert "customer_outcome" not in source

    def test_bridge_never_constructs_review_objects_itself(self):
        """Decisions and revisions are built by the service, never here."""
        source = (Path(bridge.__file__)).read_text()
        assert "Decision(" not in source
        assert "RequirementRevision(" not in source
        assert "EvidenceLinkJudgment(" not in source

    def test_bridge_passes_approval_gating_through_rather_than_repeating_it(self):
        source = (Path(bridge.__file__)).read_text()
        # The flag is forwarded, but the rule that approval requires it lives
        # in ReviewService.decide and must not be restated here.
        assert "uncertainty_acknowledged" in source
        assert "approval requires" not in source
