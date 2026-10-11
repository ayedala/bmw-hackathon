"""PM decisions and immutable edits; persistence enforces concurrency and records audit events."""

from __future__ import annotations

from typing import Any

from ..contracts import Decision, DecisionAction, EvidenceLinkJudgment, RequirementRevision
from ..storage import Database
from ..utils import stable_id, utc_now


class ReviewService:
    """Application-level PM workflow; role selection is demonstrative, not authentication."""

    EDITABLE_FIELDS = {"title", "customer_outcome", "use_conditions", "assumptions", "acceptance_proposal", "target_status", "successor_draft_id"}

    def __init__(self, database: Database) -> None:
        self.database = database

    def judge_evidence_link(
        self,
        *,
        requirement_id: str,
        expected_revision: int,
        signal_id: str,
        verdict: str,
        rationale: str,
        actor_id: str,
        request_id: str,
    ) -> EvidenceLinkJudgment:
        return self.database.record_evidence_judgment(
            requirement_id=requirement_id,
            expected_revision=expected_revision,
            signal_id=signal_id,
            verdict=verdict,
            rationale=rationale,
            actor_id=actor_id,
            request_id=request_id,
        )

    def decide(
        self,
        *,
        requirement_id: str,
        expected_revision: int,
        action: DecisionAction,
        rationale: str,
        actor_id: str,
        request_id: str,
        role: str = "demo_pm",
        uncertainty_acknowledged: bool = False,
        expected_priority_sequence: int | None = None,
    ) -> Decision:
        if action == DecisionAction.EDIT:
            raise ValueError("use edit() for requirement changes")
        if not actor_id.strip():
            raise ValueError("a reviewer ID is required")
        if not rationale.strip():
            raise ValueError("a review rationale is required")
        if action == DecisionAction.APPROVE and not uncertainty_acknowledged:
            raise ValueError("approval requires explicit acknowledgement of unresolved evidence and policy limits")
        decision, _ = self.database.atomic_review(
            requirement_id=requirement_id,
            expected_revision=expected_revision,
            action=action,
            rationale=rationale.strip(),
            actor_id=actor_id,
            role=role,
            request_id=request_id,
            uncertainty_acknowledged=uncertainty_acknowledged,
            expected_priority_sequence=expected_priority_sequence,
        )
        return decision

    def edit(
        self,
        *,
        requirement_id: str,
        expected_revision: int,
        changes: dict[str, Any],
        rationale: str,
        actor_id: str,
        request_id: str,
        role: str = "demo_pm",
    ) -> tuple[Decision, RequirementRevision]:
        if not actor_id.strip():
            raise ValueError("a reviewer ID is required")
        if not rationale.strip():
            raise ValueError("an edit rationale is required")
        unsupported = set(changes) - self.EDITABLE_FIELDS
        if unsupported:
            raise ValueError(f"unsupported edit fields: {sorted(unsupported)}")
        if not changes:
            raise ValueError("at least one edited field is required")
        current = self.database.requirement(requirement_id, expected_revision)
        actual_changes = {key for key, value in changes.items()
            if current.model_dump(mode="python")[key] != value}
        payload = current.model_dump(mode="python")
        payload.update(changes)
        payload.update(
            {
                "revision": current.revision + 1,
                "supersedes_revision": current.revision,
                "lifecycle_status": "needs_review",
                "created_by": actor_id,
                "created_at": utc_now(),
            }
        )
        edited = RequirementRevision.model_validate(payload)
        decision, new_revision = self.database.atomic_review(
            requirement_id=requirement_id,
            expected_revision=expected_revision,
            action=DecisionAction.EDIT,
            rationale=rationale.strip(),
            actor_id=actor_id,
            role=role,
            request_id=request_id,
            edited_revision=edited,
        )
        assert new_revision is not None
        if self.database.latest_score(requirement_id, new_revision.revision) is not None:
            # A replayed edit request returns the recorded revision and score,
            # including its original scoring date, instead of recalculating.
            return decision, new_revision
        previous_score = self.database.latest_score(requirement_id, expected_revision)
        if previous_score and actual_changes <= {"title"}:
            copied_score = previous_score.model_copy(
                update={
                    "score_snapshot_id": stable_id(
                        "score", previous_score.score_snapshot_id, str(new_revision.revision)
                    ),
                    "requirement_revision": new_revision.revision,
                    "assumptions": [
                        *previous_score.assumptions,
                        "Only the display title changed; recorded criterion inputs were carried forward.",
                    ],
                }
            )
            self.database.persist_score(
                copied_score,
                request_id=f"{request_id}:score-recalculation",
            )
        elif previous_score and current.canonical_provenance:
            # An edited canonical revision must be reassessable without copying
            # an authored impact judgment onto a changed customer outcome. The
            # frozen corpus remains the input; all links require fresh human
            # entailment review for the new revision.
            from .canonical import build_score

            supporting = [ref.provenance["source_record"] for ref in new_revision.evidence_references
                          if ref.role == "supports" and ref.provenance.get("source_record")]
            opposing = [ref.provenance["source_record"] for ref in new_revision.evidence_references
                        if ref.role == "opposes" and ref.provenance.get("source_record")]
            recalculated = build_score(
                new_revision, supporting, opposing,
                run_id=f"edit-reassessment:{request_id}",
                corpus_hash=previous_score.corpus_manifest_hash, today=utc_now().date(),
            )
            recalculated = recalculated.model_copy(update={"assumptions": [
                *new_revision.assumptions,
                "Semantic edit invalidated the authored customer-impact input. Existing links are "
                "unreviewed candidates for this new revision; challenge them before commitment.",
            ]})
            self.database.persist_score(recalculated, request_id=f"{request_id}:score-recalculation")
        return decision, new_revision
