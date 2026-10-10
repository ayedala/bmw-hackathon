"""Synthetic end-to-end checks for the redesigned workbench and real service writes."""
from pathlib import Path
from streamlit.testing.v1 import AppTest
from bmw_pm.storage import Database
from bmw_pm.decision.planning import PriorityService
from test_audit import _requirement

APP = Path("ui/app.py").resolve()

def open_app(db, monkeypatch):
    monkeypatch.delenv("BMW_PM_HOSTED", raising=False)
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.setenv("BMW_PM_DATABASE", str(db.path))
    return AppTest.from_file(str(APP), default_timeout=30).run()

def widget(items, label):
    return next(x for x in items if x.label == label)

def test_priority_reordering_keeps_selected_card_and_decision_reference(tmp_path, monkeypatch):
    db = Database(tmp_path / "ui.db")
    for key in ("synthetic-a", "synthetic-z"):
        db.ensure_requirement(_requirement().model_copy(update={"requirement_id": key, "title": key}), request_id=f"create:{key}", run_id="fixture")
    app = open_app(db, monkeypatch)
    assert not app.exception
    widget(app.button, "synthetic-z").click().run()
    assert app.session_state["selected_requirement"] == "synthetic-z"
    assert widget(app.button, "Approve").disabled
    widget(app.button, "Prepare private decision brief").click().run()
    assert not app.exception
    assert "vehicles X99; markets ZZ" in app.session_state["planning_export"][3]
    assert "Planning scenario: US 5 Series" not in app.session_state["planning_export"][3]
    widget(app.text_input, "Planning reviewer ID").set_value("synthetic-pm")
    for item in app.slider:
        if item.label.endswith(" weight"):
            item.set_value(25)
    app.run()
    for item in app.number_input:
        if item.label.startswith("Priority "):
            item.set_value(0 if item.label == "Priority uncertainty" else 4)
    widget(app.text_area, "Priority rationale (required)").set_value("Synthetic test judgement")
    widget(app.button, "Save priority assessment").click().run()
    assert not app.exception
    assert app.session_state["selected_requirement"] == "synthetic-z"
    assert "planning_export" not in app.session_state
    assessment = PriorityService(db).history("synthetic-z")[-1]
    widget(app.text_input, "Reviewer ID (declared, not verified)").set_value("synthetic-pm").run()
    widget(app.text_area, "Decision rationale (required)").set_value("Synthetic approval of selected card").run()
    assert widget(app.button, "Approve").disabled
    next(x for x in app.checkbox if x.label.startswith("For approval:")).check().run()
    widget(app.button, "Approve").click().run()
    assert not app.exception
    decision = db.replay_requirement("synthetic-z")["decisions"][-1]
    assert decision["action"] == "approve"
    assert decision["uncertainty_acknowledged"]
    assert decision["priority_assessment_id"] == assessment.assessment_id
    assert not db.replay_requirement("synthetic-a")["decisions"]
    widget(app.button, "View audit trail →").click().run()
    assert not app.exception
    assert app.session_state["destination"] == "Audit trail"
    assert any("Audit chain verified" in x.value for x in app.success)

def test_evidence_assessment_and_navigation_use_selected_requirement(tmp_path, monkeypatch):
    from test_fusion import database, run
    db = database(tmp_path)
    run(db)
    app = open_app(db, monkeypatch)
    assert not app.exception
    selected_id = app.session_state["selected_requirement"]
    widget(app.button, "Inspect sources and assess links →").click().run()
    assert not app.exception
    assert app.session_state["destination"] == "Data & AI findings"
    widget(app.selectbox, "Does this signal support the selected outcome?").set_value("supports")
    widget(app.text_input, "Reviewer ID (declared, not verified)").set_value("synthetic-evidence-pm")
    widget(app.text_area, "Reason for this link assessment").set_value("Synthetic excerpt supports the selected customer task")
    widget(app.button, "Record link assessment").click().run()
    assert not app.exception
    req = db.latest_requirement(selected_id)
    judgments = db.latest_evidence_judgments(selected_id, req.revision)
    assert len(judgments) == 1
    assert next(iter(judgments.values())).actor_id == "synthetic-evidence-pm"
    widget(app.radio, "Workspace").set_value("Audit trail").run()
    assert not app.exception
    assert app.session_state["selected_requirement"] == selected_id

