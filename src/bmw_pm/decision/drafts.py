"""Immutable proposal snapshots; synthesis never writes a decision or PM priority."""
import json
from pathlib import Path

from ..contracts import SuccessorDraft, PriorityPolicy
from ..utils import content_hash
from ..storage import WorkflowError

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_POLICY = PriorityPolicy(impact=.35, evidence=.25, relevance=.25, uncertainty=.15)


def generate_draft(database, requirement, proposals):
    from .planning import proposal_for, anchor_records
    proposal = proposal_for(database, requirement, proposals)
    if proposal is None:
        return None
    records = anchor_records(database, proposal)
    public = json.loads((ROOT / "configs/planning_public_context.json").read_text(encoding="utf-8"))
    external = []
    if proposal.domain in {"charging_and_range", "noise_and_refinement", "ride_and_comfort", "controls_usability"}:
        for entry in public:
            if "iea.org" in entry["url"] and proposal.domain != "charging_and_range":
                continue
            external.append({**entry, "checked_on": "2026-10-10",
                "status": "Primary page checked; authored contextual summary, not a quotation or US customer-demand finding."})
    payload = dict(requirement_id=requirement.requirement_id, base_revision=requirement.revision,
        recipe_version="successor_us_g60_v2", proposal=proposal,
        quoted_records=records, context_evidence=requirement.cross_channel_evidence, external_context=external,
        unknowns=list(dict.fromkeys([*requirement.missing_evidence,
            "Customer reports are not independently verified; theme/polarity and entailment need human review.",
            "No confirmed respondent counts, baseline task performance, future market mix or feasibility supplied.",
            "BEVE is preserved as supplied; its meaning and any BEV equivalence need data-owner review.",
            "Study scales/sample sizes are missing; equipment is German July 2026 context, not confirmed US availability; sales combine G60/G68 without powertrain split.",
            "No usable video transcripts in the available research run; no YouTube findings are inferred."])),
        priority_policy=DEFAULT_POLICY,
        priority_explanations={
            "impact": f"AI-suggested {proposal.factors.impact}/4 for proposed value: {proposal.value} Not measured severity or prevalence.",
            "evidence": f"AI-suggested 2/4: {len(records)} resolved anchor records; meaning, independence and representativeness are unreviewed.",
            "relevance": "AI-suggested 3/4: G60 US anchors match the chosen demonstration; not a market-demand estimate.",
            "uncertainty": f"AI-suggested {proposal.factors.uncertainty}/4; higher means more risk. Unresolved trade-off: {proposal.contrary}"})
    draft = SuccessorDraft(draft_id="pending", **payload)
    draft = draft.model_copy(update={"draft_id": "draft_" + content_hash(draft.model_dump(mode="json", exclude={"draft_id"}))})
    with database.connect() as connection:
        connection.executescript('''
            CREATE TABLE IF NOT EXISTS successor_drafts (
                draft_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL, payload_hash TEXT NOT NULL);
            CREATE TRIGGER IF NOT EXISTS successor_drafts_no_update BEFORE UPDATE ON successor_drafts
                BEGIN SELECT RAISE(ABORT, 'immutable successor draft'); END;
            CREATE TRIGGER IF NOT EXISTS successor_drafts_no_delete BEFORE DELETE ON successor_drafts
                BEGIN SELECT RAISE(ABORT, 'immutable successor draft'); END;
        ''')
        connection.execute("BEGIN IMMEDIATE")
        exists = connection.execute("SELECT payload_hash FROM successor_drafts WHERE draft_id=?", (draft.draft_id,)).fetchone()
        if not exists:
            connection.execute("INSERT INTO successor_drafts VALUES (?,?,?)", (draft.draft_id, draft.model_dump_json(), content_hash(draft)))
            database._append_audit(connection, actor_id="draft-synthesis", actor_type="pipeline",
                action="generate_successor_draft", object_type="successor_draft", object_id=draft.draft_id,
                object_revision=requirement.revision, before_hash=None, after_hash=content_hash(draft),
                reason="Evidence-linked interpretation and scenario; not a human decision or priority.",
                request_id=draft.draft_id, result="success")
        elif exists[0] != content_hash(draft):
            raise WorkflowError("Successor draft hash mismatch")
        connection.commit()
    return draft


def read_draft(database, draft_id):
    with database.connect() as connection:
        row = connection.execute("SELECT payload_json,payload_hash FROM successor_drafts WHERE draft_id=?", (draft_id,)).fetchone()
    if row is None:
        raise KeyError(draft_id)
    if content_hash(json.loads(row[0])) != row[1]:
        raise WorkflowError("Successor draft hash mismatch")
    return SuccessorDraft.model_validate_json(row[0])


def adopt_draft(database, draft, *, actor_id, rationale, request_id):
    """Explicit human edit creates a reviewable revision; it does not approve it."""
    from ..review import ReviewService
    stored = read_draft(database, draft.draft_id)
    if stored != draft:
        raise WorkflowError("Draft does not match immutable snapshot")
    p = draft.proposal
    return ReviewService(database).edit(requirement_id=draft.requirement_id,
        expected_revision=draft.base_revision, actor_id=actor_id, rationale=rationale, request_id=request_id,
        changes={"title": p.title, "customer_outcome": p.outcome,
            "successor_draft_id": draft.draft_id,
            "assumptions": ["Forward-looking scenario (not observed): " + p.future_assumption,
                "AI interpretation (not quotation): " + p.interpretation,
                "Conflicting/preservation evidence to review: " + p.contrary],
            "acceptance_proposal": {"method": p.validation, "target": None, "unit": None}})


def validate_successor_drafts(database, requirements):
    """Check immutable snapshot identities, exact records and adopted references."""
    from ..contracts import FeedbackRecord
    errors = []
    with database.connect() as connection:
        exists = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='successor_drafts'").fetchone()
        ids = [row[0] for row in connection.execute("SELECT draft_id FROM successor_drafts")] if exists else []
        for draft_id in ids:
            try:
                draft = read_draft(database, draft_id)
                if draft_id != "draft_" + content_hash(draft.model_dump(mode="json", exclude={"draft_id"})):
                    errors.append(f"{draft_id}: content identity mismatch")
                if set(draft.proposal.anchor_ids) != {r.source_record_id for r in draft.quoted_records}:
                    errors.append(f"{draft_id}: anchor set mismatch")
                for record in draft.quoted_records:
                    row = connection.execute("SELECT payload_json,payload_hash FROM feedback_records WHERE record_id=?",(record.record_id,)).fetchone()
                    if not row or content_hash(json.loads(row[0])) != row[1] or FeedbackRecord.model_validate_json(row[0]) != record:
                        errors.append(f"{draft_id}: quoted source record mismatch")
                    if record.model_code != "G60" or record.country != "US":
                        errors.append(f"{draft_id}: unsupported source scope")
            except (ValueError, WorkflowError, KeyError) as error:
                errors.append(f"{draft_id}: {error}")
        for req in requirements:
            if req.successor_draft_id:
                if req.successor_draft_id not in ids:
                    errors.append(f"{req.requirement_id}: missing adopted draft")
                else:
                    try:
                        draft = read_draft(database, req.successor_draft_id)
                        if draft.requirement_id != req.requirement_id or draft.base_revision >= req.revision:
                            errors.append(f"{req.requirement_id}: adopted draft revision mismatch")
                    except (ValueError, WorkflowError, KeyError) as error:
                        errors.append(f"{req.requirement_id}: {error}")
    return errors
