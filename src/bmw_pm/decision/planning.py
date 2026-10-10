"""Explicit successor hypotheses and immutable, human-controlled priorities."""
from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from ..contracts import FeedbackRecord, PriorityAssessment, PriorityFactors, PriorityPolicy, SuccessorProposal
from ..storage import Database, RevisionConflict, WorkflowError
from ..utils import content_hash, utc_now


def priority_score(factors: PriorityFactors, policy: PriorityPolicy) -> float:
    """0–100 weighted judgement; uncertainty is reversed, never confidence."""
    return round(25 * (factors.impact * policy.impact + factors.evidence * policy.evidence
        + factors.relevance * policy.relevance + (4 - factors.uncertainty) * policy.uncertainty), 4)


def load_proposals(path: str | Path) -> dict[str, SuccessorProposal]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return {item["domain"]: SuccessorProposal.model_validate(item) for item in payload["proposals"]}


def proposal_for(database, requirement, proposals):
    # Never transfer the curated US 5 Series hypotheses to a different vehicle/market.
    if requirement.scope.models != ["G60"] or requirement.scope.countries != ["US"]:
        return None
    ids = requirement.supporting_signal_ids or requirement.counter_signal_ids
    if not ids:
        return None
    proposal = proposals.get(database.signal(ids[0]).need_domain)
    if proposal and {r.source_record_id for r in anchor_records(database, proposal)} == set(proposal.anchor_ids):
        return proposal
    return None


def anchor_records(database, proposal):
    records = []
    with database.connect() as connection:
        for source_id in proposal.anchor_ids:
            rows = connection.execute("SELECT payload_json FROM feedback_records WHERE source_record_id=? AND model_code='G60' AND country='US'", (source_id,)).fetchall()
            records.extend(FeedbackRecord.model_validate_json(row[0]) for row in rows)
    return records


class PriorityService:
    def __init__(self, database: Database):
        self.database = database

    def history(self, requirement_id: str) -> list[PriorityAssessment]:
        with self.database.connect() as connection:
            rows = connection.execute("SELECT payload_json,payload_hash FROM priority_assessments WHERE requirement_id=? ORDER BY rowid", (requirement_id,)).fetchall()
        result = []
        for row in rows:
            item = PriorityAssessment.model_validate_json(row["payload_json"])
            if content_hash(item) != row["payload_hash"]:
                raise WorkflowError("Priority payload hash mismatch")
            result.append(item)
        return result

    def save(self, *, requirement_id, expected_revision, expected_sequence, factors, policy,
             actor_id, rationale, request_id) -> PriorityAssessment:
        if not rationale.strip() or not actor_id.strip():
            raise ValueError("Reviewer ID and priority rationale are required")
        factors = PriorityFactors.model_validate(factors)
        policy = PriorityPolicy.model_validate(policy)
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            old = connection.execute("SELECT payload_json FROM priority_assessments WHERE request_id=?", (request_id,)).fetchone()
            if old:
                item = PriorityAssessment.model_validate_json(old[0])
                if (item.requirement_id, item.requirement_revision, item.factors, item.policy, item.actor_id, item.rationale) != (requirement_id, expected_revision, factors, policy, actor_id.strip(), rationale.strip()):
                    raise WorkflowError("Request ID reused with a different priority payload")
                connection.rollback()
                return item
            latest = connection.execute("SELECT MAX(revision) FROM requirement_revisions WHERE requirement_id=?", (requirement_id,)).fetchone()[0]
            if latest != expected_revision:
                raise RevisionConflict("Requirement changed; reload before setting priority")
            sequence = connection.execute("SELECT COALESCE(MAX(sequence),0) FROM priority_assessments WHERE requirement_id=? AND requirement_revision=?", (requirement_id, expected_revision)).fetchone()[0]
            if sequence != expected_sequence:
                raise RevisionConflict("Priority changed in another session; reload")
            item = PriorityAssessment(assessment_id=f"priority_{uuid4().hex}", requirement_id=requirement_id,
                requirement_revision=expected_revision, sequence=sequence + 1, factors=factors, policy=policy,
                score=priority_score(factors, policy), actor_id=actor_id.strip(), rationale=rationale.strip(),
                recorded_at=utc_now(), request_id=request_id)
            connection.execute("INSERT INTO priority_assessments VALUES (?,?,?,?,?,?,?)", (item.assessment_id,
                requirement_id, expected_revision, item.sequence, request_id, item.model_dump_json(), content_hash(item)))
            self.database._append_audit(connection, actor_id=actor_id.strip(), actor_type="demo_pm",
                action="set_priority", object_type="requirement", object_id=requirement_id,
                object_revision=expected_revision, before_hash=None, after_hash=content_hash(item),
                reason=rationale.strip(), request_id=request_id, result="success")
            connection.commit()
        return item


