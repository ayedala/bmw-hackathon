"""Synthetic workflow checks, not evidence of recommendation accuracy."""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

from bmw_pm.advisor.contracts import (AdvisorRequest, AdvisorResult, Claim, DecisionReport,
                                      EvidenceItem, EvidencePacket, Option, ResearchBundle, ResearchPlan)
from bmw_pm.advisor.evidence import build_packet, model_payload
from bmw_pm.advisor.finance import scenario_results
from bmw_pm.advisor.provider import AdvisorProvider, parse_research, validate_report
from bmw_pm.advisor.settings import project_credentials
from bmw_pm.advisor.service import run_advisor
from bmw_pm.contracts import FeedbackRecord, SourceLocator
from bmw_pm.intelligence.provider import ProviderError
from bmw_pm.storage import Database
from bmw_pm.utils import content_hash


@pytest.fixture
def evidence_db(tmp_path):
    db = Database(tmp_path / "advisor.db")
    db.initialize()
    with db.connect() as connection:
        for index, (model, country, powertrain, text) in enumerate([
            ("G60", "US", "ICE", "The climate control menu is hard. Contact me at sample@example.com."),
            ("G60", "US", "ICE", "The climate control menu is easy."),
            ("G60", "GB", "ICE", "The climate control menu is poor."),
            ("G70", "US", "ICE", "The climate control menu is poor."),
            ("G60", "US", "BEV", "Charging is slow."),
        ]):
            locator = SourceLocator(source_id="synthetic", source_hash="a" * 64, locator_type="sheet_range",
                                    sheet="Feedback", cell_range=f"A{index + 1}", exact_quote=text)
            record = FeedbackRecord(record_id=str(index), source_id="synthetic", source_record_id=str(index),
                raw_text_ref="synthetic", cleaned_text=text, redacted_text=text, raw_country=country,
                country=country, raw_model=model, model_code=model, raw_brand="BMW", raw_sales_description=None,
                raw_derivative=None, powertrain_raw=powertrain, powertrain=powertrain,
                powertrain_mapping_status="exact", source_label="fixture", row_locators=[locator], transformation_ids=[])
            connection.execute("INSERT OR IGNORE INTO sources VALUES (?,?,?,?)", ("synthetic", "a" * 64, "{}", "x"))
            connection.execute("INSERT INTO feedback_records VALUES (?,?,?,?,?,?,?,?)",
                               (record.record_id, record.source_id, record.source_record_id, model, country, powertrain,
                                record.model_dump_json(), content_hash(record)))
        connection.commit()
    return db.path


def request(journey="improve", **kwargs):
    return AdvisorRequest(journey=journey, model_code="G60", market="US", powertrain="ICE", **kwargs)


def draft(req):
    cited = Claim(text="Controls deserve investigation.", basis="inference",
                  evidence_ids=["topic:controls_usability"], explanation="The scoped corpus contains a complaint and praise.")
    unknown = Claim(text="Matched internal estimates are unavailable.", basis="unknown", evidence_ids=[], explanation="Obtain an engineering estimate.")
    options = [Option(option_id=f"idea_{i + 1}", title=idea, proposal="Test the customer task before selecting hardware.",
                      customer_case=[cited], competitors=[unknown], feasibility=unknown,
                      cost_outlook=unknown, revenue_outlook=unknown, delivery_steps=["Prototype and measure task success."],
                      risks=["Preserve familiar controls."], validation_needed=["Engineering integration review."])
               for i, idea in enumerate(req.ideas or ["Improve climate controls"])]
    return DecisionReport(headline="Investigate controls", summary="Synthetic test result.", options=options,
                          preferred_option_id=options[0].option_id, recommendation=cited, comparison=[cited],
                          follow_up_questions=["What is the approved budget?"])


def web_response():
    text = "A manufacturer describes controls. [source]"
    payload = {"output": [{"type": "web_search_call", "status": "completed", "action": {"type": "search", "query": "vehicle controls"}},
                          {"type": "message", "content": [{"type": "output_text", "text": text, "annotations": [
                              {"type": "url_citation", "url": "https://example.com/controls", "title": "Synthetic manufacturer",
                               "start_index": text.index("[source]"), "end_index": len(text)}]}]}]}
    return SimpleNamespace(model_dump=lambda: payload, id="web_response", model="fixture", status="completed", usage=None)


