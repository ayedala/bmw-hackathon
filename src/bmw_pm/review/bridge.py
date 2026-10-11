"""Local JSON/NDJSON adapter so the web frontend can reach the review service.

The web app held PM decisions in browser storage, which made the overlay the
authority: a decision survived only in one browser, carried no audit event, and
could not be contradicted by a stale-revision check. This bridge moves that
authority back to :class:`~bmw_pm.review.service.ReviewService`.

It deliberately contains no review logic of its own. Validation, revision
conflicts, idempotency and audit all stay in the service and the database; this
module only parses a request, calls the service and serialises the result. The
frontend gets a typed error code for each failure so it can tell "the backend
is not configured" apart from "someone else already edited this", instead of
treating every failure as a reason to fall back to local state.

Protocol matches ``bmw_pm.advisor.bridge``: JSON payload on stdin, action as
argv[1], NDJSON events on stdout.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import Field, ValidationError

from ..contracts import Contract, DecisionAction, PolicyVersion
from ..decision.readiness import assess_readiness
from ..pipeline import load_json
from ..storage import Database
from ..storage.config import StorageError, database_target
from ..storage.database import RevisionConflict, WorkflowError
from .service import ReviewService
from .canonical import canonical_review_details, canonical_view, import_canonical
from .challenge import ChallengeService

#: Repository root, three levels up from this file (src/bmw_pm/review/).
ROOT = Path(__file__).resolve().parents[3]

#: The policy the web app scores with. Readiness needs one, and the database
#: does not store policies, so it is loaded from config like the CLI does.
DEFAULT_POLICY_PATH = "configs/exploratory_equal_v1.json"

#: Error codes the frontend branches on. Anything unexpected is "internal", and
#: the frontend must not treat any of these as permission to use local state as
#: the authority.
ErrorCode = Literal[
    "backend_unavailable",
    "requirement_not_found",
    "stale_revision",
    "request_conflict",
    "invalid_request",
    "internal",
]


class DecideRequest(Contract):
    requirement_id: str = Field(min_length=1)
    expected_revision: int = Field(ge=1)
    action: Literal["approve", "reject", "defer", "challenge"]
    rationale: str = Field(min_length=1)
    actor_id: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    role: str = "demo_pm"
    uncertainty_acknowledged: bool = False
    expected_priority_sequence: int | None = None


class EditRequest(Contract):
    requirement_id: str = Field(min_length=1)
    expected_revision: int = Field(ge=1)
    changes: dict[str, Any] = Field(min_length=1)
    rationale: str = Field(min_length=1)
    actor_id: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    role: str = "demo_pm"


class JudgeLinkRequest(Contract):
    requirement_id: str = Field(min_length=1)
    expected_revision: int = Field(ge=1)
    signal_id: str = Field(min_length=1)
    # Mirrors EvidenceLinkJudgment.verdict exactly; a wider set here would be
    # rejected by the contract anyway, and a narrower one would hide a verdict.
    verdict: Literal["supports", "does_not_support", "context_only"]
    rationale: str = Field(min_length=1)
    actor_id: str = Field(min_length=1)
    request_id: str = Field(min_length=1)


class StateRequest(Contract):
    """Read-only: what the backend currently holds for these requirements."""

    requirement_ids: list[str] = Field(default_factory=list)


class ImportCanonicalRequest(Contract):
    actor_id: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    rationale: str = Field(min_length=1)


class ChallengeRequest(Contract):
    requirement_id: str = Field(min_length=1)
    expected_revision: int = Field(ge=1)
    hypothesis: str = Field(min_length=1, max_length=8000)
    rationale: str = Field(min_length=1)
    actor_id: str = Field(min_length=1)
    request_id: str = Field(min_length=1)


class ReassessRequest(Contract):
    challenge_id: str = Field(min_length=1)
    requirement_id: str = Field(min_length=1)
    expected_revision: int = Field(ge=1)
    accept: bool
    rationale: str = Field(min_length=1)
    actor_id: str = Field(min_length=1)
    request_id: str = Field(min_length=1)


def _load_policy(policy_path: str | None = None) -> PolicyVersion | None:
    """Load the scoring policy, or None when it is not readable.

    Readiness is reported as unavailable rather than guessed when the policy is
    missing, because assess_readiness treats an unapproved policy as a blocker
    and inventing one would fake that gate.
    """
    candidate = ROOT / (policy_path or DEFAULT_POLICY_PATH)
    try:
        return PolicyVersion.model_validate(load_json(candidate))
    except (OSError, ValueError, ValidationError):
        return None


def _requirement_state(
    database: Database,
    requirement_id: str,
    policy: PolicyVersion | None = None,
) -> dict[str, Any]:
    """Authoritative state for one requirement, or why there is none."""
    try:
        requirement = database.latest_requirement(requirement_id)
    except KeyError:
        return {"requirement_id": requirement_id, "present": False,
                "detail": "No revision of this requirement exists in the review database."}

    score = database.latest_score(requirement_id, requirement.revision)
    judgments = database.latest_evidence_judgments(requirement_id, requirement.revision)
    decision = next(
        (item["decision"] for item in database.requirement_summaries()
         if item["requirement"].requirement_id == requirement_id),
        None,
    )
    if policy is None:
        readiness: dict[str, Any] | None = None
        readiness_note = (
            f"Readiness not evaluated: {DEFAULT_POLICY_PATH} could not be read, and "
            "an unapproved policy is itself a readiness blocker, so guessing one "
            "would fake the gate."
        )
    else:
        readiness = assess_readiness(requirement, score, policy).model_dump(mode="json")
        readiness_note = None
    quality = None
    if requirement.canonical_provenance:
        details = canonical_review_details(requirement, score, judgments)
        quality, readiness = details["quality"], details["readiness"]
        readiness_note = None
    history = database.replay_requirement(requirement_id)
    return {
        "requirement_id": requirement_id,
        "present": True,
        "revision": requirement.revision,
        "lifecycle_status": requirement.lifecycle_status,
        "feasibility": requirement.feasibility,
        "requirement": requirement.model_dump(mode="json"),
        "score": score.model_dump(mode="json") if score else None,
        "crps": score.coverage.get("crps") if score else None,
        "decision": decision.model_dump(mode="json") if decision else None,
        "judgments": {
            signal_id: judgment.model_dump(mode="json")
            for signal_id, judgment in judgments.items()
        },
        "readiness": readiness,
        "readiness_note": readiness_note,
        "quality": quality,
        "lineage": {"need_ids": requirement.need_ids, "finding_ids": requirement.finding_ids,
                    "evidence_ids": [ref.evidence_id for ref in requirement.evidence_references]},
        "revisions": history["revisions"],
        "decisions": history["decisions"],
        "evidence_judgments": history["evidence_judgments"],
        "score_snapshots": history.get("score_snapshots", []),
        "challenges": ChallengeService(database).history(requirement_id),
    }


def execute(
    action: str,
    payload: dict,
    database_path: str | Path,
    emit: Callable[[dict], None],
) -> None:
    """Dispatch one action. Every write goes through ReviewService."""
    if action == "canonical":
        if payload:
            raise ValueError("Canonical preview accepts no parameters")
        emit({"type": "canonical", **canonical_view(ROOT)})
        return
    database = Database(database_path)
    # The write paths initialize the schema themselves, the read paths do not,
    # so an unused database reported "no such table" as backend_unavailable.
    # An empty review database is empty, not broken.
    database.initialize()
    service = ReviewService(database)
    policy = _load_policy()

    def state(requirement_id: str) -> dict[str, Any]:
        return _requirement_state(database, requirement_id, policy)

    if action == "import_canonical":
        request = ImportCanonicalRequest.model_validate(payload)
        result = import_canonical(database, root=ROOT, **request.model_dump())
        emit({"type": "import_canonical", **result,
              "requirements": [state(rid) for rid in result["requirement_ids"]]})

    elif action == "state":
        request = StateRequest.model_validate(payload)
        ids = request.requirement_ids or [
            item["requirement"].requirement_id
            for item in database.requirement_summaries()
        ]
        emit({"type": "state",
              "requirements": [state(rid) for rid in ids]})

    elif action == "decide":
        request = DecideRequest.model_validate(payload)
        decision = service.decide(
            requirement_id=request.requirement_id,
            expected_revision=request.expected_revision,
            action=DecisionAction(request.action),
            rationale=request.rationale,
            actor_id=request.actor_id,
            request_id=request.request_id,
            role=request.role,
            uncertainty_acknowledged=request.uncertainty_acknowledged,
            expected_priority_sequence=request.expected_priority_sequence,
        )
        emit({"type": "decision", "decision": decision.model_dump(mode="json"),
              "state": state(request.requirement_id)})

    elif action == "edit":
        request = EditRequest.model_validate(payload)
        decision, revision = service.edit(
            requirement_id=request.requirement_id,
            expected_revision=request.expected_revision,
            changes=request.changes,
            rationale=request.rationale,
            actor_id=request.actor_id,
            request_id=request.request_id,
            role=request.role,
        )
        emit({"type": "edit", "decision": decision.model_dump(mode="json"),
              "revision": revision.model_dump(mode="json"),
              "state": state(request.requirement_id)})

    elif action == "judge_link":
        request = JudgeLinkRequest.model_validate(payload)
        judgment = service.judge_evidence_link(
            requirement_id=request.requirement_id,
            expected_revision=request.expected_revision,
            signal_id=request.signal_id,
            verdict=request.verdict,
            rationale=request.rationale,
            actor_id=request.actor_id,
            request_id=request.request_id,
        )
        emit({"type": "judgment", "judgment": judgment.model_dump(mode="json"),
              "state": state(request.requirement_id)})

    elif action == "challenge":
        request = ChallengeRequest.model_validate(payload)
        result = ChallengeService(database, root=ROOT).challenge(**request.model_dump())
        emit({"type": "challenge", "challenge": result, "state": state(request.requirement_id)})

    elif action == "reassess":
        request = ReassessRequest.model_validate(payload)
        result = ChallengeService(database, root=ROOT).reassess(**request.model_dump())
        emit({"type": "reassessment", "reassessment": result, "state": state(request.requirement_id)})

    elif action == "audit":
        valid, checkpoint = database.verify_audit_chain()
        emit({"type": "audit", "valid": valid, "checkpoint": checkpoint,
              "events": [event.model_dump(mode="json")
                         for event in database.audit_events()]})
    else:
        raise ValueError(f"Unsupported review operation: {action!r}")


def _error(emit: Callable[[dict], None], code: ErrorCode, message: str) -> None:
    emit({"type": "error", "code": code, "message": message})


def main() -> int:
    def emit(event: dict) -> None:
        print(json.dumps(event, ensure_ascii=False), flush=True)

    try:
        raw = sys.stdin.read(1048577)
        if len(raw) > 1048576:
            raise ValueError("The request is too large.")
        payload = json.loads(raw or "{}")
        execute(
            sys.argv[1] if len(sys.argv) > 1 else "state",
            payload,
            database_target(root=ROOT),
            emit,
        )
        return 0
    except ValidationError as exc:
        messages = [
            f"{'.'.join(str(part) for part in error['loc']) or 'request'}: {error['msg']}"
            for error in exc.errors(include_input=False, include_url=False)
        ]
        _error(emit, "invalid_request", "Check the review inputs. " + "; ".join(messages))
    except RevisionConflict as exc:
        # Stale-review protection. The frontend must refuse to apply the action
        # and reload, never silently keep a local overlay that disagrees.
        _error(emit, "stale_revision", str(exc))
    except WorkflowError as exc:
        _error(emit, "request_conflict", str(exc))
    except KeyError as exc:
        _error(emit, "requirement_not_found",
               f"Requirement {exc.args[0]!r} has no revision in the review database.")
    except StorageError as exc:
        _error(emit, "backend_unavailable", str(exc))
    except ValueError as exc:
        _error(emit, "invalid_request", str(exc))
    except (OSError, sqlite3.Error) as exc:
        _error(emit, "backend_unavailable",
               f"The review database could not be opened: {exc}")
    except Exception:  # noqa: BLE001 - last resort, details stay in the log
        _error(emit, "internal", "The review action could not be completed.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