def decision_brief(database, summaries, proposals, policy: PriorityPolicy) -> str:
    lines = ["# BMW successor decision brief", "", "Planning scenario: US 5 Series, 2029–2031 (assumed horizon, not a BMW launch commitment).",
        "Drafts and PM judgements are separate from observed feedback. No measured model accuracy or representative prevalence is claimed.", "",
        "Priority = 25 × [impact × weight + evidence × weight + relevance × weight + (4 − uncertainty) × weight].",
        f"Comparison weights: {policy.model_dump()}. These are declared preferences, not an approved BMW policy.", ""]
    service = PriorityService(database)
    for item in summaries:
        req = item["requirement"]
        proposal = proposal_for(database, req, proposals)
        history = service.history(req.requirement_id)
        current = [p for p in history if p.requirement_revision == req.revision]
        assessment = current[-1] if current else None
        lines += [f"## {req.title} · r{req.revision}", req.customer_outcome,
            f"Scope: {req.scope.model_dump()}", f"Supporting records: {req.support_count}/{req.denominator_feedback_records}; preservation: {req.counter_count}. Counts refer to the broad extracted theme, not each specific draft feature."]
        if proposal:
            lines += [f"Proposed successor draft: {proposal.outcome}", f"Interpretation: {proposal.interpretation}",
                f"Customer value: {proposal.value}", f"Future assumption: {proposal.future_assumption}",
                f"Contrary evidence / trade-off: {proposal.contrary}", f"Validation proposal: {proposal.validation}", f"Revisit when: {proposal.review_trigger}"]
            for record in anchor_records(database, proposal):
                lines += [f"Anchor {record.source_record_id} ({record.raw_text_ref}; SHA-256 {record.row_locators[0].source_hash}): {record.redacted_text}"]
        factors = assessment.factors if assessment else proposal.factors if proposal else None
        if factors:
            lines += [f"Comparable priority under current weights: {priority_score(factors, policy)}; factors: {factors.model_dump()}; basis: {'saved PM judgement' if assessment else 'illustrative seed judgement'}."]
        if assessment:
            lines += [f"Saved assessment {assessment.assessment_id}: {assessment.score}; weights {assessment.policy.model_dump()}; reviewer {assessment.actor_id}; rationale: {assessment.rationale}"]
        lines += [f"Assumptions: {req.assumptions}", f"Missing evidence: {req.missing_evidence}",
            f"Cross-channel evidence: {json.dumps([x.model_dump(mode='json') for x in req.cross_channel_evidence], ensure_ascii=False)}",
            f"Requirement evidence links: {json.dumps([x.model_dump(mode='json') for x in req.evidence_links], ensure_ascii=False)}",
            f"Decision/revision history: {json.dumps(database.replay_requirement(req.requirement_id), ensure_ascii=False)}",
            f"Priority history: {json.dumps([x.model_dump(mode='json') for x in history], ensure_ascii=False)}", ""]
    return "\n\n".join(lines)