def test_retrieval_scope_preservation_redaction_and_read_only(evidence_db):
    before = evidence_db.read_bytes()
    packet = build_packet(request(), evidence_db)
    assert packet.feedback_records == 2
    controls = next(t for t in packet.topics if t.domain == "controls_usability")
    assert controls.supporting_records == controls.praise_records == 1
    assert next(t for t in packet.topics if t.domain == "charging_and_range").eligible_records == 0
    feedback = [e for e in packet.evidence if e.channel == "customer_feedback"]
    assert {e.scope["country"] for e in feedback} == {"US"}
    assert any("praise" in e.title for e in feedback)
    # An extra query match includes contact text, which must not enter the model payload.
    packet = build_packet(request("idea", question="Contact sample about climate controls"), evidence_db,
                          focus_domains=["software_reliability"], search_terms=["contact"])
    assert "sample@example.com" not in json.dumps(model_payload(packet))
    assert evidence_db.read_bytes() == before
    assert packet.fingerprint == build_packet(packet.request, evidence_db,
        focus_domains=["software_reliability"], search_terms=["contact"]).fingerprint


def test_uncovered_market_and_invalid_comparison(evidence_db):
    req = request().model_copy(update={"market": "CN"})
    packet = build_packet(req, evidence_db)
    assert packet.feedback_records == 0
    assert any("No feedback" in text for text in packet.limitations)
    with pytest.raises(ValueError):
        request("compare", ideas=["A single idea is insufficient"])
    with pytest.raises(ValueError):
        request("compare", ideas=["Repeated idea", "Repeated idea"])


def test_citations_and_comparison_coverage_are_enforced(evidence_db):
    req = request("compare", ideas=["Physical climate shortcuts", "Improved voice control"])
    packet = build_packet(req, evidence_db)
    report = draft(req)
    validate_report(report, packet.evidence, req)
    with pytest.raises(ProviderError, match="every submitted"):
        validate_report(report.model_copy(update={"options": report.options[:1]}), packet.evidence, req)
    bad = report.recommendation.model_copy(update={"evidence_ids": ["invented:source"]})
    with pytest.raises(ProviderError, match="not supplied"):
        validate_report(report.model_copy(update={"recommendation": bad}), packet.evidence, req)
    bad = bad.model_copy(update={"basis": "evidence", "evidence_ids": []})
    with pytest.raises(ProviderError, match="uncited"):
        validate_report(report.model_copy(update={"recommendation": bad}), packet.evidence, req)


def test_search_must_really_complete_and_return_citations():
    response = web_response()
    payload = response.model_dump()
    annotations = payload["output"][1]["content"][0]["annotations"]
    annotations.append({**annotations[0], "url": "https://example.com/second"})
    response.model_dump = lambda: payload
    result = parse_research(response)
    assert result.sources[0].evidence_id == "web:1"
    assert result.text.endswith("[web:1] [web:2]")
    response.model_dump = lambda: {"output": []}
    with pytest.raises(ProviderError, match="completed search"):
        parse_research(response)


def test_settings_do_not_execute_or_print_secrets(tmp_path):
    secret = "synthetic-secret-value"
    (tmp_path / ".env").write_text(f'OPENAI_API_KEY="{secret}"\nOPENAI_PROJECT_ID=synthetic-project\nUNRELATED=ignored\n', encoding="utf-8")
    credentials = project_credentials(tmp_path)
    assert credentials.api_key == secret
    assert credentials.project_id == "synthetic-project"
    assert secret not in repr(credentials)


def test_provider_errors_do_not_expose_credentials_or_silently_substitute():
    def fail(**kwargs):
        raise RuntimeError("synthetic-secret-value")
    provider = AdvisorProvider(client=SimpleNamespace(responses=SimpleNamespace(parse=fail)))
    with pytest.raises(ProviderError) as result:
        provider.plan(request(), ["controls_usability"])
    assert "synthetic-secret-value" not in str(result.value)


