"""Chronological, real backend events with revision and priority comparisons."""
from html import escape
import streamlit as st
from bmw_pm.decision.planning import PriorityService

def render_audit(database, requirement):
    valid, checkpoint = database.verify_audit_chain()
    st.caption(f'{requirement.title} · r{requirement.revision} · UTC timestamps · declared reviewer identities')
    if valid:
        st.success(f"Audit chain verified · checkpoint {checkpoint[:16]}…")
    else:
        st.error(f"Audit verification failed: {checkpoint}")
    events = [e for e in database.audit_events() if e.object_id == requirement.requirement_id]
    if not events:
        st.info("No audit events have been recorded for this requirement.")
        return
    table, detail = st.columns([0.58, 0.42], gap="large")
    with table, st.container(border=True, key="audit-events"):
        st.subheader("Chronological events")
        event_id = st.selectbox("Inspect audit event", [e.event_id for e in reversed(events)],
            format_func=lambda value: next(f"{e.recorded_at:%Y-%m-%d %H:%M} UTC · {e.action.replace('_', ' ').title()} · {e.actor_id}" for e in events if e.event_id == value),
            key=f"audit_event_{requirement.requirement_id}")
        st.dataframe([{"Time (UTC)": e.recorded_at.strftime("%Y-%m-%d %H:%M:%S"), "Actor": e.actor_id,
            "Change": e.action.replace("_", " ").title(), "Revision": e.object_revision, "Rationale": e.reason} for e in events],
            hide_index=True, width="stretch")
    event = next(e for e in events if e.event_id == event_id)
    with detail, st.container(border=True, key="audit-detail"):
        st.caption(f"{event.event_id} · {event.recorded_at:%Y-%m-%d %H:%M:%S} UTC")
        st.subheader(event.action.replace("_", " ").title())
        st.caption(f"{event.actor_id} · {event.actor_type} · {event.result}")
        st.markdown("**PM rationale / event reason**")
        st.write(event.reason)
        priorities = PriorityService(database).history(requirement.requirement_id)
        current = next((p for p in priorities if p.request_id == event.request_id), None)
        if current:
            previous = next((p for p in priorities if p.requirement_revision == current.requirement_revision and p.sequence == current.sequence - 1), None)
            st.divider()
            st.markdown("**Before → after**")
            st.write(f"Priority: {previous.score if previous else 'Not rated'} → {current.score:.1f} / 100")
            st.caption(f"Requirement r{current.requirement_revision} · assessment {current.sequence}")
            st.dataframe([{"Factor": name.title(), "Before": getattr(previous.factors, name) if previous else None,
                "After": getattr(current.factors, name), "Saved weight": getattr(current.policy, name)}
                for name in ("impact", "evidence", "relevance", "uncertainty")], hide_index=True, width="stretch")
            st.caption("These are recorded PM judgements; source evidence is unchanged by a priority assessment.")
        if event.object_revision:
            revision = database.requirement(requirement.requirement_id, event.object_revision)
            st.divider()
            st.markdown(f"**Customer outcome · stored r{revision.revision}**")
            st.write(revision.customer_outcome)
            if revision.supersedes_revision:
                prior = database.requirement(requirement.requirement_id, revision.supersedes_revision)
                if prior.customer_outcome != revision.customer_outcome:
                    st.caption(f"Before · r{prior.revision}")
                    st.write(prior.customer_outcome)
        with st.expander("Inspect event hashes and full record"):
            st.json(event.model_dump(mode="json"))
    st.caption("Append-only, hash-linked audit events. Saved decisions and priority assessments retain their original revision references.")
