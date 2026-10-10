"""Decision-workflow tests, not extraction accuracy or real PM judgements."""
import sqlite3
import pytest

from bmw_pm.contracts import PriorityFactors, PriorityPolicy, DecisionAction
from bmw_pm.decision.planning import PriorityService, priority_score, load_proposals, proposal_for
from bmw_pm.review import ReviewService
from bmw_pm.storage import Database, RevisionConflict, WorkflowError
from test_audit import _requirement


def setup(tmp_path):
    db = Database(tmp_path / "planning.db")
    req = db.ensure_requirement(_requirement(), request_id="create", run_id="fixture")
    return db, req, PriorityService(db)


def save(service, req, **overrides):
    values = dict(requirement_id=req.requirement_id, expected_revision=req.revision, expected_sequence=0,
        factors=PriorityFactors(impact=4,evidence=2,relevance=3,uncertainty=2), policy=PriorityPolicy(),
        actor_id="synthetic-pm", rationale="Synthetic judgement, not BMW input", request_id="priority-1")
    values.update(overrides)
    return service.save(**values)


def test_priority_math_weights_and_uncertainty():
    high = PriorityFactors(impact=4,evidence=4,relevance=4,uncertainty=0)
    assert priority_score(high,PriorityPolicy()) == 100
    assert priority_score(PriorityFactors(impact=0,evidence=0,relevance=0,uncertainty=4),PriorityPolicy()) == 0
    assert priority_score(high.model_copy(update={"uncertainty":4}),PriorityPolicy()) == 85
    with pytest.raises(ValueError):
        PriorityPolicy(impact=.9)
    with pytest.raises(ValueError):
        PriorityFactors(impact=5,evidence=0,relevance=0,uncertainty=0)


def test_saved_priority_revision_binding_idempotency_and_conflict(tmp_path):
    db,req,service=setup(tmp_path)
    first=save(service,req)
    assert save(service,req)==first
    with pytest.raises(WorkflowError,match="reused"):
        save(service,req,rationale="different payload")
    with pytest.raises(RevisionConflict,match="another session"):
        save(service,req,request_id="concurrent")
    decision=ReviewService(db).decide(requirement_id=req.requirement_id, expected_revision=1,
        action=DecisionAction.APPROVE,rationale="Synthetic conditional approval",actor_id="synthetic-pm",request_id="approve")
    assert decision.priority_assessment_id==first.assessment_id
    second=save(service,req,expected_sequence=1,request_id="priority-2",factors=first.factors.model_copy(update={"impact":1}))
    assert second.score<first.score
    assert db.replay_requirement(req.requirement_id)["decisions"][0]["priority_assessment_id"]==first.assessment_id
    _,new=ReviewService(db).edit(requirement_id=req.requirement_id,expected_revision=1,
        changes={"customer_outcome":"Revised synthetic customer task."},rationale="Synthetic challenge",actor_id="synthetic-pm",request_id="edit")
    with pytest.raises(RevisionConflict,match="Requirement changed"):
        save(service,req,expected_sequence=2,request_id="stale")
    assert not [p for p in service.history(req.requirement_id) if p.requirement_revision==new.revision]
    with db.connect() as connection:
        with pytest.raises(sqlite3.IntegrityError,match="immutable"):
            connection.execute("UPDATE priority_assessments SET sequence=9")
    assert db.verify_audit_chain()[0]


def test_missing_rationale_and_scope_do_not_create_false_evidence(tmp_path):
    db,req,service=setup(tmp_path)
    with pytest.raises(ValueError):
        save(service,req,rationale=" ")
    with pytest.raises(ValueError):
        save(service,req,actor_id=" ")
    assert service.history(req.requirement_id)==[]
    proposals=load_proposals("configs/successor_proposals_v1.json")
    assert len(proposals)==7
    assert proposal_for(db,req,proposals) is None  # unseen scope must not inherit US G60 recommendations


def test_substantive_edit_invalidates_score_but_title_retains_it(tmp_path):
    from test_fusion import database, run
    db=database(tmp_path)
    run(db)
    req=db.requirement_summaries()[0]["requirement"]
    assert db.latest_score(req.requirement_id,req.revision)
    review=ReviewService(db)
    _,renamed=review.edit(requirement_id=req.requirement_id, expected_revision=req.revision,
        changes={"title":"Renamed synthetic requirement"}, rationale="Editorial only",actor_id="synthetic-pm",request_id="rename")
    assert db.latest_score(req.requirement_id,renamed.revision)
    _,changed=review.edit(requirement_id=req.requirement_id, expected_revision=renamed.revision,
        changes={"customer_outcome":"Different synthetic task"}, rationale="Change meaning",actor_id="synthetic-pm",request_id="change")
    assert db.latest_score(req.requirement_id,changed.revision) is None
    assert db.latest_score(req.requirement_id,req.revision)
