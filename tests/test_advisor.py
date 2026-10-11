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
from bmw_pm.advisor.settings import ProjectCredentials, project_credentials, save_project_credentials
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


def test_private_env_key_overrides_tracked_template(tmp_path):
    (tmp_path / ".env").write_text("OPENAI_API_KEY=\n")
    (tmp_path / ".env.local").write_text("OPENAI_API_KEY=synthetic-local-key\n")
    credentials = project_credentials(tmp_path)
    assert (credentials.api_key, credentials.origin) == ("synthetic-local-key", ".env.local")


def test_saved_app_key_survives_restart_and_does_not_overwrite_other_settings(tmp_path):
    existing = 'OPENAI_API_KEY=old-key\nUNRELATED=keep\n'
    (tmp_path / ".env").write_text(existing, encoding="utf-8")
    candidate = ProjectCredentials("new-synthetic-key", "proj-synthetic")
    save_project_credentials(candidate, tmp_path)
    loaded = project_credentials(tmp_path)
    assert (loaded.api_key, loaded.project_id, loaded.origin) == (candidate.api_key, candidate.project_id, ".env.advisor")
    assert (tmp_path / ".env").read_text(encoding="utf-8") == existing
    assert loaded.fingerprint("model-a") != loaded.fingerprint("model-b")
    assert loaded.fingerprint("model-a") != ProjectCredentials("other-key").fingerprint("model-a")
    with pytest.raises(ValueError):
        save_project_credentials(ProjectCredentials("bad\nUNRELATED=replace"), tmp_path)
    assert project_credentials(tmp_path).api_key == candidate.api_key
    assert not list(tmp_path.glob(".env.advisor-*"))


@pytest.mark.parametrize("status,reason,accepted", [
    ("completed", None, True), ("incomplete", "max_output_tokens", True),
    ("incomplete", "content_filter", False), ("failed", None, False),
])
def test_connection_probe_is_bounded_and_only_checks_generation_access(status, reason, accepted):
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(status=status, incomplete_details=SimpleNamespace(reason=reason),
                               id="synthetic", model="fixture", usage=None)

    provider = AdvisorProvider(model_id="fixture", client=SimpleNamespace(responses=SimpleNamespace(create=create)))
    if accepted:
        provider.check_connection()
    else:
        with pytest.raises(ProviderError):
            provider.check_connection()
    assert calls == [dict(model="fixture", store=False, input="Reply with OK.", max_output_tokens=32, timeout=20)]
    if status != "completed":
        with pytest.raises(ProviderError):
            provider._call("Real research", input="A public question")


def test_provider_errors_do_not_expose_credentials_or_silently_substitute():
    def fail(**kwargs):
        raise RuntimeError("synthetic-secret-value")
    provider = AdvisorProvider(client=SimpleNamespace(responses=SimpleNamespace(parse=fail)))
    with pytest.raises(ProviderError) as result:
        provider.plan(request(), ["controls_usability"])
    assert "synthetic-secret-value" not in str(result.value)


def test_live_workflow_uses_bounded_calls_and_keeps_private_quotes_out_of_search(evidence_db, monkeypatch):
    monkeypatch.setattr("bmw_pm.advisor.provider.firecrawl_key", lambda: None)
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


def test_page_inspection_is_restricted_to_cited_public_urls(tmp_path, monkeypatch):
    from bmw_pm.advisor.public_tools import PublicPageInspector, firecrawl_key, public_page_url

    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    (tmp_path / ".env.local").write_text("FIRECRAWL_API_KEY=synthetic-firecrawl-key\n", encoding="utf-8")
    assert firecrawl_key(tmp_path) == "synthetic-firecrawl-key"
    assert public_page_url("https://www.bmw.com/example")
    for url in ("http://example.com", "https://localhost/a", "https://127.0.0.1/a",
                "https://10.0.0.1/a", "https://example.com:8080/a", "file:///etc/passwd"):
        assert not public_page_url(url)
    calls = []

    def scrape(url, **kwargs):
        calls.append((url, kwargs))
        return {"markdown": "Official product information", "metadata": {"title": "Product page", "source_url": url}}

    inspector = PublicPageInspector("synthetic-key", client=SimpleNamespace(scrape=scrape))
    with pytest.raises(ValueError, match="cited"):
        inspector.inspect("https://other.example/page", {"https://example.com/page"}, "page:1")
    assert not calls
    page = inspector.inspect("https://example.com/page", {"https://example.com/page"}, "page:1")
    assert page.channel == "inspected_public_page" and page.locator["url"] == "https://example.com/page"
    assert len(calls) == 1


