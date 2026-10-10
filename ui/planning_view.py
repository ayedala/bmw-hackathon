"""PM-facing planning experience; keeps evidence, hypotheses and judgements distinct."""
from pathlib import Path
from uuid import uuid4
import json
import streamlit as st

from bmw_pm.contracts import PriorityFactors, PriorityPolicy
from bmw_pm.decision.planning import PriorityService, anchor_records, decision_brief, load_proposals, priority_score, proposal_for
from bmw_pm.review import ReviewService
from bmw_pm.storage import RevisionConflict, WorkflowError

CONFIGS = Path(__file__).resolve().parents[1] / "configs"


def audit(database, action, reason):
    with database.connect() as connection:
        database._append_audit(connection, actor_id="workbench-session", actor_type="demo_pm",
            action=action, object_type="planning_view", object_id="successor", object_revision=None,
            before_hash=None, after_hash=None, reason=reason, request_id=f"{action}:{uuid4().hex}", result="success")
        connection.commit()


def portfolio(database, summaries):
    proposals = load_proposals(CONFIGS / "successor_proposals_v1.json")
    st.subheader("Next-generation planning · 2029–2031")
    st.write("Primary demonstration: US 5 Series (G60). The supplied file has 3,610 US feedback IDs out of 4,000 G60 IDs, multiple powertrains, and linked studies, sales and equipment context. The 1 and 7 Series provide comparison scopes; their data does not automatically justify transferring a 5 Series proposal.")
    st.caption("2029–2031 is an assumed three-to-five-year planning window from October 2026, not a confirmed BMW launch. German equipment pages do not establish US fitment. Sales are family-level supplied values; 2030 is a planning scenario. No representative-customer prevalence is inferred.")
    scopes = ["G60 · US", "All available scopes"] if any(i["requirement"].scope.models == ["G60"] and i["requirement"].scope.countries == ["US"] for i in summaries) else ["All available scopes"]
    scope = st.selectbox("Decision portfolio scope", scopes)
    if scope != "All available scopes":
        summaries = [i for i in summaries if i["requirement"].scope.models == ["G60"] and i["requirement"].scope.countries == ["US"]]
    with st.expander("Priority method and what-if weights", expanded=False):
        st.write("Score = 25 × [impact × weight + evidence × weight + market relevance × weight + (4 − uncertainty) × weight]. Ratings run from 0 to 4. Uncertainty reduces priority; it is not a calibrated probability. Seed ratings and weights are illustrative judgements, not verified BMW preferences.")
        st.caption("Impact: 0 no meaningful benefit, 2 useful convenience, 4 major everyday benefit. Evidence: 0 unsupported, 2 traceable reports with unreviewed interpretation, 4 independent converging reviewed evidence. Relevance: 0 outside scope, 2 plausible niche, 4 demonstrated fit to selected customers. Uncertainty: 0 key assumptions tested, 2 material gaps, 4 speculative. Potentially severe reports require separate review regardless of their score.")
        weights = {}
        for name, default in [("impact",35),("evidence",25),("relevance",25),("uncertainty",15)]:
            weights[name] = st.slider(f"{name.title()} weight", 0, 100, default, key=f"weight_{name}")
        if sum(weights.values()) == 0:
            st.warning("All weights are zero. Using the labelled seed policy until a positive weight is selected.")
            policy = PriorityPolicy()
        else:
            policy = PriorityPolicy(**{name: value/sum(weights.values()) for name,value in weights.items()})
        st.caption(f"Normalized weights: {policy.model_dump()}. Changes preview the whole portfolio immediately. Save a selected card's assessment to retain its ratings, weights and rationale.")
    audit(database, "read_planning_portfolio", f"Opened {scope} with weights {policy.model_dump()}")
    service = PriorityService(database)
    decorated = []
    for item in summaries:
        req = item["requirement"]
        proposal = proposal_for(database, req, proposals)
        current = [p for p in service.history(req.requirement_id) if p.requirement_revision == req.revision]
        latest = current[-1] if current else None
        factors = latest.factors if latest else proposal.factors if proposal else None
        value = priority_score(factors, policy) if factors else None
        decorated.append((value, req.requirement_id, item, proposal, factors, latest))
    decorated.sort(key=lambda row: (-(row[0] if row[0] is not None else -1), row[1]))
    rows = []
    for value, _, item, proposal, factors, latest in decorated:
        req = item["requirement"]
        rank = 1 + sum(other[0] is not None and value is not None and other[0] > value for other in decorated) if value is not None else None
        rows.append({"Rank (ties retained)":rank, "Proposal / theme":proposal.title if proposal else req.title,
            "Scope": "/".join(req.scope.models)+" · "+",".join(req.scope.countries),
            "Priority what-if":value, "Impact":factors.impact if factors else None,
            "Evidence":factors.evidence if factors else None, "Market fit":factors.relevance if factors else None,
            "Uncertainty":factors.uncertainty if factors else None,
            "Basis":"Saved PM ratings" if latest else "Illustrative seed" if factors else "Not yet rated",
            "Review":item["decision"].action.value if item["decision"] else "Not decided"})
    st.dataframe(rows, hide_index=True, width="stretch")
    st.caption("Ranks compare ratings under the same current weights. Ties are real ties. Broad-theme recurrence below is a separate evidence signal; it is not the fraction of customers needing a specific proposed feature. Unrated comparison scopes stay unranked.")
    with st.expander("External research and source coverage"):
        st.write("Customer studies inform context, not respondent counts. Equipment-page keyword matches are discovery context pending derivative/market review. Sales contextualize the selected market without changing individual impact ratings. YouTube findings are used only when validated against saved transcripts.")
        youtube = sum(x.channel == "youtube" for i in summaries for x in i["requirement"].cross_channel_evidence)
        st.info(f"Validated YouTube links in this portfolio: {youtube}. " + ("The saved discovery run has no usable transcript findings; this is missing evidence, not absence of customer need." if not youtube else "Inspect the Evidence tab for exact video references."))
        for source in json.loads((CONFIGS / "planning_public_context.json").read_text(encoding="utf-8")):
            st.markdown(f"**[{source['title']}]({source['url']})**")
            st.write(source["observation"])
            st.caption(source["use"] + " Retrieved 10 October 2026; curated page summary, not a full archived document.")
    with st.expander("Walkthrough · evidence → proposal → human decision"):
        st.write("1. Select Controls Usability in the requirement queue. Read G60-0271: the driver reports distracting airflow controls and was unaware of the existing voice capability.")
        st.write("2. Compare the proposed persistent-access requirement with G60-0092's climate praise. Separate the observed complaint from the interpretation (access/discoverability) and the future assumption (the need persists in 2029–2031).")
        st.write("3. Enter a reviewer ID and adopt the draft as a new revision, or edit it yourself. Re-rate the revised proposal and save a rationale. Change the weights to see the portfolio consequence.")
        st.write("4. Approve conditionally, reject or challenge using PM review. Inspect History: the decision references the exact revision and saved priority assessment. No approval is prefilled as a real BMW decision.")
        st.caption("For a pre-recorded illustrative decision, run scripts/demo_successor.py. It writes a separate demo database and report; the working BMW database is not modified.")
    with st.expander("Export the decision brief"):
        if st.button("Prepare private decision brief"):
            audit(database, "prepare_planning_export", f"Prepared private brief for {scope}; includes source excerpts and declared PM judgements")
            st.session_state["planning_export"] = (str(database.path), decision_brief(database, [row[2] for row in decorated], proposals, policy))
        exported = st.session_state.get("planning_export")
        if exported and exported[0] == str(database.path):
            st.download_button("Download prepared Markdown snapshot", exported[1], file_name="bmw-successor-decision-brief.md", mime="text/markdown",
                on_click=lambda: audit(database, "download_planning_export", "Downloaded the previously prepared private decision brief snapshot"))
            st.caption("The snapshot contains private source excerpts. Keep it in the authorized team workspace. Prepare again after changing evidence, ratings or decisions.")
    return [row[2] for row in decorated], proposals, policy


