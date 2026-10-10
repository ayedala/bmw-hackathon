"""Streamlit PM workbench; delegate workflow rules to core application services."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import streamlit as st

from bmw_pm.contracts import DecisionAction
from bmw_pm.hosting import hosted_mode
from bmw_pm.decision import assess_ranking
from bmw_pm.review import ReviewService
from bmw_pm.storage import Database, RevisionConflict, WorkflowError


st.set_page_config(page_title="BMW Product Decision Lab", layout="wide")
st.markdown(
    """
    <style>
    .block-container { max-width: 1320px; padding-top: 2.6rem; padding-bottom: 5rem; }
    [data-testid="stSidebar"] { background: #f4f7fb; border-right: 1px solid #dfe6f0; }
    h1, h2, h3 { color: #14233b; letter-spacing: -.035em; }
    h1 { font-size: clamp(2.25rem, 4vw, 3.5rem) !important; line-height: 1.08 !important; }
    h2 { font-size: 1.6rem !important; }
    [data-testid="stMetric"] { border-top: 2px solid #1763d6; padding: 1rem 0 .25rem; }
    [data-testid="stMetricLabel"] { color: #53657e; }
    [data-testid="stMetricValue"] { color: #14233b; font-size: 1.65rem; }
    [data-testid="stTabs"] { margin-top: 1.25rem; }
    [data-testid="stTabs"] button { font-weight: 600; }
    [data-testid="stExpander"] { border: 1px solid #dfe6f0; border-radius: 8px; }
    .eyeline { color: #1763d6; font-size: .77rem; font-weight: 700; letter-spacing: .11em; text-transform: uppercase; }
    .subtle { color: #53657e; font-size: .95rem; }
    </style>
    """,
    unsafe_allow_html=True,
)
st.title("BMW Product Decision Lab")
st.markdown(
    '<p class="subtle">An evidence-to-decision workbench for customer outcomes, transparent value ranges, and PM review.</p>',
    unsafe_allow_html=True,
)

if hosted_mode():
    from hosting_access import require_hosted_access
    db_path = require_hosted_access()
else:
    db_path = Path(st.sidebar.text_input("SQLite database", "data/processed/bmw_pm.db"))
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
            Path("src/bmw_pm/data_pipeline/youtube_research/output"),
            Path("youtube_research_agent/output"),
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
                        profile=load_json(vehicle_profiles[selected_profile]),
                        policy=PolicyVersion.model_validate(load_json("configs/exploratory_equal_v1.json")),
                        provider=select_provider("baseline", baseline_config="configs/baseline_taxonomy_v1.json"),
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

summaries = database.requirement_summaries()

if not summaries:
    st.info(
        "No requirement candidates exist yet. Run `bmw-pm ingest` and then `bmw-pm run`. "
        "With no API key, the run is visibly labelled deterministic baseline—not AI."
    )
    st.stop()

from planning_view import portfolio, selected_planning
summaries, successor_proposals, priority_policy = portfolio(database, summaries)

ranking_assessment = assess_ranking(
    [item["score"] for item in summaries if item["score"] is not None]
)
st.markdown(f"**{len(summaries)} candidate outcomes**")
st.caption(
    f"Value comparisons resolved by non-overlapping ranges: "
    f"{len(ranking_assessment['resolved_value_pairs'])}; unresolved: "
    f"{len(ranking_assessment['unresolved_value_pairs'])}. "
    "Engineering feasibility must be reviewed separately."
)

labels = {
    item["requirement"].requirement_id: (
        f"{'/'.join(item['requirement'].scope.models)} · {item['requirement'].title} · r{item['requirement'].revision}"
    )
    for item in summaries
}
st.sidebar.markdown("### Requirement queue")
st.sidebar.caption("Compare ranks in the portfolio table. Selection stays on the same requirement when its priority changes.")
if st.session_state.get("selected_requirement") not in labels:
    st.session_state["selected_requirement"] = summaries[0]["requirement"].requirement_id
selected_id = st.sidebar.radio(
    "Requirement", options=sorted(labels), format_func=lambda key: labels[key], key="selected_requirement"
)
selected = next(
    item for item in summaries if item["requirement"].requirement_id == selected_id
)
requirement = selected["requirement"]
from bmw_pm.data_pipeline.context import source_acquisition_urls
original_source_urls = source_acquisition_urls(database)
score = selected["score"]
decision = selected["decision"]

status = decision.action.value if decision else requirement.lifecycle_status
run = database.run_manifest(score.run_id) if score else None
run_mode = run.provider.mode if run else "unknown"
mode_label = {
    "baseline_no_ai": "Deterministic baseline · no AI",
    "live_ai": "Live model extraction",
    "cached_replay": "Cached replay · no live inference",
}.get(run_mode, "Run mode unavailable")
st.markdown(f"**{mode_label}**")
st.markdown('<p class="eyeline">Selected customer outcome</p>', unsafe_allow_html=True)
st.header(requirement.customer_outcome)
st.caption(
    f"{requirement.title} · revision {requirement.revision} · {status} · "
    f"{requirement.requirement_id}"
)

selected_planning(database, requirement, successor_proposals, priority_policy, decision)

if score:
    left, middle, right = st.columns(3, gap="large")
    customer = score.dimension_intervals.get("customer")
    business = score.dimension_intervals.get("business")
    left.metric(
        "Customer value (scenario range)",
        f"{customer.lower_bound:.1f}–{customer.upper_bound:.1f}" if customer else "unavailable",
    )
    middle.metric(
        "Business value (scenario range)",
        f"{business.lower_bound:.1f}–{business.upper_bound:.1f}" if business else "unavailable",
    )
    right.metric("Engineering feasibility", score.feasibility_status.replace("_", " ").title())
    st.caption(
        f"Combined value range {score.lower_bound:.1f}–{score.upper_bound:.1f}; "
        f"feedback extraction coverage {score.coverage['processed_feedback_records']}/"
        f"{score.coverage['eligible_feedback_records']}. "
        "The list uses the lower value bound as an exploratory order; overlapping ranges are unresolved. "
        "Evidence claims await human entailment review; the equal-weight seed policy is unapproved. "
        "Ranges are scenarios, not measured probabilities."
    )

overview_tab, evidence_tab, scoring_tab, uncertainty_tab, history_tab = st.tabs(
    ["Overview", "Evidence", "Scoring", "Uncertainty", "History"]
)
with overview_tab:
    left, right = st.columns([1.5, 1], gap="large")
    with left:
        st.subheader("Outcome and validation")
        st.write(requirement.customer_outcome)
        st.markdown("**Use conditions**")
        if requirement.use_conditions:
            for condition in requirement.use_conditions:
                st.markdown(f"- {condition}")
        else:
            st.caption("No use conditions recorded.")
        st.markdown("**Proposed validation**")
        st.write(requirement.acceptance_proposal.method)
        st.caption(f"Target status: {requirement.target_status.replace('_', ' ')}")
    with right:
        st.subheader("Evidence scope")
        st.write("Models: " + (", ".join(requirement.scope.models) or "unknown"))
        st.write("Countries: " + (", ".join(requirement.scope.countries) or "unknown"))
        st.write("Powertrains: " + (", ".join(requirement.scope.powertrains) or "unknown"))
        st.write(f"Supporting feedback records: {requirement.support_count}")
        st.write(f"Praise / preservation records: {requirement.counter_count}")
        st.caption(
            f"Denominator: {requirement.denominator_feedback_records} unique feedback IDs "
            "in this supplied-file scope. IDs are records, not verified people."
        )
    st.divider()
    st.subheader("Run provenance")
    if run:
        st.write(
            f"{mode_label} · {run.provider.label} · run {run.run_id} · "
            f"vehicle profile {run.profile_id} r{run.profile_revision}"
        )
        if run.provider.model_id:
            st.caption(f"Model ID: {run.provider.model_id}; prompt version: {run.provider.prompt_version}")
        if run.replay_of_run_id:
            st.caption(f"Replay of {run.replay_of_run_id}; no new model inference is implied.")
    else:
        st.caption("No run manifest is linked to this revision's score snapshot.")
    st.caption("Reviewer IDs are declared, not verified personal identities.")
with evidence_tab:
    st.subheader("Combined evidence assessment")
    for statement in requirement.evidence_synthesis:
        st.write(statement)
    if requirement.cross_channel_evidence:
        channels = sorted({link.channel for link in requirement.cross_channel_evidence})
        channel = st.selectbox("Cross-channel evidence", channels)
        external = [link for link in requirement.cross_channel_evidence if link.channel == channel]
        page = st.number_input("Cross-channel page", min_value=1,
            max_value=max(1, (len(external) + 9) // 10), value=1)
        for link in external[(page - 1) * 10:page * 10]:
            with st.expander(f"{link.role.title()} · {link.claim[:110]}"):
                st.write(link.claim)
                if link.channel == "youtube":
                    st.link_button("Open video at cited timestamp", link.locator["url"])
                    st.write(link.locator["exact_quote"])
                else:
                    source_id = link.payload.get("source_id")
                    if source_id in original_source_urls:
                        st.link_button("Open original BMW source in Drive", original_source_urls[source_id])
                    if link.channel == "bmw_equipment":
                        st.write(link.locator.get("exact_quote", ""))
                st.caption(f"Applicability: {link.applicability}; semantic entailment: {link.semantic_entailment}")
                for limitation in link.limitations:
                    st.caption(limitation)
                st.json({"locator": link.locator, "original_evidence": link.payload})
    st.subheader("Trace the evidence")
    st.caption(
        "A checked text span locates source wording; semantic support is still unreviewed. "
        "Study observations are separate from feedback recurrence."
    )
    st.write(
        f"Study observations for selected models in database: {sum(database.survey_count(model=m) for m in requirement.scope.models)}; "
        "respondent counts unavailable."
    )
    roles = {
        "Supporting signals": requirement.supporting_signal_ids,
        "Praise / preservation": requirement.counter_signal_ids,
        "Ambiguous context": requirement.context_signal_ids,
    }
    role = st.radio("Evidence role", list(roles), horizontal=True)
    signal_ids = roles[role]
    if not signal_ids:
        st.info("No linked signals in this role. Zero linked signals do not establish no customer need.")
    else:
        page_size = 12
        page_count = (len(signal_ids) + page_size - 1) // page_size
        page = st.number_input("Page", min_value=1, max_value=page_count, value=1, step=1)
        page_ids = signal_ids[(page - 1) * page_size:page * page_size]
        rows = []
        for signal_id in page_ids:
            signal = database.signal(signal_id)
            locator = signal.evidence_spans[0].locator
            rows.append({
                "Signal ID": signal_id,
                "Polarity": signal.polarity.value,
                "Atomic claim": signal.atomic_claim,
                "Source locator": f"{locator.sheet}!{locator.cell_range}",
            })
        st.dataframe(rows, width="stretch", hide_index=True)
        st.caption(f"Showing {len(page_ids)} of {len(signal_ids)} linked signals in this role.")
        selected_signal_id = st.selectbox("Inspect exact source span", page_ids)
        signal = database.signal(selected_signal_id)
        span = signal.evidence_spans[0]
        if span.locator.source_id in original_source_urls:
            st.link_button("Open original feedback workbook in Drive", original_source_urls[span.locator.source_id])
        st.markdown("**Redacted source wording**")
        st.write(span.text)
        st.caption(
            f"{span.locator.sheet}!{span.locator.cell_range} · "
            f"source SHA-256 {span.locator.source_hash}"
        )
        st.caption(
            f"Provider mode: {signal.provider_mode}; source author expertise: unknown; "
            "semantic entailment: unreviewed."
        )
    st.warning(
        "Evidence shown here is locally redacted by a heuristic. Privacy review is still required before hosted inference or export."
    )

with scoring_tab:
    st.subheader("How this value range was calculated")
    st.caption(
        "Deterministic contributions come from recorded policy inputs. "
        "Unknown inputs retain their weight and widen the scenario range."
    )
    if not score:
        st.info("No score snapshot is linked to this revision.")
    else:
        rows = []
        for name, criterion in score.criterion_inputs.items():
            rows.append(
                {
                    "criterion": name.replace("_", " ").title(),
                    "input": f"{criterion.value:.1f}"
                    if criterion.value is not None
                    else (
                        f"{criterion.lower_value:.1f}–{criterion.upper_value:.1f}"
                        if criterion.lower_value is not None
                        else "unknown"
                    ),
                    "contribution interval": (
                        f"{score.contributions[name][0]:.1f}–"
                        f"{score.contributions[name][1]:.1f}"
                    ),
                    "basis / missing reason": criterion.basis or criterion.missing_reason,
                }
            )
        st.dataframe(rows, width="stretch", hide_index=True)
        st.caption(score.feasibility_basis)

with uncertainty_tab:
    st.subheader("What remains uncertain")
    st.markdown("**Assumptions**")
    for item in requirement.assumptions:
        st.write(f"- {item}")
    st.markdown("**Missing evidence**")
    for item in requirement.missing_evidence:
        st.write(f"- {item}")
    st.markdown("**Acceptance proposal**")
    st.write(requirement.acceptance_proposal.model_dump(mode="json"))
    st.markdown("**Implementation cost**")
    st.caption(requirement.implementation_cost_missing_reason)

with history_tab:
    replay = database.replay_requirement(requirement.requirement_id)
    st.subheader("Decision history")
    st.caption(
        f"Audit chain: {'valid' if replay['audit_valid'] else 'invalid'} · "
        f"checkpoint {replay['audit_checkpoint'][:16]}…"
    )
    if replay["decisions"]:
        for item in replay["decisions"]:
            st.write(
                f"Revision {item['requirement_revision']} · {item['action'].title()} · "
                f"{item['recorded_at']} · {item['rationale']}"
            )
    else:
        st.caption("No PM decisions recorded for this requirement.")
    with st.expander("Inspect full revision and decision records"):
        st.json({"revisions": replay["revisions"], "decisions": replay["decisions"]})

st.divider()
st.subheader("PM review")
st.caption(f"Decisions apply to stored revision {requirement.revision}: {requirement.title}. Adopt a successor draft first if that is the wording you intend to review. Record a rationale for every decision; edits create an immutable new revision.")
actor = st.text_input("Reviewer ID", "local-demo-pm")
reason = st.text_area("Decision rationale (required)")
service = ReviewService(database)
action_columns = st.columns(4)
actions = [
    ("Approve", DecisionAction.APPROVE),
    ("Reject", DecisionAction.REJECT),
    ("Challenge", DecisionAction.CHALLENGE),
    ("Defer", DecisionAction.DEFER),
]
for column, (label, action) in zip(action_columns, actions):
    if column.button(label, width="stretch"):
        try:
            service.decide(
                requirement_id=requirement.requirement_id,
                expected_revision=requirement.revision,
                action=action,
                rationale=reason,
                actor_id=actor,
                request_id=f"ui_{uuid4().hex}",
            )
            st.success(f"Recorded {action.value} for revision {requirement.revision}.")
            st.rerun()
        except (ValueError, WorkflowError, RevisionConflict) as exc:
            st.error(str(exc))

with st.expander("Edit into a new revision"):
    with st.form("edit_requirement"):
        title = st.text_input("Title", requirement.title)
        outcome = st.text_area("Customer outcome", requirement.customer_outcome)
        edit_reason = st.text_area("Edit rationale")
        conditions = st.text_area("Use conditions (one per line)", "\n".join(requirement.use_conditions))
        assumptions = st.text_area("Assumptions (one per line)", "\n".join(requirement.assumptions))
        validation_method = st.text_area("Proposed customer validation", requirement.acceptance_proposal.method)
        submitted = st.form_submit_button("Create new revision")
        if submitted:
            try:
                _, new_revision = service.edit(
                    requirement_id=requirement.requirement_id,
                    expected_revision=requirement.revision,
                    changes={"title": title, "customer_outcome": outcome,
                        "use_conditions": [x.strip() for x in conditions.splitlines() if x.strip()],
                        "assumptions": [x.strip() for x in assumptions.splitlines() if x.strip()],
                        "acceptance_proposal": {**requirement.acceptance_proposal.model_dump(), "method": validation_method}},
                    rationale=edit_reason,
                    actor_id=actor,
                    request_id=f"ui_{uuid4().hex}",
                )
                st.success(f"Created revision {new_revision.revision}; prior decisions remain frozen.")
                st.rerun()
            except (ValueError, WorkflowError, RevisionConflict) as exc:
                st.error(str(exc))