def test_model_selected_page_is_added_as_citable_evidence_without_private_data():
    from bmw_pm.advisor.public_tools import PublicPageInspector

    research = parse_research(web_response())
    seen = []
    call = SimpleNamespace(type="function_call", name="inspect_public_page", call_id="call-1",
                           arguments='{"url":"https://example.com/controls"}')

    def create(**kwargs):
        seen.append(kwargs)
        if len(seen) == 1:
            return SimpleNamespace(output=[call], status="completed", id="select", model="fixture", usage=None)
        return SimpleNamespace(output=[], status="completed", id="continued", model="fixture", usage=None)

    def scrape(url, **kwargs):
        return {"markdown": "Controls are described on this public page.",
                "metadata": {"title": "Controls", "source_url": url}}

    provider = AdvisorProvider(model_id="fixture", client=SimpleNamespace(responses=SimpleNamespace(create=create)))
    enriched = provider.inspect_research_pages(research, PublicPageInspector("synthetic-key", SimpleNamespace(scrape=scrape)))
    assert [item.evidence_id for item in enriched.sources] == ["web:1", "page:1"]
    assert seen[0]["tools"][0]["name"] == "inspect_public_page"
    assert "The climate control menu is hard" not in json.dumps(seen[0]["input"])
    assert seen[1]["input"][-1]["type"] == "function_call_output"
    assert "page:1" in seen[1]["input"][-1]["output"]
    assert all(call["store"] is False for call in seen)


def test_uncited_model_page_request_never_reaches_scraper():
    from bmw_pm.advisor.public_tools import PublicPageInspector

    research = parse_research(web_response())
    calls = []
    tool_call = SimpleNamespace(type="function_call", name="inspect_public_page", call_id="call-1",
                                arguments='{"url":"https://uncited.example/private"}')

    def create(**kwargs):
        calls.append(kwargs)
        output = [tool_call] if len(calls) == 1 else []
        return SimpleNamespace(output=output, status="completed", id="synthetic", model="fixture", usage=None)

    def scrape(*args, **kwargs):
        raise AssertionError("Uncited URL reached scraper")

    provider = AdvisorProvider(model_id="fixture", client=SimpleNamespace(responses=SimpleNamespace(create=create)))
    result = provider.inspect_research_pages(research, PublicPageInspector("synthetic-key", SimpleNamespace(scrape=scrape)))
    assert [item.evidence_id for item in result.sources] == ["web:1"]
    assert "error" in calls[-1]["input"][-1]["output"]


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
    import bmw_pm.advisor.settings as settings_module
    monkeypatch.setattr(settings_module, "project_credentials", lambda: ProjectCredentials("synthetic-key"))
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


