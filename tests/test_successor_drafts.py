"""Synthetic boundary tests, never BMW feedback or real PM approvals."""
import json
import sqlite3
import pytest
from bmw_pm.contracts import DecisionAction, PriorityFactors
from bmw_pm.decision.planning import load_proposals, PriorityService, criteria_score, decision_brief, planning_order
from bmw_pm.decision.drafts import generate_draft, read_draft, adopt_draft, DEFAULT_POLICY, validate_successor_drafts
from bmw_pm.review import ReviewService
from bmw_pm.storage import WorkflowError, RevisionConflict
from bmw_pm.utils import content_hash
from test_fusion import database, run, saved_run


def fixture(tmp_path):
    db=database(tmp_path)
    run(db)
    req=db.requirement_summaries()[0]["requirement"]
    p=load_proposals("configs/successor_proposals_v1.json")["controls_usability"].model_copy(update={
        "anchor_ids":["G60-001"],"interpretation":"Synthetic interpretation, not source text.",
        "future_assumption":"Synthetic future scenario, not observed data.","contrary":"Synthetic conflicting design consideration."})
    return db,req,{p.domain:p}


def test_draft_generation_is_idempotent_immutable_and_not_a_decision(tmp_path):
    db,req,proposals=fixture(tmp_path)
    draft=generate_draft(db,req,proposals)
    assert draft==generate_draft(db,req,proposals)==read_draft(db,draft.draft_id)
    assert draft.quoted_records[0].redacted_text=="The touchscreen is hard to use."
    assert draft.proposal.interpretation not in draft.quoted_records[0].redacted_text
    assert not db.replay_requirement(req.requirement_id)["decisions"]
    assert not PriorityService(db).history(req.requirement_id)
    assert db.latest_requirement(req.requirement_id).revision==1
    assert validate_successor_drafts(db,[req])==[]
    with db.connect() as conn:
        with pytest.raises(sqlite3.IntegrityError,match="immutable"):
            conn.execute("DELETE FROM successor_drafts")
    bad=proposals["controls_usability"].model_copy(update={"anchor_ids":["nonexistent"]})
    assert generate_draft(db,req,{bad.domain:bad}) is None
    with pytest.raises(ValueError):
        adopt_draft(db,draft,actor_id="",rationale="Synthetic",request_id="empty")
    brief=decision_brief(db,db.requirement_summaries(),proposals,None)
    for label in ("AI provisional score", "future_assumption", "quoted_records", "Unknown; explicit PM input required"):
        assert label in brief


def test_raw_beve_preserved_and_ambiguity_flagged(tmp_path):
    db,req,proposals=fixture(tmp_path)
    with db.connect() as conn:
        row=conn.execute("SELECT record_id,payload_json FROM feedback_records").fetchone()
        payload=json.loads(row[1]);payload.update(powertrain_raw="BEVE",powertrain="BEVE",powertrain_mapping_status="unknown")
        conn.execute("UPDATE feedback_records SET payload_json=?,payload_hash=? WHERE record_id=?",(json.dumps(payload),content_hash(payload),row[0]))
        conn.commit()
    draft=generate_draft(db,req,proposals)
    assert draft.quoted_records[0].powertrain_raw=="BEVE"
    assert any("BEVE" in x and "review" in x for x in draft.unknowns)
    assert draft.quoted_records[0].powertrain=="BEVE"


