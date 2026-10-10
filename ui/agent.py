"""Guided product decisions: idea assessment, discovery and comparison."""
from __future__ import annotations

import os
import re
from decimal import Decimal
from pathlib import Path

import pandas as pd
import streamlit as st

from bmw_pm.advisor.contracts import AdvisorRequest, AdvisorResult, Claim, EvidenceItem
from bmw_pm.advisor.evidence import ROOT
from bmw_pm.advisor.finance import ScenarioInput, scenario_results
from bmw_pm.advisor.provider import AdvisorProvider, DEFAULT_MODEL, safe_url
from bmw_pm.advisor.service import run_advisor
from bmw_pm.advisor.settings import project_credentials
from bmw_pm.hosting import hosted_mode
from bmw_pm.intelligence.provider import ProviderError

VEHICLES = {"BMW 1 Series · F70": "F70", "BMW 5 Series · G60": "G60", "BMW 7 Series · G70": "G70"}
MARKETS = {"United States": "US", "United Kingdom": "GB", "Germany": "DE", "China": "CN", "Japan": "JP", "South Korea": "KR"}
JOURNEYS = {"Assess my idea": "idea", "Find the next improvement": "improve", "Compare several ideas": "compare"}


def _plain_markdown(value: str) -> str:
    # Do not render model/evidence instructions, links or tracking images as markup.
    return re.sub(r"([\\`*_{}\[\]()<>#+.!|~-])", r"\\\1", value)


def render_claim(claim: Claim, evidence: dict[str, EvidenceItem]) -> None:
    labels = {"evidence": "Sourced claim · review pending", "inference": "Agent assessment",
              "assumption": "Assumption to test", "unknown": "Evidence gap"}
    st.caption(labels[claim.basis])
    st.markdown(_plain_markdown(claim.text))
    if claim.explanation:
        st.caption(_plain_markdown(claim.explanation))
    for ref in dict.fromkeys(claim.evidence_ids):
        item = evidence[ref]
        url = item.locator.get("url")
        if isinstance(url, str) and safe_url(url):
            st.markdown(f"[{_plain_markdown(item.title)}](<{url}>) · `{ref}`")
        else:
            st.caption(f"Source: {item.title} · {ref}")


def render_evidence(item: EvidenceItem) -> None:
    with st.expander(f"{item.title} · {item.evidence_id}"):
        st.caption(item.channel.replace("_", " ").title())
        st.text(item.text)
        st.write("**Why this was selected**")
        st.text(item.selection_reason)
        st.json(item.scope, expanded=False)
        for limitation in item.limitations:
            st.caption(_plain_markdown(limitation))
        url = item.locator.get("url")
        if isinstance(url, str) and safe_url(url):
            st.link_button("Open original source", url)
        st.json(item.locator, expanded=False)


