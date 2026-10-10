"""Synthetic guardrails: no source validity or extraction accuracy is implied."""
from pathlib import Path
import pytest
from bmw_pm.contracts import PriorityPolicy
from streamlit.testing.v1 import AppTest
from bmw_pm.intelligence.provider import OpenAIStructuredExtractionProvider, _Draft, _ExtractionResult
from bmw_pm.decision.planning import PriorityService, decision_brief
from test_fusion import database, run


def test_live_model_paraphrase_and_severity_cannot_become_evidence(tmp_path):
    with pytest.raises(ValueError):
        PriorityPolicy.model_validate({})  # no implicit policy may fill missing human input
    db=database(tmp_path)
    record=db.feedback_records(model_code="G60")[0]
    text=record.redacted_text
    draft=_Draft(need_domain="controls_usability",atomic_claim="Invented verified global defect",
        customer_outcome="Invented future product target",polarity="complaint",evidence_text=text,
        evidence_start=0,evidence_end=len(text),severity_label="invented high severity",use_context="invented future market")
    signals=OpenAIStructuredExtractionProvider._validate_drafts(record,_ExtractionResult(signals=[draft],abstention_reason=None),run_id="fixture")
    assert signals[0].atomic_claim==text
    assert signals[0].customer_outcome=="Evidence topic: controls_usability"
    assert signals[0].severity_label is None and signals[0].use_context is None


def test_blank_priorities_stay_unknown_and_export_has_no_future_forecast(tmp_path,monkeypatch):
    app_path=Path("ui/app.py").resolve()
    db=database(tmp_path)
    run(db)
    monkeypatch.delenv("BMW_PM_HOSTED",raising=False)
    monkeypatch.delenv("RENDER",raising=False)
    monkeypatch.setenv("BMW_PM_DATABASE",str(db.path))
    monkeypatch.chdir(tmp_path)
    app=AppTest.from_file(str(app_path),default_timeout=30).run()
    next(x for x in app.text_input if x.label=="SQLite database").set_value(str(db.path)).run()
    assert not app.exception
    assert all(x.value==0 for x in app.slider if x.label.endswith(" weight"))
    assert all(x.value is None for x in app.number_input if x.label.startswith("Priority "))
    next(x for x in app.button if x.label=="Save priority assessment").click().run()
    assert not app.exception
    assert any("No default policy" in x.value for x in app.error)
    for item in db.requirement_summaries():
        assert PriorityService(db).history(item["requirement"].requirement_id)==[]
    brief=decision_brief(db,db.requirement_summaries(),{},None)
    assert "2029" not in brief and "seed judgement" not in brief
    assert "Unknown; explicit PM input required" in brief
