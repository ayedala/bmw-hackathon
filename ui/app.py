"""Figma workbench, connected to the existing BMW decision engine."""
from __future__ import annotations

from pathlib import Path
from html import escape
from uuid import uuid4
import os
import json
import streamlit as st

from bmw_pm.hosting import hosted_mode
from bmw_pm.contracts import PriorityPolicy
from bmw_pm.decision import assess_ranking
from bmw_pm.decision.planning import load_proposals, planning_order, decision_brief
from bmw_pm.data_pipeline.context import source_acquisition_urls
from bmw_pm.storage import Database
from bmw_pm.storage.config import database_target, is_postgres
from workbench_theme import apply_theme, brand, page_intro, badge, workflow, source_row
from workbench_views import render_evidence, render_priority, render_review, render_history_records
from planning_view import audit
from youtube_research_view import render as render_youtube_research
from feature_cost_view import render_feature_cost

ROOT = Path(__file__).resolve().parents[1]
CONFIGS = ROOT / "configs"
st.set_page_config(page_title="BMW Product Decision Lab", layout="wide", initial_sidebar_state="collapsed")
apply_theme()

if hosted_mode():
    from hosting_access import require_hosted_access
    db_path = require_hosted_access()
else:
    with st.sidebar.expander("Workspace settings", expanded=False):
        configured_db = database_target(root=ROOT)
        if is_postgres(configured_db):
            st.caption("Shared PostgreSQL database configured in the server environment.")
            db_path = configured_db
        else:
            default_db = Path(os.environ.get("BMW_PM_DATABASE", str(configured_db)))
            db_path = Path(st.text_input("SQLite database", str(default_db)))
database = Database(db_path)
database.initialize()
if hosted_mode():
    with database.connect() as connection:
        database._append_audit(connection, actor_id="shared-team-access", actor_type="pipeline",
            action="read_hosted_workbench", object_type="database", object_id="canonical",
            object_revision=None, before_hash=None, after_hash=None,
            reason="Authenticated team session opened the decision/evidence review surface.",
            request_id=f"hosted-view:{uuid4().hex}", result="success")
        connection.commit()
with st.sidebar.expander("Imported evidence context", expanded=False):
    from bmw_pm.data_pipeline.legacy_database import evidence_context
    channels = ["sales_observation", "equipment_fact", "external_claim",
        "web_research_seed", "benchmark_vehicle", "source_document"]
    if not hosted_mode():
        channels.append("source_locator")
    context_table = st.selectbox("Evidence channel", channels)
    st.caption("Imported context retains original scope and locators. Claims await entailment review; context does not automatically change scores.")
    if st.button("Read evidence context"):
        st.json([row.model_dump(mode="json") for row in evidence_context(database, context_table)])

with st.sidebar.expander("Combined engine", expanded=False):
    st.caption("Combine BMW feedback, studies, imported context and saved YouTube findings into versioned requirement cards.")
    if not hosted_mode():
        saved_runs = sorted({str(p.parent) for root in (
            ROOT / "src/bmw_pm/data_pipeline/youtube_research/output",
            ROOT / "youtube_research_agent/output",
        ) for p in root.glob("*/evidence.json")})
        selected_runs = st.multiselect("YouTube research runs", saved_runs, default=saved_runs)
        vehicle_profiles = {"BMW 5 Series (G60)": "configs/g60.json", "BMW 1 Series (F70)": "configs/f70.json", "BMW 7 Series (G70)": "configs/g70.json"}
        selected_profile = st.selectbox("Vehicle research scope", list(vehicle_profiles))
        if st.button("Build combined results"):
            from bmw_pm.contracts import PolicyVersion
            from bmw_pm.intelligence.provider import select_provider
            from bmw_pm.pipeline import load_json, run_candidate_pipeline
            try:
                with st.spinner("Validating evidence and building combined results..."):
                    combined = run_candidate_pipeline(database=database,
                        profile=load_json(ROOT / vehicle_profiles[selected_profile]),
                        policy=PolicyVersion.model_validate(load_json(ROOT / "configs/exploratory_equal_v1.json")),
                        provider=select_provider("baseline", baseline_config=ROOT / "configs/baseline_taxonomy_v1.json"),
                        youtube_runs=selected_runs)
                st.success(f"Built {len(combined['requirements'])} combined cards. BMW extraction: deterministic baseline; saved YouTube extraction retains its original provenance.")
                if combined["unlinked_youtube_findings"]:
                    st.warning(f"{len(combined['unlinked_youtube_findings'])} YouTube findings need manual theme/scope alignment.")
                    st.json(combined["unlinked_youtube_findings"])
                for report in combined["youtube_imports"]:
                    if report["rejected"]:
                        st.warning(f"{len(report['rejected'])} invalid findings excluded.")
                    if not report["accepted"]:
                        st.warning("This YouTube run contains no validated findings. Discovery alone cannot support requirements.")
            except (ValueError, OSError) as error:
                st.error(str(error))
    else:
        st.caption("Combined cards are prepared locally and included in the private database upload.")



