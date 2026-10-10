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
    from bmw_pm.ingestion.legacy_database import evidence_context
    channels = ["sales_observation", "equipment_fact", "external_claim",
        "web_research_seed", "benchmark_vehicle", "source_document"]
    if not hosted_mode():
        channels.append("source_locator")
    context_table = st.selectbox("Evidence channel", channels)
    st.caption("Imported context retains original scope and locators. Claims await entailment review; context does not automatically change scores.")
    if st.button("Read evidence context"):
        st.json([row.model_dump(mode="json") for row in evidence_context(database, context_table)])

summaries = database.requirement_summaries()

if not summaries:
    st.info(
        "No requirement candidates exist yet. Run `bmw-pm ingest` and then `bmw-pm run`. "
        "With no API key, the run is visibly labelled deterministic baseline—not AI."
    )
    st.stop()

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
        f"{item['requirement'].title} · r{item['requirement'].revision}"
    )
    for item in summaries
}
st.sidebar.markdown("### Requirement queue")
st.sidebar.caption("Exploratory order by lower value bound; overlapping ranges remain unresolved.")
selected_id = st.sidebar.radio(
    "Requirement", options=list(labels), format_func=lambda key: labels[key]
)
selected = next(
    item for item in summaries if item["requirement"].requirement_id == selected_id
)
requirement = selected["requirement"]
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
    st.subheader("Trace the evidence")
    st.caption(
        "A checked text span locates source wording; semantic support is still unreviewed. "
        "Study observations are separate from feedback recurrence."
    )
    st.write(
        f"G60 study observations in database: {database.survey_count(model='G60')}; "
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
st.caption("Record a rationale for every decision. Edits create an immutable new revision.")
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
        submitted = st.form_submit_button("Create new revision")
        if submitted:
            try:
                _, new_revision = service.edit(
                    requirement_id=requirement.requirement_id,
                    expected_revision=requirement.revision,
                    changes={"title": title, "customer_outcome": outcome},
                    rationale=edit_reason,
                    actor_id=actor,
                    request_id=f"ui_{uuid4().hex}",
                )
                st.success(f"Created revision {new_revision.revision}; prior decisions remain frozen.")
                st.rerun()
            except (ValueError, WorkflowError, RevisionConflict) as exc:
                st.error(str(exc))