def test_edit_creates_revision_with_no_stale_score(tmp_path, monkeypatch):
    from test_fusion import database, run
    db = database(tmp_path)
    run(db)
    app = open_app(db, monkeypatch)
    selected_id = app.session_state["selected_requirement"]
    before = db.latest_requirement(selected_id)
    widget(app.text_input, "Reviewer ID (declared, not verified)").set_value("synthetic-editor").run()
    widget(app.text_area, "Customer outcome").set_value("A revised synthetic customer task.")
    widget(app.text_area, "Edit rationale").set_value("Synthetic clarification of customer outcome")
    widget(app.button, "Create new revision").click().run()
    assert not app.exception
    after = db.latest_requirement(selected_id)
    assert after.revision == before.revision + 1
    assert after.customer_outcome == "A revised synthetic customer task."
    assert db.latest_score(selected_id, after.revision) is None
    assert db.latest_score(selected_id, before.revision)
    assert db.verify_audit_chain()[0]


def test_future_draft_seed_adoption_and_confirmed_priority_are_separate(tmp_path,monkeypatch):
    from test_successor_drafts import fixture
    import bmw_pm.decision.planning as planning
    db,req,proposals=fixture(tmp_path)
    monkeypatch.setattr(planning,"load_proposals",lambda path:proposals)
    app=open_app(db,monkeypatch)
    assert not app.exception
    assert any(x.value=="Future-facing draft · not approved" for x in app.subheader)
    # A reviewer may not accidentally approve the displayed draft while the stored wording is different.
    widget(app.text_input,"Reviewer ID (declared, not verified)").set_value("synthetic-pm")
    widget(app.text_area,"Decision rationale (required)").set_value("Synthetic concept-testing intent")
    next(x for x in app.checkbox if x.label.startswith("For approval:")).check().run()
    assert widget(app.button,"Approve").disabled
    assert widget(app.button,"Reject").disabled
    widget(app.button,"Use AI suggestion as editable draft inputs").click().run()
    assert not PriorityService(db).history(req.requirement_id)
    assert not db.replay_requirement(req.requirement_id)["decisions"]
    widget(app.text_input,"Planning reviewer ID").set_value("synthetic-pm")
    widget(app.text_area,"Draft adoption rationale (required)").set_value("Synthetic explicit adoption for review")
    widget(app.button,"Adopt draft as reviewable revision").click().run()
    assert not app.exception
    current=db.latest_requirement(req.requirement_id)
    assert current.revision==2 and current.successor_draft_id
    widget(app.button,"Use AI suggestion as editable draft inputs").click().run()
    widget(app.number_input,"Priority uncertainty").set_value(3)
    widget(app.number_input,"Manual portfolio rank (0 = score order)").set_value(1)
    widget(app.text_area,"Priority rationale (required)").set_value("Synthetic PM draft priority")
    widget(app.button,"Save priority assessment").click().run()
    assert not app.exception
    saved=PriorityService(db).history(req.requirement_id)[-1]
    assert not saved.priority_confirmed and saved.rank_override==1
    assert saved.requirement_revision==2 and saved.factors.uncertainty==3
    widget(app.button,"Use AI suggestion as editable draft inputs").click().run()
    widget(app.text_area,"Priority rationale (required)").set_value("Synthetic explicit priority confirmation")
    widget(app.checkbox,"I explicitly confirm this priority as the reviewer").check()
    widget(app.button,"Save priority assessment").click().run()
    assert not app.exception
    assert PriorityService(db).history(req.requirement_id)[-1].priority_confirmed
    assert not any(x["action"]=="approve" for x in db.replay_requirement(req.requirement_id)["decisions"])
    widget(app.button,"Prepare private decision brief").click().run()
    brief=app.session_state["planning_export"][3]
    assert "Future assumption (not fact)" in brief and "confirmed=True" in brief
    widget(app.radio,"Workspace").set_value("Audit trail").run()
    assert not app.exception
    assert any("Audit chain verified" in x.value for x in app.success)