def render_finance(result: AdvisorResult) -> None:
    request = result.packet.request
    st.subheader("Test the business case")
    st.write("Enter sourced estimates or your own hypothetical assumptions. Blank values stay unknown.")
    options = {option.option_id: option.title for option in result.report.options}
    selected = st.selectbox("Idea to model", list(options), format_func=options.get, key=f"finance_option_{result.run_id}")
    prefix = f"finance_{result.run_id}_{selected}"
    numeric = [field for field in ScenarioInput.model_fields if field != "scenario"]
    frame = pd.DataFrame([{ "scenario": name, **{field: None for field in numeric}}
                          for name in ("Downside", "Base", "Upside")])
    st.caption(f"Currency: {request.currency}. Values repeat annually over {request.planning_years} years. Sales scope: {request.model_code} / {request.market}. Adoption is a fraction from 0 to 1.")
    with st.form(prefix):
        table = st.data_editor(frame, hide_index=True, disabled=["scenario"], key=f"{prefix}_table",
            column_config={
                "scenario": "Scenario", "upfront_cost": st.column_config.NumberColumn("Development / tooling", min_value=0),
                "annual_fixed_cost": st.column_config.NumberColumn("Annual support cost", min_value=0),
                "baseline_units": st.column_config.NumberColumn("Existing annual sales", min_value=0, step=1),
                "incremental_units": st.column_config.NumberColumn("Added annual sales", min_value=0, step=1),
                "adoption_rate": st.column_config.NumberColumn("Adoption (0–1)", min_value=0, max_value=1),
                "revenue_per_extra_vehicle": st.column_config.NumberColumn("Revenue / added vehicle", min_value=0),
                "cost_per_extra_vehicle": st.column_config.NumberColumn("Vehicle cost / added vehicle", min_value=0),
                "revenue_uplift_per_adopter": st.column_config.NumberColumn("Feature revenue / existing adopter", min_value=0),
                "feature_cost_per_adopter": st.column_config.NumberColumn("Feature cost / equipped vehicle", min_value=0),
            }, use_container_width=True)
        source = st.text_input("Estimate source / owner (or write ‘hypothetical scenario’)")
        discount = st.number_input("Discount rate (%)", min_value=0.0, max_value=99.0, value=10.0,
                                   help="A scenario assumption, not an approved company discount rate.")
        calculate = st.form_submit_button("Calculate scenario outcomes")
    if calculate:
        try:
            rows = scenario_results(table.to_dict("records"), years=request.planning_years,
                                    discount_rate=Decimal(str(discount)) / 100, source=source)
            st.session_state[f"{prefix}_result"] = rows
        except ValueError:
            st.session_state.pop(f"{prefix}_result", None)
            st.error("Complete every numeric field in all three scenarios, including explicit zeros, and name the assumption source. Adoption must be 0–1; unit counts must be whole numbers.")
    if f"{prefix}_result" in st.session_state:
        st.dataframe(st.session_state[f"{prefix}_result"], hide_index=True, use_container_width=True)
        st.caption("NPV discounts annual cash flows and deducts upfront cost. These are conditional scenarios, not forecasts or approvals.")


def render_result(result: AdvisorResult) -> None:
    request, report = result.packet.request, result.report
    evidence = {item.evidence_id: item for item in [*result.packet.evidence, *result.research.sources]}
    st.divider()
    st.caption(f"LIVE AI RESEARCH · {request.model_code} / {request.market} / {request.powertrain} · {result.created_at[:19]}")
    st.subheader(report.headline)
    st.markdown(_plain_markdown(report.summary))
    preferred = next((option for option in report.options if option.option_id == report.preferred_option_id), None)
    st.info(f"Provisional preference: {preferred.title}" if preferred else "The evidence does not establish a preferred option yet.")
    tabs = st.tabs(["Decision brief", "Customer evidence", "Market research", "Costs & revenue", "How it was built"])
    with tabs[0]:
        render_claim(report.recommendation, evidence)
        for option in report.options:
            with st.container(border=True):
                st.subheader(option.title)
                st.markdown(_plain_markdown(option.proposal))
                if request.journey == "compare":
                    index = int(option.option_id.split("_")[1]) - 1
                    st.caption(f"Your idea: {request.ideas[index]}")
                st.write("**Customer value**")
                for claim in option.customer_case:
                    render_claim(claim, evidence)
                with st.expander("Can it be built and shipped?"):
                    render_claim(option.feasibility, evidence)
                    st.write("**Proposed delivery path**")
                    for index, step in enumerate(option.delivery_steps, 1):
                        st.markdown(f"{index}. {_plain_markdown(step)}")
                    st.write("**Risks and release gates**")
                    for text in [*option.risks, *option.validation_needed]:
                        st.markdown(f"- {_plain_markdown(text)}")
                with st.expander("Competitor implementations"):
                    for claim in option.competitors:
                        render_claim(claim, evidence)
                with st.expander("Cost and revenue outlook"):
                    render_claim(option.cost_outlook, evidence)
                    render_claim(option.revenue_outlook, evidence)
        st.write("**Why this option, and what could change the choice**")
        for claim in report.comparison:
            render_claim(claim, evidence)
        if report.follow_up_questions:
            with st.chat_message("assistant"):
                st.write("These answers would help refine the decision:")
                for question in report.follow_up_questions:
                    st.markdown(f"- {_plain_markdown(question)}")
    with tabs[1]:
        st.metric("Feedback records in this scope", f"{result.packet.feedback_records:,}")
        st.caption("Unique feedback IDs, not verified people. Topic counts use the existing keyword baseline; the LLM assesses selected evidence.")
        st.dataframe([{"Topic": topic.domain.replace("_", " "), "Support": topic.supporting_records,
                       "Praise": topic.praise_records, "Mixed / context": topic.context_records,
                       "Applicable records": topic.eligible_records} for topic in result.packet.topics], hide_index=True)
        for item in result.packet.evidence:
            if item.channel != "corpus_summary":
                render_evidence(item)
    with tabs[2]:
        st.caption("Current public research. Citation links come from the search response; applicability and claim meaning remain reviewable.")
        text = _plain_markdown(result.research.text)
        for item in result.research.sources:
            marker = _plain_markdown(f"[{item.evidence_id}]")
            text = text.replace(marker, f"[{item.evidence_id}](<{item.locator['url']}>)")
        st.markdown(text)
        for item in result.research.sources:
            render_evidence(item)
    with tabs[3]:
        for option in report.options:
            st.write(f"**{_plain_markdown(option.title)}**")
            render_claim(option.cost_outlook, evidence)
            render_claim(option.revenue_outlook, evidence)
        render_finance(result)
    with tabs[4]:
        st.write("**Completed steps**")
        for index, step in enumerate(result.steps, 1):
            st.write(f"{index}. {step}")
        st.write("**Research focus**")
        st.text(result.plan.rationale)
        for question in result.plan.research_questions:
            st.markdown(f"- {_plain_markdown(question)}")
        st.write("**Limits that affect the recommendation**")
        for limitation in result.packet.limitations:
            st.markdown(f"- {_plain_markdown(limitation)}")
        with st.expander("Search activity and run provenance"):
            st.json({"run_id": result.run_id, "model": result.model_id, "prompt_version": result.prompt_version,
                     "input_hash": result.packet.fingerprint, "usage": result.usage, "search_actions": result.research.search_actions})
    st.download_button("Download decision brief (JSON)", result.model_dump_json(indent=2),
                       file_name=f"bmw-{request.model_code}-decision.json", mime="application/json")