all_summaries = database.requirement_summaries()
with st.container(key="app-header"):
    identity, vehicle_slot, market_slot = st.columns([5, 2, 2], vertical_alignment="center")
    with identity:
        brand()
    models = sorted({m for item in all_summaries for m in item["requirement"].scope.models})
    preferred_model = models.index("G60") if "G60" in models else len(models)
    model = vehicle_slot.selectbox("Vehicle", [*models, "All vehicles"], index=preferred_model, key="vehicle_scope",
        format_func=lambda value: {"G60": "BMW 5 Series (G60)", "F70": "BMW 1 Series (F70)", "G70": "BMW 7 Series (G70)"}.get(value, value))
    available = [i for i in all_summaries if model == "All vehicles" or model in i["requirement"].scope.models]
    markets = sorted({m for item in available for m in item["requirement"].scope.countries})
    if st.session_state.get("market_scope") not in [*markets, "All markets"]:
        st.session_state["market_scope"] = "US" if "US" in markets else "All markets"
    market = market_slot.selectbox("Market", [*markets, "All markets"], key="market_scope",
        format_func=lambda value: {"US": "United States", "DE": "Germany", "CN": "China", "EU": "Europe"}.get(value, value))
summaries = [i for i in available if market == "All markets" or market in i["requirement"].scope.countries]

with st.container(key="app-navigation"):
    navigation, disclosure = st.columns([7, 3], vertical_alignment="center")
    destination = navigation.radio("Workspace", ["Decision desk", "Data & AI findings", "YouTube research", "Audit trail"],
        horizontal=True, label_visibility="collapsed", key="destination")
    disclosure.markdown('<div class="disclosure">Evidence-grounded proposals · human decisions</div>', unsafe_allow_html=True)

with st.sidebar.expander("Priority method and what-if weights", expanded=False):
    st.caption("AI draft policy: impact 35%, evidence 25%, relevance 25%, uncertainty 15%. PM weights start blank. Seed suggestions explicitly, or enter weights below to preview a different ranking. No preview confirms a priority.")
    weights = {name: st.slider(f"{name.title()} weight", 0, 100, key=f"evidence_weight_{name}")
        for name in ("impact", "evidence", "relevance", "uncertainty")}
    total = sum(weights.values())
    priority_policy = PriorityPolicy(**{name: value / total for name, value in weights.items()}) if total else None
    if not total:
        st.caption("No PM preview policy supplied. Cards show AI provisional scores or the saved PM assessment under its own policy.")
    st.caption("25 × [impact × weight + evidence × weight + relevance × weight + (4 − uncertainty) × weight].")

subtitles = {
    "Decision desk": "Review the customer outcome. Inspect the source. Own the priority.",
    "Data & AI findings": "From source records to linked signals, with human assessment at the boundaries.",
    "YouTube research": "Discover video evidence, verify transcript-backed findings, and connect them to BMW data.",
    "Audit trail": "Follow the source, interpretation and human rationale through every revision.",
}
page_intro(destination, subtitles[destination])
if destination == "YouTube research":
    render_youtube_research(database, ROOT, hosted=hosted_mode())
    st.stop()