def test_explicit_adoption_priority_confirmation_and_decision_trace(tmp_path):
    db,req,proposals=fixture(tmp_path)
    draft=generate_draft(db,req,proposals)
    args=dict(actor_id="synthetic-reviewer",rationale="Synthetic concept-testing judgement",request_id="adopt")
    decision,revision=adopt_draft(db,draft,**args)
    assert revision.revision==2 and revision.successor_draft_id==draft.draft_id
    assert adopt_draft(db,draft,**args)[1]==revision  # edit retry is safe
    service=PriorityService(db)
    custom=[dict(name="Customer task value",rating=4,weight=3,direction="benefit",explanation="Synthetic judgement"),
        dict(name="Uncertainty",rating=2,weight=1,direction="risk",explanation="Unreviewed design")]
    save=dict(requirement_id=req.requirement_id,expected_revision=2,expected_sequence=0,
        factors=PriorityFactors(impact=0,evidence=0,relevance=0,uncertainty=4),policy=DEFAULT_POLICY,
        criteria=custom,actor_id=args["actor_id"],rationale=args["rationale"],request_id="priority",rank_override=2)
    first=service.save(**save)
    assert first.score==87.5 and not first.priority_confirmed
    assert service.save(**save)==first
    with pytest.raises(RevisionConflict,match="Priority changed"):
        ReviewService(db).decide(requirement_id=req.requirement_id,expected_revision=2,
            action=DecisionAction.APPROVE,actor_id=args["actor_id"],rationale=args["rationale"],
            request_id="stale-priority",expected_priority_sequence=0,uncertainty_acknowledged=True)
    assert not [x for x in db.replay_requirement(req.requirement_id)["decisions"] if x["action"]=="approve"]
    with pytest.raises(WorkflowError,match="reused"):
        service.save(**{**save,"priority_confirmed":True})
    confirmed=service.save(**{**save,"expected_sequence":1,"request_id":"confirm","priority_confirmed":True})
    review=ReviewService(db).decide(requirement_id=req.requirement_id,expected_revision=2,
        action=DecisionAction.APPROVE,actor_id=args["actor_id"],rationale=args["rationale"],request_id="approve",uncertainty_acknowledged=True)
    assert review.priority_assessment_id==confirmed.assessment_id
    with pytest.raises(WorkflowError,match="reused"):
        ReviewService(db).decide(requirement_id=req.requirement_id,expected_revision=2,
            action=DecisionAction.REJECT,actor_id=args["actor_id"],rationale=args["rationale"],request_id="approve")
    assert db.requirement(req.requirement_id,1).successor_draft_id is None
    assert db.replay_requirement(req.requirement_id)["audit_valid"]
    # Regeneration with different evidence must not replace human-reviewed wording.
    run(db,youtube_runs=[saved_run(tmp_path/"new-video")])
    assert db.latest_requirement(req.requirement_id)==revision
    with pytest.raises(RevisionConflict):
        adopt_draft(db,draft,**{**args,"request_id":"stale"})


def test_invalid_anchor_hash_cannot_be_used_for_a_draft(tmp_path):
    db,req,proposals=fixture(tmp_path)
    with db.connect() as conn:
        conn.execute("UPDATE feedback_records SET payload_hash=?",("0"*64,))
        conn.commit()
    with pytest.raises(WorkflowError,match="hash mismatch"):
        generate_draft(db,req,proposals)


def test_draft_validation_detects_untrusted_inserted_payload(tmp_path):
    db,req,proposals=fixture(tmp_path)
    generate_draft(db,req,proposals)
    with db.connect() as conn:
        conn.execute("INSERT INTO successor_drafts VALUES (?,?,?)",("invalid","{}","0"*64))
        conn.commit()
    assert any("hash mismatch" in error for error in validate_successor_drafts(db,[req]))


def test_manual_rank_and_export_use_the_same_order(tmp_path):
    db,req,proposals=fixture(tmp_path)
    other=db.ensure_requirement(req.model_copy(update={"requirement_id":"req-other","title":"Other synthetic requirement"}),request_id="other",run_id="test")
    service=PriorityService(db)
    for requirement,rank in ((req,2),(other,1)):
        service.save(requirement_id=requirement.requirement_id,expected_revision=1,expected_sequence=0,
            factors=PriorityFactors(impact=1,evidence=1,relevance=1,uncertainty=3),policy=DEFAULT_POLICY,
            actor_id="synthetic-pm",rationale="Synthetic manual ordering",request_id="rank:"+requirement.requirement_id,rank_override=rank)
    summaries=db.requirement_summaries()
    ordered=planning_order(db,summaries,proposals)
    assert ordered[0][1]["requirement"].requirement_id==other.requirement_id
    assert not ordered[0][2].priority_confirmed
    brief=decision_brief(db,summaries,proposals,None)
    assert "Display position 1: Other synthetic requirement" in brief


@pytest.mark.parametrize("criteria",[[],[dict(name="x",rating=5,weight=1,explanation="x")],
    [dict(name="x",rating=2,weight=0,explanation="x")],
    [dict(name="x",rating=2,weight=float("nan"),explanation="x")],
    [dict(name="x",rating=2,weight=1,explanation="x")]*2])
def test_invalid_custom_priorities_cannot_be_saved(criteria):
    with pytest.raises(ValueError):
        criteria_score(criteria)