def main() -> None:
    st.set_page_config(page_title="BMW Decision Studio", page_icon="◈", layout="wide")
    st.markdown("""<style>
    .block-container {max-width: 1180px; padding-top: 2.2rem; padding-bottom: 4rem;}
    h1 {letter-spacing: -.045em; font-weight: 750;}
    h2,h3 {letter-spacing: -.025em;}
    [data-testid="stSidebar"] {background: #f3f6fa;}
    [data-testid="stMetric"] {padding: 1rem; border-left: 3px solid #1769e0;}
    [data-testid="stForm"] {border-radius: 14px; padding: 1.3rem;}
    div.stButton > button[kind="primary"] {background: #1769e0; border-color: #1769e0;}
    </style>""", unsafe_allow_html=True)
    database = ROOT / "data/processed/bmw_pm.db"
    if hosted_mode():
        from hosting_access import require_hosted_access
        database = Path(require_hosted_access())
    with st.sidebar:
        st.subheader("Decision Studio")
        st.caption("Evidence → market research → product decision")
        with st.expander("Agent settings"):
            saved_credentials = project_credentials()
            connections = (["Saved project research connection"] if saved_credentials else []) + ["Server environment", "Enter an API key"]
            connection = st.selectbox("API connection", connections)
            model_id = st.text_input("LLM model", value=os.getenv("BMW_PM_OPENAI_MODEL") or DEFAULT_MODEL)
            api_key = st.text_input("OpenAI API key", type="password") if connection == "Enter an API key" else None
            project_id = None
            if connection == "Saved project research connection" and saved_credentials:
                api_key, project_id = saved_credentials.api_key, saved_credentials.project_id
                st.caption(f"Using the connection stored in {saved_credentials.origin}. The key stays on the server.")
            st.caption("Live research uses your API project and incurs provider usage charges.")
        st.caption("Dataset available" if database.is_file() else "Dataset missing — import the supplied files")
        if st.button("Start a new decision", use_container_width=True):
            st.session_state.pop("advisor_result", None)
            st.session_state.pop("advisor_error", None)
            st.rerun()
    st.caption("BMW PRODUCT INTELLIGENCE")
    st.title("What should we build next?")
    st.write("Explore an idea, uncover an opportunity, or compare your options—with customer evidence and current market research.")
    with st.chat_message("assistant"):
        st.write("First, tell me what you want to decide. I’ll check customer needs, research competitors, and build a reviewable recommendation.")
    journey_label = st.radio("What would you like to do?", list(JOURNEYS), horizontal=True,
                            captions=["Test feasibility, demand and economics", "Discover an opportunity for a model", "Evaluate 2–5 ideas on the same basis"])
    journey = JOURNEYS[journey_label]
    c1, c2, c3 = st.columns(3)
    with c1:
        vehicle = st.selectbox("Which BMW?", list(VEHICLES), index=1)
    code = VEHICLES[vehicle]
    with c2:
        market = st.selectbox("Target market", list(MARKETS), index=1 if code == "F70" else 0, key=f"market_{code}")
    with c3:
        powertrain = st.selectbox("Powertrain", ["ICE"] if code == "F70" else ["ALL", "ICE", "PHEV", "BEV"], key=f"powertrain_{code}")
    with st.form("decision_request"):
        ideas: list[str] = []
        question = ""
        if journey == "idea":
            question = st.text_area("Describe your idea", placeholder="For example: add tactile shortcuts for climate control while retaining the touchscreen.", height=110, max_chars=4000)
        elif journey == "compare":
            raw = st.text_area("Enter one idea per line (2–5 ideas)", height=140,
                               placeholder="Add tactile shortcuts for climate controls\nImprove voice control for common driving tasks\nAdd a configurable steering-wheel shortcut", max_chars=5000)
            ideas = [line.strip() for line in raw.splitlines() if line.strip()]
        else:
            question = st.text_area("Any area to focus on? (optional)", placeholder="Leave this open to compare customer needs across the vehicle, or focus on software, comfort, charging…", max_chars=2000)
        objective = st.selectbox("What matters most?", ["Balanced customer value and business potential", "Customer satisfaction and retention", "Revenue and profitable growth", "Competitive differentiation"])
        constraints = st.text_input("Constraints or answers to the agent's follow-up questions (optional)", max_chars=800)
        a, b, c = st.columns(3)
        with a:
            model_year = st.number_input("Model year to research", min_value=2020, max_value=2040, value=2026)
        with b:
            years = st.number_input("Planning horizon (years)", min_value=1, max_value=10, value=3)
        with c:
            currency = st.selectbox("Business-case currency", ["EUR", "USD", "GBP"])
        budget = st.number_input("Development budget cap (optional)", min_value=0.0, value=None, step=100000.0)
        st.caption("Research sends selected redacted database excerpts to OpenAI for analysis. Web search receives your idea and public research questions. The report shows source selection and assumptions.")
        run = st.form_submit_button("Research and assess", type="primary", use_container_width=True)
    if run:
        st.session_state.pop("advisor_result", None)
        st.session_state.pop("advisor_error", None)
        try:
            request = AdvisorRequest(journey=journey, model_code=code, market=MARKETS[market], powertrain=powertrain,
                                     model_year=model_year, question=question, ideas=ideas,
                                     objective=objective + (f". Constraints: {constraints}" if constraints else ""),
                                     planning_years=years, currency=currency, budget=budget or None)
            if connection == "Enter an API key" and not api_key:
                raise ValueError("Enter an API key in Agent settings.")
            provider = AdvisorProvider(model_id=model_id.strip(), api_key=api_key or None, project_id=project_id)
            with st.status("Building your decision brief…", expanded=True) as status:
                result = run_advisor(request, database, provider, progress=st.write)
                st.session_state["advisor_result"] = result.model_dump(mode="json")
                status.update(label="Decision brief ready", state="complete", expanded=False)
        except (ValueError, ProviderError) as exc:
            st.session_state["advisor_error"] = str(exc)
        except Exception:
            st.session_state["advisor_error"] = "The research run could not finish. Check the local database and provider configuration; no completed recommendation was generated."
    if error := st.session_state.get("advisor_error"):
        st.error(error)
    if saved := st.session_state.get("advisor_result"):
        render_result(AdvisorResult.model_validate(saved))
    else:
        st.caption("Current coverage: BMW 1 Series F70, 5 Series G60, and 7 Series G70. Additional models can be added when their evidence is available.")


if __name__ == "__main__":
    main()
