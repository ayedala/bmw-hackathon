"""Draft ranking preview; PM saves and requirement decisions remain explicit."""
from uuid import uuid4
import streamlit as st
from bmw_pm.contracts import PriorityPolicy
from bmw_pm.decision.planning import decision_brief, planning_order
from bmw_pm.decision.drafts import ROOT
from bmw_pm.decision.planning import load_proposals
from draft_view import selected_planning


def audit(database, action, reason):
    with database.connect() as connection:
        database._append_audit(connection, actor_id="workbench-session", actor_type="demo_pm",
            action=action, object_type="planning_view", object_id="draft-planning", object_revision=None,
            before_hash=None, after_hash=None, reason=reason, request_id=f"{action}:{uuid4().hex}", result="success")
        connection.commit()


def portfolio(database, summaries):
    st.subheader("Next-generation decision portfolio")
    st.info("Future requirements and AI priorities are provisional drafts. Exact quotations, interpretations and future assumptions are separate. Only explicit reviewer actions can adopt, approve, reject or confirm a priority.")
    st.caption("Demonstration: US BMW 5 Series (G60), 2029–2031 scenario, chosen for matching US feedback plus study, sales and equipment context. Scope mismatches and missing evidence remain visible. No future launch commitment.")
    proposals=load_proposals(ROOT / "configs/successor_proposals_v1.json")
    scopes=["All available scopes"]+sorted({"/".join(i["requirement"].scope.models)+" · "+",".join(i["requirement"].scope.countries) for i in summaries})
    scope=st.selectbox("Decision portfolio scope",scopes,index=scopes.index("G60 · US") if "G60 · US" in scopes else 0)
    if scope!=scopes[0]:
        summaries=[i for i in summaries if "/".join(i["requirement"].scope.models)+" · "+",".join(i["requirement"].scope.countries)==scope]
    with st.expander("PM priority policy · explicit input required"):
        st.write("AI provisional policy: impact 35%, evidence 25%, relevance 25%, uncertainty 15%. PM weights below start blank. Change them to preview an alternative ranking; save and explicitly confirm separately.")
        weights={name:st.slider(f"{name.title()} weight",0,100,key=f"evidence_weight_{name}") for name in ("impact","evidence","relevance","uncertainty")}
        total=sum(weights.values())
        policy=PriorityPolicy(**{name:value/total for name,value in weights.items()}) if total else None
        st.caption("Formula: 25 × [impact × weight + evidence × weight + relevance × weight + (4 − uncertainty) × weight]. Positive weights normalize. AI suggestions, unsaved previews, PM draft assessments and confirmed priorities remain distinct.")
    decorated=planning_order(database,summaries,proposals,policy)
    rows=[]
    for score,item,latest,draft in decorated:
        req=item["requirement"]
        preview=bool(latest and policy and not latest.criteria and policy != latest.policy)
        rows.append({"Requirement":req.title,"Stored outcome":req.customer_outcome,"Revision":req.revision,
            "Supporting feedback IDs":req.support_count,"Preservation feedback IDs":req.counter_count,
            "Eligible feedback IDs":req.denominator_feedback_records,"Context links":len(req.cross_channel_evidence),
            "Provisional score /100":score,"Future draft":draft.proposal.title if draft else "No anchored draft for scope",
            "Manual PM rank":latest.rank_override if latest else None,
            "Saved PM score":latest.score if latest else None,
            "Saved PM priority status":("Confirmed by reviewer" if latest.priority_confirmed else "Draft only") if latest else "None",
            "Priority basis":("What-if preview — not confirmed" if preview else ("Saved PM confirmed policy" if latest.priority_confirmed else "PM-entered draft")) if latest else ("AI provisional — not PM approved" if score is not None else "Unknown — no PM rating"),
            "Decision":item["decision"].action.value if item["decision"] else "Not decided"})
    st.dataframe(rows,hide_index=True,width="stretch")
    st.caption("Display order: manual PM rank first, then score, with stable IDs breaking ties. Different custom criteria may yield incomparable scores; use a shared policy for comparison. Weight changes only preview rankings and never change saved confirmation.")
    st.caption("Counts are feedback records, not verified people, prevalence or severity. Topic/polarity classifications are unreviewed; unconfirmed mappings and scope mismatches are not verified facts.")
    audit(database,"read_planning_portfolio",f"Draft scope {scope}; PM preview policy {policy.model_dump() if policy else 'not supplied'}")
    with st.expander("Export source-backed review snapshot"):
        if st.button("Prepare private decision brief"):
            audit(database,"prepare_planning_export",f"Draft decision snapshot: {scope}")
            st.session_state["planning_export"]=(str(database.path),decision_brief(database,[x[1] for x in decorated],proposals,policy))
        exported=st.session_state.get("planning_export")
        if exported and exported[0]==str(database.path):
            st.download_button("Download prepared Markdown snapshot",exported[1],file_name="bmw-evidence-review.md",mime="text/markdown",on_click=lambda:audit(database,"download_planning_export","Downloaded private evidence snapshot"))
            st.caption("Private snapshot; regenerate after changes. Historical assumptions remain history, not endorsed facts.")
    return [x[1] for x in decorated],proposals,policy