if not summaries:
    st.info("No requirement candidates exist in this scope. Choose another vehicle or market, or ingest sources and build results from Workspace settings.")
    st.stop()

successor_proposals = load_proposals(CONFIGS / "successor_proposals_v1.json")
ordered = planning_order(database, summaries, successor_proposals, priority_policy)
summaries = []
for value,item,latest,draft in ordered:
    req = item["requirement"]
    proposal = draft.proposal if draft else None
    factors = latest.factors if latest else proposal.factors if proposal else None
    preview = bool(latest and priority_policy and not latest.criteria and priority_policy != latest.policy)
    basis = ("Unsaved preview · not confirmed" if preview else "PM confirmed priority" if latest.priority_confirmed else "PM draft priority") if latest else "AI provisional · not PM approved" if draft else "Unrated"
    item.update(proposal=proposal, draft=draft, priority_assessment=latest, priority_factors=factors,
        priority_value=value, priority_basis=basis,
        display_title=proposal.title if proposal and not req.successor_draft_id else req.title,
        display_outcome=proposal.outcome if proposal and not req.successor_draft_id else req.customer_outcome)
    summaries.append(item)
ids = [i["requirement"].requirement_id for i in summaries]
if st.session_state.get("selected_requirement") not in ids:
    st.session_state["selected_requirement"] = ids[0]
selected = next(i for i in summaries if i["requirement"].requirement_id == st.session_state["selected_requirement"])
requirement, score, decision = selected["requirement"], selected["score"], selected["decision"]
run = database.run_manifest(score.run_id) if score else None
mode_label = {"baseline_no_ai": "Feedback extraction: deterministic baseline · no live model call", "live_ai": "Live model extraction",
    "cached_replay": "Cached replay · no live inference"}.get(run.provider.mode if run else "", "No score run linked to this revision")
status = decision.action.value if decision else requirement.lifecycle_status
linked_signal_ids = set(requirement.supporting_signal_ids + requirement.counter_signal_ids + requirement.context_signal_ids)
judgments = database.latest_evidence_judgments(requirement.requirement_id, requirement.revision)
reviewed_link_count = len(linked_signal_ids & judgments.keys())
original_source_urls = source_acquisition_urls(database)
ranking_assessment = assess_ranking([i["score"] for i in summaries if i["score"] is not None])
view_signature = (str(database.path), destination, requirement.requirement_id, requirement.revision)
if st.session_state.get("view_audit_signature") != view_signature:
    with database.connect() as connection:
        database._append_audit(connection, actor_id="workbench-session", actor_type="demo_pm",
            action="view_requirement", object_type="requirement", object_id=requirement.requirement_id,
            object_revision=requirement.revision, before_hash=None, after_hash=None,
            reason=f"Opened {destination} for the selected requirement; no decision or rating changed.",
            request_id=f"view:{uuid4().hex}", result="success")
        connection.commit()
    st.session_state["view_audit_signature"] = view_signature

def select_requirement(requirement_id):
    st.session_state["selected_requirement"] = requirement_id
    st.session_state.pop("planning_export", None)

def change_destination(value):
    st.session_state["destination"] = value

def proposal_selector():
    st.selectbox("Requirement", ids, format_func=lambda value: next(i["requirement"].title for i in summaries if i["requirement"].requirement_id == value), key="selected_requirement")