def test_ui_configures_connection_inside_app_without_exposing_ai_model(monkeypatch, tmp_path):
    import bmw_pm.advisor.provider as provider_module
    import bmw_pm.advisor.service as service_module
    import bmw_pm.advisor.settings as settings_module
    monkeypatch.setenv("BMW_PM_OPENAI_MODEL", "private-configured-model")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(settings_module, "project_credentials", lambda: project_credentials(tmp_path))
    monkeypatch.setattr(settings_module, "save_project_credentials", lambda credentials: save_project_credentials(credentials, tmp_path))
    calls = []
    research = []

    def provider(**kwargs):
        calls.append(kwargs)
        def check():
            if kwargs["api_key"] == "rejected-synthetic-key":
                raise ProviderError("Connection check: The API key was rejected.")
        return SimpleNamespace(check_connection=check)

    def fail_research(req, database, provider, progress):
        research.append(req)
        raise ProviderError("Synthetic quota error")

    monkeypatch.setattr(provider_module, "AdvisorProvider", provider)
    monkeypatch.setattr(service_module, "run_advisor", fail_research)
    app = AppTest.from_file(Path("ui/mocktest.py").resolve(), default_timeout=45).run()
    assert not app.exception
    assert not any(item.label in {"OpenAI API key", "LLM model"} for item in app.text_input)
    next(button for button in app.button if button.label == "App settings").click().run()
    assert not app.radio
    next(item for item in app.text_input if item.label == "OpenAI API key").set_value("new-synthetic-key")
    next(item for item in app.text_input if item.label == "Project ID (optional)").set_value("proj-synthetic")
    next(button for button in app.button if button.label == "Save and test connection").click().run()
    assert not app.exception and app.success
    assert project_credentials(tmp_path).api_key == "new-synthetic-key"
    assert calls[-1] == dict(model_id="private-configured-model", api_key="new-synthetic-key", project_id="proj-synthetic")
    assert not next(item for item in app.text_input if item.label == "OpenAI API key").value
    next(item for item in app.text_input if item.label == "OpenAI API key").set_value("rejected-synthetic-key")
    next(button for button in app.button if button.label == "Save and test connection").click().run()
    assert app.error and not app.exception
    assert project_credentials(tmp_path).api_key == "new-synthetic-key"
    assert app.session_state["advisor_credentials"].api_key == "new-synthetic-key"
    next(button for button in app.button if button.label == "Back to Decision Studio").click().run()
    assert not any(item.label in {"OpenAI API key", "LLM model"} for item in app.text_input)
    app.radio[0].set_value("Find the next improvement").run()
    next(button for button in app.button if button.label == "Research and assess").click().run()
    assert not app.exception and len(research) == 1
    assert calls[-1]["api_key"] == "new-synthetic-key"
    assert app.status[0].label == "Research could not finish" and app.status[0].state == "error"
    next(button for button in app.button if button.label == "App settings").click().run()
    assert any(item.value == "Synthetic quota error" for item in app.error)
    next(button for button in app.button if button.label == "Back to Decision Studio").click().run()
    assert app.radio[0].value == "Find the next improvement"
    visible = [item.value for group in (app.caption, app.markdown, app.error, app.success) for item in group]
    assert "private-configured-model" not in str(visible)
    assert "new-synthetic-key" not in str(visible)


def test_advisor_hosted_entry_requires_sign_in(monkeypatch, tmp_path):
    monkeypatch.setenv("BMW_PM_HOSTED", "1")
    monkeypatch.setenv("BMW_PM_DB_PATH", str(tmp_path / "absent.db"))
    monkeypatch.setenv("BMW_PM_APP_PASSWORD", "synthetic-team-password-long")
    monkeypatch.setenv("BMW_PM_ADMIN_PASSWORD", "synthetic-admin-password-long")
    app = AppTest.from_file(Path("ui/mocktest.py").resolve(), default_timeout=45).run()
    assert not app.exception
    assert any(item.value == "Team sign-in" for item in app.subheader)
    assert not app.radio


