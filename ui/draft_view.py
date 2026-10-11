"""Reviewable successor synthesis, separate from evidence and human decisions."""
from uuid import uuid4
import streamlit as st
from bmw_pm.contracts import PriorityFactors, PriorityPolicy
from bmw_pm.decision.planning import PriorityService, priority_score, load_proposals
from bmw_pm.decision.drafts import ROOT, DEFAULT_POLICY, generate_draft, read_draft, adopt_draft
from bmw_pm.storage import RevisionConflict, WorkflowError


def draft_for(database,req,proposals):
    return read_draft(database,req.successor_draft_id) if req.successor_draft_id else generate_draft(database,req,proposals)


def show_draft(database, requirement, draft, actor):
    if draft is None:
        return
    p=draft.proposal
    st.subheader("Future-facing draft · not approved")
    st.write(p.outcome)
    st.write("Proposed customer value: " + p.value)
    st.caption(draft.method + " " + draft.planning_window + "; snapshot " + draft.draft_id)
    with st.expander("1. Exact source records and observed counts"):
        st.write(f"Theme classifications: {requirement.support_count} supporting and {requirement.counter_count} preservation feedback IDs / {requirement.denominator_feedback_records} eligible IDs. Not proposal-specific prevalence or verified people.")
        for record in draft.quoted_records:
            st.caption(f"Source {record.source_record_id}; country {record.raw_country}; supplied powertrain {record.powertrain_raw}")
            st.code(record.redacted_text,language=None)
            st.json([x.model_dump(mode="json") for x in record.row_locators])
            if record.powertrain_raw == "BEVE" or record.powertrain_mapping_status != "exact":
                st.warning(f"Ambiguous supplied label {record.powertrain_raw}: preserved exactly; meaning requires data-owner review.")
            for label,raw,normalized in (("country",record.raw_country,record.country),("model",record.raw_model,record.model_code)):
                if raw and raw != normalized:
                    st.warning(f"Supplied {label} '{raw}' differs from normalized '{normalized}'. Raw label retained; confirm applicability before relying on it.")
    st.write("2. AI interpretation (not quotation): " + p.interpretation)
    st.write("3. Future assumption / scenario (not fact): " + p.future_assumption)
    st.write("4. Conflicting / preservation signals: " + p.contrary)
    st.write("Proposed validation (no agreed numeric target): " + p.validation)
    st.write("Revisit when: " + p.review_trigger)
    with st.expander("Unknowns and contextual evidence limitations"):
        for unknown in draft.unknowns:
            st.write(unknown)
        st.caption("Exact BMW study/sales/equipment and available video context remains in the Evidence tab; resolving a span is not semantic corroboration.")
        for context in draft.external_context:
            st.markdown(f"[{context['title']}]({context['url']})")
            st.write("Authored context summary (not quotation): " + context["observation"])
            st.caption(context["use"] + " " + context["status"])
    st.subheader("AI provisional priority · not PM approved")
    st.dataframe([{"Criterion":name,"AI rating /4":rating,"AI weight":getattr(draft.priority_policy,name),"Reason":draft.priority_explanations[name]} for name,rating in p.factors.model_dump().items()],hide_index=True)
    st.write(f"AI draft score: {priority_score(p.factors,draft.priority_policy):.2f}/100")
    reason=st.text_area("Draft adoption rationale (required)")
    if not requirement.successor_draft_id and st.button("Adopt draft as reviewable revision"):
        try:
            adopt_draft(database,draft,actor_id=actor,rationale=reason,request_id=f"adopt:{uuid4().hex}")
            st.session_state.pop("planning_export",None)
            st.rerun()
        except (ValueError,RevisionConflict,WorkflowError) as error:
            st.error(str(error))
    elif requirement.successor_draft_id:
        st.caption("Reviewer adopted this snapshot. Stored wording may contain subsequent PM edits; inspect History. Adoption is not approval.")