if destination == "Decision desk":
    queue, detail = st.columns([0.37, 0.63], gap="large")
    with queue:
        with st.container(border=True, height=760, key="proposal-queue"):
            st.subheader("Proposed requirements")
            st.caption(f"Priority ↓ · {len(summaries)} proposals · {model} / {market}")
            search = st.text_input("Search proposals", placeholder="Search title, outcome or ID…", key="proposal_search")
            visible = [i for i in summaries if search.casefold() in (i["display_title"] + " " + i["display_outcome"] + " " + i["requirement"].requirement_id).casefold()]
            if not visible:
                st.info("No proposals match your search.")
            for item in visible:
                req = item["requirement"]
                active = req.requirement_id == requirement.requirement_id
                with st.container(key=f"proposal-{'selected' if active else req.requirement_id}"):
                    value = f'{item["priority_value"]:.1f}' if item["priority_value"] is not None else "—"
                    st.markdown(f'<div class="proposal-meta"><span>{escape(req.requirement_id)} · r{req.revision}</span><strong>{value}</strong></div>', unsafe_allow_html=True)
                    st.button(item["display_title"], key=f"select_{req.requirement_id}", width="stretch", on_click=select_requirement, args=(req.requirement_id,))
                    st.markdown(f'<p class="proposal-outcome">{escape(item["display_outcome"])}</p>', unsafe_allow_html=True)
                    item_status = item["decision"].action.value if item["decision"] else req.lifecycle_status
                    basis = item["priority_basis"]
                    st.markdown(f'<div class="proposal-footer"><span>{escape(basis)}</span>{badge(item_status)}</div>', unsafe_allow_html=True)
    with detail:
        with st.container(border=True, key="selected-review"):
            st.markdown(f'<div class="review-identity"><span>{escape(selected["display_title"])} · stored r{requirement.revision}</span>{badge(status)}</div>'
                f'<h2 class="outcome-title">{escape(selected["display_outcome"])}</h2>', unsafe_allow_html=True)
            if selected["draft"] and not requirement.successor_draft_id:
                st.caption("AI future-facing draft · not adopted or approved. Human adoption creates a new reviewable revision; decisions always apply to stored wording.")
            if selected["draft"]:
                st.caption("US BMW 5 Series · 2029–2031 planning scenario, not a launch commitment. Future interpretations and assumptions are labelled below; observations do not establish future demand.")
            st.caption(mode_label)
            st.divider()
            st.subheader("Inspect the evidence")
            st.write(f"{requirement.support_count} supporting records · {requirement.counter_count} praise / preservation records · {requirement.denominator_feedback_records} feedback IDs in scope")
            st.caption(f"{reviewed_link_count} of {len(linked_signal_ids)} candidate links assessed. Record counts do not establish customer prevalence.")
            if requirement.evidence_synthesis:
                st.write(requirement.evidence_synthesis[0])
            st.button("Inspect sources and assess links →", key="open_evidence", on_click=change_destination, args=("Data & AI findings",))
            st.divider()
            st.subheader("Priority, with its assumptions")
            factors = selected["priority_factors"]
            if factors and not (selected["priority_assessment"] and selected["priority_assessment"].criteria):
                saved = selected["priority_assessment"]
                st.markdown(f'<div class="score-explanation"><strong>{selected["priority_value"]:.1f} / 100</strong>'
                    f'<span>Impact {factors.impact} · Evidence {factors.evidence} · Market fit {factors.relevance} · Uncertainty {factors.uncertainty}</span>'
                    f'<small>{escape(selected["priority_basis"])} · ratings 0–4 · weights and reasoning below</small></div>', unsafe_allow_html=True)
                if saved:
                    st.caption(f"Stored assessment {saved.sequence}: {saved.score:.1f}/100 under its saved weights. Decisions keep that assessment reference.")
            elif selected["priority_assessment"] and selected["priority_assessment"].criteria:
                st.write(f'{selected["priority_value"]:.1f}/100 · {selected["priority_basis"]} · custom criteria')
            else:
                st.info("This revision has no priority rating. Save an assessment below.")
            priority_sequence = render_priority(database, requirement, score, decision, ranking_assessment, successor_proposals, priority_policy)
            render_feature_cost(requirement, ROOT)
            st.divider()
            render_review(database, requirement, run, mode_label, reviewed_link_count, linked_signal_ids,
                expected_priority_sequence=priority_sequence, needs_adoption=bool(selected["draft"] and not requirement.successor_draft_id))
            st.button("View audit trail →", key="open_history", on_click=change_destination, args=("Audit trail",))
    with st.expander("Compare portfolio and export a decision brief"):
        st.dataframe([{"Proposal": i["display_title"], "Revision": i["requirement"].revision, "Provisional score": i["priority_value"],
            "Basis": i["priority_basis"],
            "Saved PM score": i["priority_assessment"].score if i["priority_assessment"] else None,
            "PM priority confirmed": i["priority_assessment"].priority_confirmed if i["priority_assessment"] else False,
            "Manual PM rank": i["priority_assessment"].rank_override if i["priority_assessment"] else None,
            "Decision": i["decision"].action.value if i["decision"] else "Not decided"} for i in summaries], hide_index=True, width="stretch")
        st.caption("Manual PM rank first, then provisional score; ties use stable IDs. Custom policies may be incomparable. US G60 2029–2031 is a scenario, not a launch commitment. AI scores, PM draft assessments and confirmed priorities are separate; none approves a requirement.")
        export_policy = priority_policy.model_dump() if priority_policy else None
        if st.button("Prepare private decision brief"):
            audit(database, "prepare_planning_export", "Prepared a scoped private brief with source excerpts and PM judgements")
            st.session_state["planning_export"] = (str(database.path), tuple(ids), export_policy, decision_brief(database, summaries, successor_proposals, priority_policy))
        exported = st.session_state.get("planning_export")
        if exported and exported[:3] == (str(database.path), tuple(ids), export_policy):
            st.download_button("Download prepared Markdown snapshot", exported[3], "bmw-successor-decision-brief.md", mime="text/markdown",
                on_click=lambda: audit(database, "download_planning_export", "Downloaded the prepared private decision brief snapshot"))
            st.caption("This snapshot contains private source excerpts. Prepare it again after changing evidence, ratings or decisions.")