def selected_planning(database, requirement, proposals, policy, decision):
    proposal = proposal_for(database, requirement, proposals)
    service = PriorityService(database)
    history = service.history(requirement.requirement_id)
    current = [p for p in history if p.requirement_revision == requirement.revision]
    latest = current[-1] if current else None
    with st.expander("Successor proposal and editable priority", expanded=False):
        actor = st.text_input("Planning reviewer ID", "", key="planning_reviewer")
        if proposal:
            st.subheader(proposal.title)
            if requirement.customer_outcome != proposal.outcome:
                st.info(f"This successor draft is a proposal alongside stored revision {requirement.revision}. Adopt it or edit the requirement before approving this exact wording. Priority saves and PM decisions always apply to the stored revision.")
            st.write("**Proposed requirement — authored hypothesis:** " + proposal.outcome)
            st.write("**Customer value:** " + proposal.value)
            st.write("**Interpretation of observed evidence:** " + proposal.interpretation)
            st.write("**Future assumption:** " + proposal.future_assumption)
            st.write("**Conflicting signals / trade-off:** " + proposal.contrary)
            st.write("**Proposed validation:** " + proposal.validation)
            st.caption("Revisit when: " + proposal.review_trigger)
            for record in anchor_records(database, proposal):
                st.markdown(f"**Observed anchor: {record.source_record_id}**")
                st.write(record.redacted_text)
                st.caption(record.raw_text_ref + " · " + record.row_locators[0].source_hash)
            adopt_reason = st.text_input("Rationale for adopting the successor draft")
            if st.button("Adopt draft as new requirement revision", disabled=not actor.strip() or not adopt_reason.strip()):
                try:
                    ReviewService(database).edit(requirement_id=requirement.requirement_id,
                        expected_revision=requirement.revision, changes={"title":proposal.title,
                        "customer_outcome":proposal.outcome,
                        "assumptions":[*requirement.assumptions, "Authored successor hypothesis; broad-theme counts are not feature-specific prevalence.", proposal.future_assumption],
                        "acceptance_proposal":{"method":proposal.validation}, "target_status":"proposed_target"},
                        rationale=adopt_reason, actor_id=actor, request_id=f"adopt:{uuid4().hex}")
                    st.session_state.pop("planning_export", None)
                    st.rerun()
                except (ValueError, RevisionConflict, WorkflowError) as error:
                    st.error(str(error))
        else:
            st.caption("No authored successor draft is supplied for this scope. Edit the requirement below and rate it explicitly; the US G60 hypothesis is not transferred automatically.")
        seed = latest.factors if latest else proposal.factors if proposal else PriorityFactors(impact=2,evidence=0,relevance=2,uncertainty=4)
        key = f"{requirement.requirement_id}:{requirement.revision}:{latest.sequence if latest else 0}"
        with st.form(f"priority:{key}"):
            inputs = {}
            for name in ("impact","evidence","relevance","uncertainty"):
                inputs[name] = st.slider(f"Priority {name}",0,4,getattr(seed,name),key=f"{name}:{key}")
            rationale = st.text_area("Priority rationale (required)", key=f"rationale:{key}")
            save = st.form_submit_button("Save priority assessment")
        if save:
            try:
                service.save(requirement_id=requirement.requirement_id, expected_revision=requirement.revision,
                    expected_sequence=latest.sequence if latest else 0, factors=inputs, policy=policy,
                    actor_id=actor, rationale=rationale, request_id=f"priority:{uuid4().hex}")
                st.session_state.pop("planning_export", None)
                st.rerun()
            except (ValueError, RevisionConflict, WorkflowError) as error:
                st.error(str(error))
        st.write(f"Priority preview under current weights: **{priority_score(PriorityFactors(**inputs),policy):.1f}/100**")
        if latest:
            st.caption(f"Saved assessment {latest.sequence}: {latest.score:.1f}/100 under weights {latest.policy.model_dump()} · {latest.actor_id} · {latest.rationale}")
        else:
            st.caption("No saved priority for this revision. Displayed seed ratings are illustrative assumptions until a PM records their judgement.")
        if decision:
            st.caption(f"Current decision references priority: {decision.priority_assessment_id or 'none saved at decision time'}. Later priority changes do not rewrite that decision.")
        if history:
            with st.expander("All saved priority assessments"):
                st.json([item.model_dump(mode="json") for item in history])
