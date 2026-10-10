"""Explicit successor hypotheses and immutable, human-controlled priorities."""
from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from ..contracts import FeedbackRecord, PriorityAssessment, PriorityFactors, PriorityPolicy, SuccessorProposal, PlanningCriterion, Signal
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
    if requirement.scope.models != ["G60"] or requirement.scope.countries != ["US"]:
        return None
    ids = [link.signal_id for link in requirement.evidence_links]
    if not ids:
        return None
    with database.connect() as connection:
        domains = {row[0] for row in connection.execute(
            "SELECT DISTINCT need_domain FROM signals WHERE signal_id IN (" + ",".join("?" for _ in ids) + ")", ids)}
    if len(domains) != 1:
        return None  # ambiguous consolidation needs explicit domain review
    for domain in sorted(domains):
        proposal = proposals.get(domain)
        if proposal and set(proposal.anchor_ids) <= {r.source_record_id for r in anchor_records(database, proposal)}:
            return proposal
    return None


def criteria_score(criteria):
    criteria = [PlanningCriterion.model_validate(x) for x in criteria]
    if not criteria or len({x.name.strip().casefold() for x in criteria}) != len(criteria):
        raise ValueError("Supply unique, nonempty priority criteria")
    if any(not x.name.strip() or not x.explanation.strip() for x in criteria):
        raise ValueError("Each criterion needs a name and explanation")
    total = sum(x.weight for x in criteria)
    if total <= 0:
        raise ValueError("At least one criterion weight must be positive")
    return round(25 * sum((4-x.rating if x.direction == "risk" else x.rating)*x.weight for x in criteria)/total, 4)


def anchor_records(database, proposal):
    records = []
    with database.connect() as connection:
        for source_id in proposal.anchor_ids:
            rows = connection.execute("SELECT payload_json,payload_hash FROM feedback_records WHERE source_record_id=? AND model_code='G60' AND country='US'", (source_id,)).fetchall()
            for row in rows:
                if content_hash(json.loads(row[0])) != row[1]:
                    raise WorkflowError("Feedback anchor payload hash mismatch")
                record = FeedbackRecord.model_validate_json(row[0])
                source = connection.execute("SELECT sha256 FROM sources WHERE source_id=?", (record.source_id,)).fetchone()
                if not source or not record.row_locators or any(loc.source_hash != source[0] or loc.source_id != record.source_id for loc in record.row_locators):
                    raise WorkflowError("Feedback anchor source locator mismatch")
                records.append(record)
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
            if content_hash(json.loads(row["payload_json"])) != row["payload_hash"]:
                raise WorkflowError("Priority payload hash mismatch")
            result.append(item)
        return result

    def save(self, *, requirement_id, expected_revision, expected_sequence, factors, policy,
             actor_id, rationale, request_id, criteria=None, rank_override=None, priority_confirmed=False) -> PriorityAssessment:
        if not rationale.strip() or not actor_id.strip():
            raise ValueError("Reviewer ID and priority rationale are required")
        factors = PriorityFactors.model_validate(factors)
        policy = PriorityPolicy.model_validate(policy)
        criteria = [PlanningCriterion.model_validate(x) for x in (criteria or [])]
        score = criteria_score(criteria) if criteria else priority_score(factors, policy)
        if rank_override is not None and (isinstance(rank_override, bool) or not isinstance(rank_override, int) or rank_override < 1):
            raise ValueError("Manual rank must be a positive integer")
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            old = connection.execute("SELECT payload_json FROM priority_assessments WHERE request_id=?", (request_id,)).fetchone()
            if old:
                item = PriorityAssessment.model_validate_json(old[0])
                if (item.requirement_id, item.requirement_revision, item.factors, item.policy, item.actor_id, item.rationale) != (requirement_id, expected_revision, factors, policy, actor_id.strip(), rationale.strip()):
                    raise WorkflowError("Request ID reused with a different priority payload")
                if (item.criteria, item.rank_override, item.priority_confirmed) != (criteria, rank_override, priority_confirmed):
                    raise WorkflowError("Request ID reused with a different priority payload")
                connection.rollback()
                return item
            latest = connection.execute("SELECT MAX(revision) FROM requirement_revisions WHERE requirement_id=?", (requirement_id,)).fetchone()[0]
            if latest != expected_revision:
                raise RevisionConflict("Requirement changed; reload before setting priority")
            sequence = connection.execute("SELECT COALESCE(MAX(sequence),0) FROM priority_assessments WHERE requirement_id=? AND requirement_revision=?", (requirement_id, expected_revision)).fetchone()[0]
            if sequence != expected_sequence:
                raise RevisionConflict("Priority changed in another session; reload")
            item = PriorityAssessment(input_origin="explicit_pm", assessment_id=f"priority_{uuid4().hex}", requirement_id=requirement_id,
                requirement_revision=expected_revision, sequence=sequence + 1, factors=factors, policy=policy,
                score=score, criteria=criteria, rank_override=rank_override, priority_confirmed=priority_confirmed,
                interpretation=("Custom criteria are the sole scoring inputs; factors/policy are compatibility placeholders, not additional PM ratings. " if criteria else "Four-factor assessment under the recorded policy. ") + "Declared PM judgement, not measured customer prevalence or calibrated confidence.",
                actor_id=actor_id.strip(), rationale=rationale.strip(),
                recorded_at=utc_now(), request_id=request_id)
            connection.execute("INSERT INTO priority_assessments VALUES (?,?,?,?,?,?,?)", (item.assessment_id,
                requirement_id, expected_revision, item.sequence, request_id, item.model_dump_json(), content_hash(item)))
            self.database._append_audit(connection, actor_id=actor_id.strip(), actor_type="demo_pm",
                action="set_priority", object_type="requirement", object_id=requirement_id,
                object_revision=expected_revision, before_hash=None, after_hash=content_hash(item),
                reason=rationale.strip(), request_id=request_id, result="success")
            connection.commit()
        return item