elif destination == "Data & AI findings":
    workflow(mode_label)
    proposal_selector()
    intake, enrichment = st.columns(2, gap="large")
    with intake, st.container(border=True, key="source-intake"):
        st.subheader("Source intake")
        with database.connect() as connection:
            sources = connection.execute("SELECT source_id, payload_json FROM sources ORDER BY source_id").fetchall()
        st.caption(f"{len(sources)} imported source documents · full database inventory")
        source_page = st.number_input("Source inventory page", min_value=1, max_value=max(1, (len(sources) + 7) // 8), value=1)
        for row in sources[(source_page - 1) * 8:source_page * 8]:
            source = json.loads(row["payload_json"])
            source_row(source, original_source_urls.get(row["source_id"]))
        if not sources:
            st.caption("No source documents have been imported.")
        st.caption("Original source hashes and row/page locators are retained. Records are not verified people.")
    with enrichment, st.container(border=True, key="web-enrichment"):
        st.subheader("Web enrichment")
        external_links = requirement.cross_channel_evidence
        st.write(f"{len(external_links)} linked cross-channel observations")
        st.caption("Imported studies, equipment, sales and validated YouTube findings retain their applicability and limitations. They do not automatically confirm a requirement.")
        st.write("Channels: " + (", ".join(sorted({x.channel for x in external_links})) or "No external evidence linked"))
        with st.expander("Research context and limitations"):
            for source in json.loads((CONFIGS / "planning_public_context.json").read_text(encoding="utf-8")):
                st.markdown(f"**[{source['title']}]({source['url']})**")
                st.write(source["observation"])
                st.caption(source["use"])
    with st.container(border=True, key="evidence-review"):
        render_evidence(database, requirement, judgments, reviewed_link_count, linked_signal_ids, original_source_urls)
else:
    proposal_selector()
    from workbench_audit import render_audit
    render_audit(database, requirement)
    with st.expander("Full revision, decision and evidence assessment records"):
        render_history_records(database, requirement)
