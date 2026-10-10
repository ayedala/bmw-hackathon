from pathlib import Path
from streamlit.testing.v1 import AppTest
from bmw_pm.storage import Database
from bmw_pm.decision.planning import PriorityService
from test_audit import _requirement


def test_priority_reordering_keeps_selected_card_and_decision_reference(tmp_path, monkeypatch):
    app_path=Path("ui/app.py").resolve()
    db=Database(tmp_path / "ui.db")
    for key in ("synthetic-a","synthetic-z"):
        db.ensure_requirement(_requirement().model_copy(update={"requirement_id":key,"title":key}),
            request_id=f"create:{key}",run_id="fixture")
    monkeypatch.delenv("BMW_PM_HOSTED",raising=False)
    monkeypatch.delenv("RENDER",raising=False)
    monkeypatch.chdir(tmp_path)
    app=AppTest.from_file(str(app_path),default_timeout=30).run()
    next(x for x in app.text_input if x.label=="SQLite database").set_value(str(db.path)).run()
    next(x for x in app.radio if x.label=="Requirement").set_value("synthetic-z").run()
    for item in app.slider:
        if item.label.startswith("Priority "):
            item.set_value(0 if item.label=="Priority uncertainty" else 4)
    next(x for x in app.text_area if x.label=="Priority rationale (required)").set_value("Synthetic test judgement")
    next(x for x in app.button if x.label=="Save priority assessment").click().run()
    assert not app.exception
    assert next(x for x in app.radio if x.label=="Requirement").value=="synthetic-z"
    assessment=PriorityService(db).history("synthetic-z")[-1]
    next(x for x in app.text_area if x.label=="Decision rationale (required)").set_value("Synthetic approval of selected card")
    next(x for x in app.button if x.label=="Approve").click().run()
    assert not app.exception
    decision=db.replay_requirement("synthetic-z")["decisions"][-1]
    assert decision["action"]=="approve"
    assert decision["priority_assessment_id"]==assessment.assessment_id
    assert not db.replay_requirement("synthetic-a")["decisions"]