@pytest.mark.parametrize("journey", ["idea", "improve", "compare"])
def test_web_bridge_uses_existing_advisor_for_every_journey(evidence_db, tmp_path, monkeypatch, journey):
    from bmw_pm.advisor.bridge import execute
    req = request(journey, question="Improve the climate controls", ideas=["Physical climate shortcuts", "Improved voice control"] if journey == "compare" else [])
    (tmp_path / ".env").write_text("OPENAI_API_KEY=synthetic-bridge-key\n", encoding="utf-8")
    plan = ResearchPlan(focus_domains=["controls_usability"], search_terms=["climate controls"], research_questions=["Which controls are available?"], rationale="Synthetic test")
    parsed = iter([plan, draft(req)])
    calls, events = [], []

    def parse(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(output_parsed=next(parsed), status="completed", id="parsed", model="fixture", usage=None)

    def create(**kwargs):
        calls.append(kwargs)
        return web_response()

    def factory(**kwargs):
        assert kwargs["api_key"] == "synthetic-bridge-key"
        return AdvisorProvider(model_id="fixture", client=SimpleNamespace(responses=SimpleNamespace(parse=parse, create=create)))

    execute("analyze", req.model_dump(mode="json"), evidence_db, events.append, root=tmp_path, provider_factory=factory)
    assert len(calls) == 3
    assert events[-1]["type"] == "result"
    result = AdvisorResult.model_validate(events[-1]["result"])
    assert result.packet.request == req
    assert result.packet.feedback_records == 2
    assert result.report == draft(req)
    assert any(e["type"] == "progress" for e in events)
    assert "synthetic-bridge-key" not in json.dumps(events)
    assert "The climate control menu is hard" not in json.dumps(calls[1])


def test_transcript_memory_is_persistent_scoped_deduplicated_and_traceable(evidence_db):
    import sqlite3
    from bmw_pm.data_pipeline.video_memory import TranscriptInput, save_transcript
    transcript = "The climate control menu is difficult to use while driving. The physical wheel is comfortable. Contact sample@example.com."
    item = TranscriptInput(video_url="https://youtu.be/abcdefghijk", title="Synthetic owner transcript", model_code="G60", market="US", transcript=transcript)
    first = save_transcript(evidence_db, item)
    assert first["inserted"] and not save_transcript(evidence_db, item)["inserted"]
    save_transcript(evidence_db, item.model_copy(update={"model_code": "F70"}))
    save_transcript(evidence_db, item.model_copy(update={"video_url": "https://youtu.be/lmnopqrstuv", "market": "DE"}))
    packet = build_packet(request(), evidence_db, search_terms=["climate", "controls"])
    memory = [e for e in packet.evidence if e.channel == "video_transcript_memory"]
    assert len(memory) == 1 and memory[0].scope["generation"] == "G60"
    assert packet.feedback_records == 2
    assert "sample@example.com" not in json.dumps(model_payload(packet))
    loc = memory[0].locator
    assert loc["memory_id"] == first["memory_id"] and loc["transcript_sha256"] == first["transcript_sha256"]
    assert transcript[loc["start_char"]:loc["end_char"]].startswith("The climate control")
    updated = item.model_copy(update={"transcript": transcript.replace("difficult", "easy")})
    save_transcript(evidence_db, updated)
    latest = [e for e in build_packet(request(), evidence_db).evidence if e.channel == "video_transcript_memory"]
    assert len(latest) == 1 and "easy to use" in latest[0].text
    with sqlite3.connect(evidence_db) as connection:
        assert connection.execute("SELECT count(*) FROM video_memories").fetchone()[0] == 4
    for url in ("https://example.com/watch?v=abcdefghijk", "https://youtube.com.evil.test/watch?v=abcdefghijk", "file:///private", "https://youtu.be/short"):
        with pytest.raises(ValueError):
            TranscriptInput(**{**item.model_dump(), "video_url": url})


def test_saved_youtube_sync_preserves_validated_findings_and_builds_memory(evidence_db, tmp_path):
    from bmw_pm.advisor.bridge import source_catalog, sync_youtube
    folder = tmp_path / "src/bmw_pm/data_pipeline/youtube_research/output/synthetic"
    (folder / "transcripts").mkdir(parents=True)
    quote = "The climate control menu is hard to use, but the physical steering wheel is comfortable."
    (folder / "transcripts/abcdefghijk.json").write_text(json.dumps([{"start": 10, "duration": 8, "text": quote}]), encoding="utf-8")
    (folder / "sources.json").write_text(json.dumps([{"video_id": "abcdefghijk", "retrieval_status": "retrieved", "title": "Synthetic video"}]), encoding="utf-8")
    finding = dict(video_id="abcdefghijk", generation="G60", topic="controls", timestamp_seconds=10, supporting_excerpt=quote, feedback_type="pain_point")
    (folder / "evidence.json").write_text(json.dumps([finding, finding, {**finding, "supporting_excerpt": "Invented quote"}]), encoding="utf-8")
    result = sync_youtube(evidence_db, tmp_path)
    assert (result.inserted, result.rejected, result.memories_inserted, result.failed_runs) == (1, 1, 1, 0)
    assert sync_youtube(evidence_db, tmp_path).inserted == 0
    assert sync_youtube(evidence_db, tmp_path).memories_inserted == 0
    catalog = source_catalog(evidence_db, tmp_path)
    assert (catalog.youtube_findings, catalog.youtube_videos, catalog.video_memories) == (1, 1, 1)
    packet = build_packet(request(), evidence_db)
    assert packet.feedback_records == 2
    assert {"saved_video_review", "video_transcript_memory"} <= {e.channel for e in packet.evidence}
    assert any(e.locator.get("original_source", {}).get("bundle_sha256") for e in packet.evidence)


def test_web_scenarios_use_the_same_deterministic_calculator(evidence_db, tmp_path):
    from bmw_pm.advisor.bridge import execute
    row = dict(upfront_cost=1000, annual_fixed_cost=20, baseline_units=100, incremental_units=2,
        adoption_rate=0.5, revenue_per_extra_vehicle=100, cost_per_extra_vehicle=60,
        revenue_uplift_per_adopter=5, feature_cost_per_adopter=2)
    events = []
    payload = dict(rows=[dict(scenario=s, **row) for s in ("Downside", "Base", "Upside")], source="Synthetic assumptions", years=2, discount_rate=0)
    execute("scenarios", payload, evidence_db, events.append, root=tmp_path)
    assert events[0]["rows"][0]["NPV"] == -584
    assert events[0]["rows"][0]["Annual added revenue"] == 450


def test_transcript_memory_survives_empty_or_quota_failed_extraction(evidence_db, tmp_path):
    import sqlite3
    from bmw_pm.advisor.bridge import sync_youtube
    from bmw_pm.utils import sha256_bytes
    folder = tmp_path / "src/bmw_pm/data_pipeline/youtube_research/output/no-observations"
    (folder / "transcripts").mkdir(parents=True)
    original = json.dumps([{"start": 12.5, "text": "The cabin is comfortable, and the physical climate controls are easy to reach while driving."}], indent=2)
    (folder / "transcripts/abcdefghijk.json").write_bytes(original.encode("utf-8"))
    (folder / "sources.json").write_text(json.dumps([
        {"video_id": "abcdefghijk", "retrieval_status": "retrieved", "research_generation": "G60", "extraction_status": "failed", "title": "Quota failure fixture"},
        {"video_id": "lmnopqrstuv", "retrieval_status": "failed", "research_generation": "G60"},
        {"video_id": "zyxwvutsrqp", "retrieval_status": "retrieved"},
    ]), encoding="utf-8")
    (folder / "evidence.json").write_text("[]", encoding="utf-8")
    result = sync_youtube(evidence_db, tmp_path)
    assert (result.accepted, result.memories_inserted, result.failed_runs) == (0, 1, 0)
    assert sync_youtube(evidence_db, tmp_path).memories_inserted == 0
    with sqlite3.connect(evidence_db) as connection:
        saved = json.loads(connection.execute("SELECT payload_json FROM video_memories").fetchone()[0])
        assert saved["original_transcript_json"] == original
        assert saved["source_locator"]["original_transcript_sha256"] == sha256_bytes(original.encode("utf-8"))
    packet = build_packet(request(), evidence_db)
    memories = [e for e in packet.evidence if e.channel == "video_transcript_memory"]
    assert len(memories) == 1 and memories[0].scope["market"] == "unknown"
    assert "original_transcript_json" not in json.dumps(model_payload(packet))
    assert packet.feedback_records == 2