def planning_order(database, summaries, proposals, policy=None):
    """Same provisional ordering in UI and exports; never writes PM assessments."""
    from .drafts import generate_draft, read_draft
    service = PriorityService(database)
    decorated = []
    for item in summaries:
        req = item["requirement"]
        current = [x for x in service.history(req.requirement_id)
            if x.requirement_revision == req.revision and x.input_origin == "explicit_pm"]
        latest = current[-1] if current else None
        draft = read_draft(database, req.successor_draft_id) if req.successor_draft_id else generate_draft(database, req, proposals)
        score = (latest.score if latest and (latest.criteria or policy is None) else priority_score(latest.factors, policy)) if latest else (priority_score(draft.proposal.factors, policy or draft.priority_policy) if draft else None)
        decorated.append((score, item, latest, draft))
    return sorted(decorated, key=lambda x: ((x[2].rank_override if x[2] and x[2].rank_override else float("inf")),
        -(x[0] if x[0] is not None else -1), x[1]["requirement"].requirement_id))


def decision_brief(database, summaries, proposals, policy: PriorityPolicy | None) -> str:
    models = sorted({model for item in summaries for model in item["requirement"].scope.models})
    markets = sorted({market for item in summaries for market in item["requirement"].scope.countries})
    scopes = [f"vehicles {', '.join(models) or 'unspecified'}; markets {', '.join(markets) or 'unspecified'}"]
    lines = ["# BMW product decision brief", "Scopes: " + "; ".join(scopes),
        "AI interpretations, future assumptions and AI draft priorities are not source facts or PM decisions. Source quotations establish what was reported; their meaning remains reviewable.",
        "No future launch date or validation target has been established by this report."]
    lines += ["Display order below is provisional, not approved. Manual PM ranks sort first, then score. Different custom policies may not be comparable.",
        "Unsaved what-if preview policy (not PM confirmation): " + str(policy.model_dump() if policy else None)]
    service = PriorityService(database)
    with database.connect() as connection:
        signals = {row[0]: Signal.model_validate_json(row[1]) for row in connection.execute("SELECT signal_id,payload_json FROM signals")}
    for position,(preview_score,item,assessment,draft) in enumerate(planning_order(database,summaries,proposals,policy),1):
        req = item["requirement"]
        history = service.history(req.requirement_id)
        lines += [f"## Display position {position}: {req.title} / revision {req.revision}",
            "Stored wording (requires human evidence review): " + req.customer_outcome,
            f"Recorded supporting feedback IDs: {req.support_count}/{req.denominator_feedback_records}; preservation IDs: {req.counter_count}. These are unreviewed classifications, not people or measured impact.",
            "Current PM priority: " + (f"{assessment.score}; confirmed={assessment.priority_confirmed}; manual rank={assessment.rank_override}" if assessment else "Unknown; explicit PM input required."),
            "Provisional display score (AI draft or unsaved preview, not priority confirmation): " + str(preview_score),
            "Historical assumptions (not verified facts): " + str(req.assumptions),
            "Missing evidence: " + str(req.missing_evidence)]
        if draft:
            p = draft.proposal
            lines += ["### Future-facing draft — not approved", p.outcome,
                "Proposed customer value: " + p.value,
                "AI interpretation (not quotation): " + p.interpretation,
                "Future assumption (not fact): " + p.future_assumption,
                "Conflicting evidence / interpretation to review: " + p.contrary,
                "Unknowns: " + "; ".join(draft.unknowns),
                "Proposed validation: " + p.validation,
                "AI ratings /4: " + str(p.factors.model_dump()) + "; AI weights: " + str(draft.priority_policy.model_dump()),
                f"AI provisional score: {priority_score(draft.proposal.factors, draft.priority_policy)} /100. Not a PM-approved priority.",
                "Snapshot provenance (includes quoted_records, future_assumption and authored context): " + draft.model_dump_json()]
            for record in draft.quoted_records:
                lines += [f"Exact redacted source record {record.source_record_id} (supplied powertrain {record.powertrain_raw}):", "> " + record.redacted_text.replace("\n", "\n> "),
                    "Source locators: " + json.dumps([x.model_dump(mode="json") for x in record.row_locators],ensure_ascii=False)]
        decision = item.get("decision")
        lines += ["Human decision on this stored revision: " + (f"{decision.action.value}; reviewer {decision.actor_id}; rationale: {decision.rationale}; priority snapshot {decision.priority_assessment_id}" if decision else "None — not approved.")]
        for link in req.evidence_links:
            signal = signals[link.signal_id]
            for span in signal.evidence_spans:
                lines += [f"Source quotation [{link.role}; interpretation unreviewed]:", "> " + span.text.replace("\n", "\n> "), str(span.locator.model_dump(mode="json"))]
        lines += ["Cross-channel source context (not automatically corroboration): " + json.dumps([x.model_dump(mode="json") for x in req.cross_channel_evidence],ensure_ascii=False),
            "Decision and revision history: " + json.dumps(database.replay_requirement(req.requirement_id),ensure_ascii=False),
            "PM assessment history (legacy entries are unconfirmed): " + json.dumps([x.model_dump(mode="json") for x in history],ensure_ascii=False)]
    return "\n\n".join(lines)