def selected_planning(database,requirement,proposals,policy,decision):
    service=PriorityService(database)
    history=service.history(requirement.requirement_id)
    current=[x for x in history if x.requirement_revision==requirement.revision and x.input_origin=="explicit_pm"]
    latest=current[-1] if current else None
    actor=st.text_input("Planning reviewer ID",placeholder="Enter reviewer ID")
    draft=draft_for(database,requirement,proposals)
    show_draft(database,requirement,draft,actor)
    key=f"{requirement.requirement_id}:{requirement.revision}:{latest.sequence if latest else 0}"
    if draft:
        def seed():
            for name,rating in draft.proposal.factors.model_dump().items():
                st.session_state[f"{name}:{key}"]=rating
                st.session_state[f"evidence_weight_{name}"]=round(100*getattr(draft.priority_policy,name))
        st.button("Use AI suggestion as editable draft inputs",on_click=seed)
    with st.expander("PM priority · editable draft or explicit confirmation",expanded=True):
        st.caption("Seeded values remain AI suggestions until explicitly saved with reviewer identity and rationale. Saving a draft is neither priority confirmation nor requirement approval.")
        with st.form(f"priority:{key}"):
            inputs={name:st.number_input(f"Priority {name}",min_value=0,max_value=4,value=None,step=1,key=f"{name}:{key}") for name in ("impact","evidence","relevance","uncertainty")}
            use_custom=st.checkbox("Use my custom criteria instead of the four-factor method",value=bool(latest and latest.criteria))
            custom=st.data_editor([x.model_dump() for x in latest.criteria] if latest and latest.criteria else [
                {"name":"Customer value","rating":0.0,"weight":1.0,"direction":"benefit","explanation":""}],
                num_rows="dynamic",hide_index=True,key=f"criteria:{key}",
                column_config={"rating":st.column_config.NumberColumn("Rating /4",min_value=0,max_value=4),
                    "weight":st.column_config.NumberColumn("Weight",min_value=0),
                    "direction":st.column_config.SelectboxColumn("Direction",options=["benefit","risk"])})
            st.caption("Add, remove or rename criteria above; edit ratings, weights and explanations. Enable the checkbox to use this table. Higher risk ratings reduce the score. Placeholder values are not recommendations.")
            rank=st.number_input("Manual portfolio rank (0 = score order)",min_value=0,value=(latest.rank_override or 0) if latest else 0,step=1)
            rationale=st.text_area("Priority rationale (required)",key=f"rationale:{key}")
            confirmed=st.checkbox("I explicitly confirm this priority as the reviewer",value=False)
            save=st.form_submit_button("Save priority assessment")
        if save:
            try:
                criteria=custom if use_custom else []
                if use_custom and not criteria:
                    raise ValueError("Add at least one custom criterion")
                if not criteria and policy is None:
                    raise ValueError("Enter priority weights first. No default policy is applied.")
                if not criteria and any(value is None for value in inputs.values()):
                    raise ValueError("Enter every PM rating explicitly; missing inputs stay unknown.")
                service.save(requirement_id=requirement.requirement_id,expected_revision=requirement.revision,
                    expected_sequence=max((x.sequence for x in history if x.requirement_revision==requirement.revision),default=0),
                    factors=PriorityFactors(**inputs) if not criteria else PriorityFactors(impact=0,evidence=0,relevance=0,uncertainty=4),
                    policy=policy or DEFAULT_POLICY,criteria=criteria,rank_override=rank or None,priority_confirmed=confirmed,
                    actor_id=actor,rationale=rationale,request_id=f"priority:{uuid4().hex}")
                st.session_state.pop("planning_export",None)
                st.rerun()
            except (ValueError,RevisionConflict,WorkflowError) as error:
                st.error(str(error))
        if latest:
            st.write(f"Saved PM {'confirmed priority' if latest.priority_confirmed else 'draft priority'}: {latest.score:.1f}/100")
            st.caption(f"Reviewer: {latest.actor_id}; rationale: {latest.rationale}; assessment {latest.assessment_id}")
        else:
            st.write("PM priority: unknown — awaiting explicit reviewer input.")
        if decision:
            st.caption(f"Decision assessment reference: {decision.priority_assessment_id or 'none'}; requirement decision and priority confirmation are separate.")
        if history:
            with st.expander("Historical PM assessments"):
                st.json([x.model_dump(mode="json") for x in history])
    return max((x.sequence for x in history if x.requirement_revision==requirement.revision),default=0)
