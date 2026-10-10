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
st.title("BMW Product Decision Lab")
st.caption(
    "Evidence-to-requirement prototype. Reviewer IDs are declared and are not verified personal identities."
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
with st.expander("Imported evidence context", expanded=False):
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
selected_id = st.sidebar.selectbox(
    "Requirement", options=list(labels), format_func=lambda key: labels[key]
)
selected = next(
    item for item in summaries if item["requirement"].requirement_id == selected_id
)
requirement = selected["requirement"]
score = selected["score"]
decision = selected["decision"]

status = decision.action.value if decision else requirement.lifecycle_status
st.subheader(requirement.customer_outcome)
st.write(
    {
        "status": status,
        "requirement_id": requirement.requirement_id,
        "revision": requirement.revision,
        "scope": requirement.scope.model_dump(mode="json"),
        "feasibility": requirement.feasibility,
        "implementation_cost": "unknown",
    }
)

if score:
    left, middle, right = st.columns(3)
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
    right.metric("Engineering feasibility", score.feasibility_status)
    st.caption(
        f"Combined value range {score.lower_bound:.1f}–{score.upper_bound:.1f}; "
        f"feedback extraction coverage {score.coverage['processed_feedback_records']}/"
        f"{score.coverage['eligible_feedback_records']}. "
        "The list uses the lower value bound as an exploratory order; overlapping ranges are unresolved. "
        "Evidence claims await human entailment review; the equal-weight seed policy is unapproved."
    )

evidence_tab, scoring_tab, uncertainty_tab, history_tab = st.tabs(
    ["Evidence", "Scoring", "Uncertainty", "History"]
)
with evidence_tab:
    st.write(
        {
            "supporting_unique_feedback_records": requirement.support_count,
            "praise_or_preservation_unique_feedback_records": requirement.counter_count,
            "denominator_unit": "unique feedback IDs in the selected supplied-file scope",
            "denominator": requirement.denominator_feedback_records,
            "customer_study_observations_in_database_for_G60": database.survey_count(model="G60"),
        }
    )
    st.caption(
        "Study observations are a separate evidence channel and are not added to feedback recurrence. "
        "Respondent counts are unavailable."
    )
    for role, ids in (
        ("Supporting signals", requirement.supporting_signal_ids),
        ("Praise / preservation signals", requirement.counter_signal_ids),
        ("Ambiguous or descriptive context", requirement.context_signal_ids),
    ):
        with st.expander(f"{role} ({len(ids)})", expanded=False):
            for signal_id in ids:
                signal = database.signal(signal_id)
                span = signal.evidence_spans[0]
                st.write(
                    {
                        "polarity": signal.polarity.value,
                        "redacted_evidence": span.text,
                        "locator": (
                            f"{span.locator.sheet}!{span.locator.cell_range} · "
                            f"source sha256 {span.locator.source_hash}"
                        ),
                        "provider_mode": signal.provider_mode,
                        "source_author_expertise": "unknown",
                        "semantic_entailment": "unreviewed",
                    }
                )
    st.warning(
        "Evidence shown here is locally redacted by a heuristic. Privacy review is still required before hosted inference or export."
    )

with scoring_tab:
    if not score:
        st.info("No score snapshot is linked to this revision.")
    else:
        rows = []
        for name, criterion in score.criterion_inputs.items():
            rows.append(
                {
                    "criterion": name,
                    "input": criterion.value
                    if criterion.value is not None
                    else (
                        [criterion.lower_value, criterion.upper_value]
                        if criterion.lower_value is not None
                        else "unknown"
                    ),
                    "contribution interval": score.contributions[name],
                    "basis / missing reason": criterion.basis or criterion.missing_reason,
                }
            )
        st.dataframe(rows, use_container_width=True, hide_index=True)
        st.caption(score.feasibility_basis)

with uncertainty_tab:
    st.markdown("**Assumptions**")
    for item in requirement.assumptions:
        st.write(f"- {item}")
    st.markdown("**Missing evidence**")
    for item in requirement.missing_evidence:
        st.write(f"- {item}")
    st.markdown("**Acceptance proposal**")
    st.write(requirement.acceptance_proposal.model_dump(mode="json"))

with history_tab:
    replay = database.replay_requirement(requirement.requirement_id)
    st.write(
        {
            "audit_chain_valid": replay["audit_valid"],
            "audit_checkpoint": replay["audit_checkpoint"],
        }
    )
    st.json({"revisions": replay["revisions"], "decisions": replay["decisions"]})

st.divider()
st.subheader("PM review")
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
    if column.button(label, use_container_width=True):
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