def test_live_workflow_uses_bounded_calls_and_keeps_private_quotes_out_of_search(evidence_db):
    req = request()
    plan = ResearchPlan(focus_domains=["controls_usability"], search_terms=["climate controls"],
                        research_questions=["Which manufacturers offer tactile controls?"], rationale="Investigate usability.")
    calls = []
    parsed = iter([plan, draft(req)])

    def parse(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(output_parsed=next(parsed), id="parsed", model="fixture", status="completed", usage=None)

    def create(**kwargs):
        calls.append(kwargs)
        assert "sample@example.com" not in json.dumps(kwargs)
        assert "The climate control menu is hard" not in json.dumps(kwargs)
        return web_response()

    provider = AdvisorProvider(model_id="fixture", client=SimpleNamespace(responses=SimpleNamespace(parse=parse, create=create)))
    progress = []
    result = run_advisor(req, evidence_db, provider, progress.append)
    assert len(calls) == 3 and all(call["store"] is False for call in calls)
    assert calls[1]["max_tool_calls"] == 8
    assert result.mode == "live_ai" and result.steps == progress
    assert len(result.usage) == 3


def test_economics_requires_inputs_and_computes_cash_flow():
    row = dict(upfront_cost=1000, annual_fixed_cost=20, baseline_units=100, incremental_units=2,
               adoption_rate=0.5, revenue_per_extra_vehicle=100, cost_per_extra_vehicle=60,
               revenue_uplift_per_adopter=5, feature_cost_per_adopter=2)
    rows = [dict(scenario=name, **row) for name in ("Downside", "Base", "Upside")]
    results = scenario_results(rows, years=2, discount_rate=Decimal("0"), source="Synthetic assumptions")
    assert results[0]["Annual added revenue"] == 450
    assert results[0]["Annual net cash flow"] == 208
    assert results[0]["NPV"] == -584
    rows[0]["upfront_cost"] = None
    with pytest.raises(ValueError):
        scenario_results(rows, years=2, discount_rate=Decimal("0"), source="Synthetic assumptions")


@pytest.mark.parametrize("label,mode", [("Assess my idea", "idea"), ("Find the next improvement", "improve"), ("Compare several ideas", "compare")])
def test_ui_journeys_render_and_results_survive_reruns(monkeypatch, label, mode):
    import bmw_pm.advisor.provider as provider_module
    import bmw_pm.advisor.service as service_module
    calls = []

    def fake_run(req, database, provider, progress):
        calls.append(req)
        evidence = EvidenceItem(evidence_id="topic:controls_usability", channel="corpus_summary", title="Controls",
                                text="Synthetic aggregate", selection_reason="Fixture")
        return AdvisorResult(run_id="fixture", created_at="2026-10-10T12:00:00Z", model_id="fixture", prompt_version="fixture",
            packet=EvidencePacket(request=req, feedback_records=2, topics=[], evidence=[evidence], limitations=["Synthetic test"], fingerprint="fixture"),
            plan=ResearchPlan(focus_domains=[], search_terms=[], research_questions=[], rationale="Synthetic test"),
            research=parse_research(web_response()), report=draft(req), steps=["Synthetic test"], usage=[])

    monkeypatch.setattr(provider_module, "AdvisorProvider", lambda **kwargs: object())
    monkeypatch.setattr(service_module, "run_advisor", fake_run)
    app = AppTest.from_file(Path("ui/mocktest.py").resolve(), default_timeout=45).run()
    app.radio[0].set_value(label).run()
    if mode == "idea":
        app.text_area[0].set_value("Add physical climate shortcuts")
    elif mode == "compare":
        app.text_area[0].set_value("Add physical climate shortcuts\nImprove voice control accuracy")
    next(button for button in app.button if button.label == "Research and assess").click().run()
    assert not app.exception
    assert len(calls) == 1 and calls[0].journey == mode
    assert len(app.tabs) == 5
    app.run()
    assert not app.exception and len(app.tabs) == 5 and len(calls) == 1


def test_advisor_hosted_entry_requires_sign_in(monkeypatch, tmp_path):
    monkeypatch.setenv("BMW_PM_HOSTED", "1")
    monkeypatch.setenv("BMW_PM_DB_PATH", str(tmp_path / "absent.db"))
    monkeypatch.setenv("BMW_PM_APP_PASSWORD", "synthetic-team-password-long")
    monkeypatch.setenv("BMW_PM_ADMIN_PASSWORD", "synthetic-admin-password-long")
    app = AppTest.from_file(Path("ui/mocktest.py").resolve(), default_timeout=45).run()
    assert not app.exception
    assert any(item.value == "Team sign-in" for item in app.subheader)
    assert not app.radio
