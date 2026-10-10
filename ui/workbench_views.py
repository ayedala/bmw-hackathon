"""Review views reuse the existing evidence, scoring and immutable review services."""
from html import escape
from uuid import uuid4
import streamlit as st
from bmw_pm.contracts import DecisionAction
from bmw_pm.review import ReviewService
from bmw_pm.storage import RevisionConflict, WorkflowError
from planning_view import selected_planning

def render_review(database, requirement, run, mode_label, reviewed_link_count, linked_signal_ids,
                  expected_priority_sequence=None, needs_adoption=False):
    st.subheader("Record a PM decision")
    st.caption(
        f"Only {reviewed_link_count} of {len(linked_signal_ids)} candidate links have a recorded human "
        "assessment for this revision. The ranking policy is exploratory and unapproved; "
        "engineering feasibility remains a separate review."
    )
    if needs_adoption:
        st.info("Adopt the future-facing draft as a reviewable revision before approving, rejecting or deferring it. You can then edit the wording, assess its priority and record a decision.")
    st.caption(
        "Review the evidence and priority limits before deciding. Actions apply to "
        f"revision {requirement.revision} and enter the audit history."
    )
    actor = st.text_input(
        "Reviewer ID (declared, not verified)", "",
        key=f"reviewer_{requirement.requirement_id}_{requirement.revision}",
    )
    st.caption("Shared app access does not verify the identity entered here.")
    reason = st.text_area(
        "Decision rationale (required)", height=90,
        key=f"review_reason_{requirement.requirement_id}_{requirement.revision}",
    )
    acknowledge = st.checkbox(
        "For approval: I reviewed the evidence and accept the unresolved links, "
        "unknown feasibility, and unapproved exploratory policy.",
        key=f"review_ack_{requirement.requirement_id}_{requirement.revision}",
    )
    service = ReviewService(database)
    action_columns = st.columns(4)
    actions = [
        ("Approve", DecisionAction.APPROVE),
        ("Reject", DecisionAction.REJECT),
        ("Challenge", DecisionAction.CHALLENGE),
        ("Defer", DecisionAction.DEFER),
    ]
    for column, (label, action) in zip(action_columns, actions):
        if column.button(
            label, width="stretch",
            type="primary" if action == DecisionAction.CHALLENGE else "secondary",
            disabled=(
                not actor.strip() or not reason.strip()
                or (needs_adoption and action in {DecisionAction.APPROVE, DecisionAction.REJECT, DecisionAction.DEFER})
                or (action == DecisionAction.APPROVE and not acknowledge)
            ),
        ):
            try:
                service.decide(
                    requirement_id=requirement.requirement_id,
                    expected_revision=requirement.revision,
                    action=action,
                    rationale=reason,
                    actor_id=actor,
                    request_id=f"ui_{uuid4().hex}",
                    uncertainty_acknowledged=acknowledge,
                    expected_priority_sequence=expected_priority_sequence,
                )
                st.success(f"Recorded {action.value} for revision {requirement.revision}.")
                st.session_state.pop("planning_export", None)
                st.rerun()
            except (ValueError, WorkflowError, RevisionConflict) as exc:
                st.error(str(exc))

    with st.expander("Edit this proposal into a new revision"):
        with st.form("edit_requirement"):
            title = st.text_input("Title", requirement.title)
            outcome = st.text_area("Customer outcome", requirement.customer_outcome)
            edit_reason = st.text_area("Edit rationale")
            conditions = st.text_area("Use conditions (one per line)", "\n".join(requirement.use_conditions))
            assumptions = st.text_area("Assumptions (one per line)", "\n".join(requirement.assumptions))
            validation_method = st.text_area("Proposed customer validation", requirement.acceptance_proposal.method)
            submitted = st.form_submit_button("Create new revision", disabled=not actor.strip())
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
                    st.session_state.pop("planning_export", None)
                    st.rerun()
                except (ValueError, WorkflowError, RevisionConflict) as exc:
                    st.error(str(exc))

    with st.expander("Validation plan, scope and provenance"):
        left, right = st.columns([1.5, 1], gap="large")
        with left:
            st.subheader("Validation plan")
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
        with st.expander("Run provenance and reviewer identity"):
            st.caption(f"Requirement ID: {requirement.requirement_id}")
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


def render_evidence(database, requirement, judgments, reviewed_link_count, linked_signal_ids, original_source_urls):
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
        "These are candidate signal links from the selected run. An exact text span proves "
        "where wording came from, not that it supports the proposed outcome."
    )
    st.info(
        f"{reviewed_link_count} of {len(linked_signal_ids)} linked signals have a recorded "
        "human assessment for this revision. Candidate counts and scores do not change "
        "when a link is assessed; reassessment requires a new revision and score snapshot."
    )
    with st.expander("Separate study context — not linked to this outcome"):
        st.write(
            f"Study observations for selected models in database: "
            f"{sum(database.survey_count(model=model) for model in requirement.scope.models)}; "
            "respondent counts unavailable. These observations are not included in "
            "the feedback recurrence above."
        )
    roles = {
        "Candidate support": requirement.supporting_signal_ids,
        "Candidate praise / preservation": requirement.counter_signal_ids,
        "Ambiguous context": requirement.context_signal_ids,
    }
    role = st.radio("Evidence role", list(roles), horizontal=True)
    review_filter = st.selectbox(
        "Filter by human assessment",
        ["All", "Unreviewed", "Supports", "Does not support", "Context only"],
    )
    wanted_verdict = {
        "Supports": "supports",
        "Does not support": "does_not_support",
        "Context only": "context_only",
    }.get(review_filter)
    signal_ids = [
        signal_id for signal_id in roles[role]
        if review_filter == "All"
        or (review_filter == "Unreviewed" and signal_id not in judgments)
        or (wanted_verdict is not None and signal_id in judgments
            and judgments[signal_id].verdict == wanted_verdict)
    ]
    if not signal_ids:
        st.info(
            "No candidate links match this role and assessment filter. "
            "Zero displayed links do not establish no customer need."
        )
    else:
        page_size = 12
        page_count = (len(signal_ids) + page_size - 1) // page_size
        page = st.number_input(
            "Page", min_value=1, max_value=page_count, value=1, step=1,
            key=f"evidence_page_{role}_{review_filter}",
        )
        page_ids = signal_ids[(page - 1) * page_size:page * page_size]
        page_signals = {signal_id: database.signal(signal_id) for signal_id in page_ids}
        table_rows = []
        mobile_cards = []
        for index, signal_id in enumerate(page_ids, start=(page - 1) * page_size + 1):
            signal = page_signals[signal_id]
            locator = signal.evidence_spans[0].locator
            place = f"{locator.sheet}!{locator.cell_range}"
            judgment = judgments.get(signal_id)
            verdict_label = (
                judgment.verdict.replace("_", " ").title() if judgment else "Unreviewed"
            )
            claim = signal.atomic_claim[:220] + ("…" if len(signal.atomic_claim) > 220 else "")
            table_rows.append(
                "<tr>"
                f"<td>{escape(claim)}</td><td>{escape(signal.polarity.value.title())}</td>"
                f"<td>{escape(verdict_label)}</td><td>{escape(place)}</td>"
                "</tr>"
            )
            mobile_cards.append(
                f'<article><small>Signal {index} · {escape(signal.polarity.value.title())} · '
                f'{escape(verdict_label)}</small><p>{escape(claim)}</p>'
                f'<small>{escape(place)}</small></article>'
            )
        st.markdown(
            '<div class="evidence-table-wrap"><table class="evidence-table">'
            '<thead><tr><th>Candidate claim</th><th>Polarity</th><th>Review</th>'
            '<th>Source</th></tr></thead><tbody>'
            + "".join(table_rows) + '</tbody></table></div>'
            + '<div class="evidence-mobile">' + "".join(mobile_cards) + '</div>',
            unsafe_allow_html=True,
        )
        st.caption(f"Showing {len(page_ids)} of {len(signal_ids)} linked signals in this role.")
        selected_signal_id = st.selectbox(
            "Inspect a source and assess its link", page_ids,
            format_func=lambda key: (
                f"{page_signals[key].polarity.value.title()} · "
                f"{page_signals[key].atomic_claim[:85]}"
            ),
            key=f"evidence_signal_{role}_{review_filter}_{page}",
        )
        signal = page_signals[selected_signal_id]
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
            f"original semantic entailment: unreviewed; signal ID: {signal.signal_id}."
        )
        prior_judgment = judgments.get(selected_signal_id)
        if prior_judgment:
            st.success(
                f"Latest human assessment: {prior_judgment.verdict.replace('_', ' ')} "
                f"by {prior_judgment.actor_id} · {prior_judgment.rationale}"
            )
        else:
            st.caption("No human assessment is recorded for this candidate link.")
        with st.form(
            f"judge_evidence_{requirement.requirement_id}_{requirement.revision}_{selected_signal_id}"
        ):
            verdict = st.selectbox(
                "Does this signal support the selected outcome?",
                ["supports", "does_not_support", "context_only"],
                index=None,
                placeholder="Choose an assessment",
                format_func=lambda value: {
                    "supports": "Yes, supports the outcome",
                    "does_not_support": "No, does not support",
                    "context_only": "Context only / different outcome",
                }[value],
            )
            evidence_actor = st.text_input("Reviewer ID (declared, not verified)", key="evidence_reviewer_id")
            evidence_reason = st.text_area("Reason for this link assessment")
            judge_submitted = st.form_submit_button("Record link assessment")
        if judge_submitted:
            try:
                if verdict is None:
                    raise ValueError("Choose an assessment before recording this link.")
                ReviewService(database).judge_evidence_link(
                    requirement_id=requirement.requirement_id,
                    expected_revision=requirement.revision,
                    signal_id=selected_signal_id,
                    verdict=verdict,
                    rationale=evidence_reason,
                    actor_id=evidence_actor,
                    request_id=f"ui_evidence_{uuid4().hex}",
                )
                st.session_state.pop("planning_export", None)
                st.rerun()
            except (ValueError, WorkflowError, RevisionConflict) as exc:
                st.error(str(exc))
    st.warning(
        "Evidence shown here is locally redacted by a heuristic. Privacy review is still required before hosted inference or export."
    )


def render_priority(database, requirement, score, decision, ranking_assessment, successor_proposals, priority_policy):
    sequence = selected_planning(database, requirement, successor_proposals, priority_policy, decision)
    with st.expander("Value ranges, methodology and missing evidence", expanded=False):
        st.subheader("Priority assessment")
        unresolved_count = len(ranking_assessment["unresolved_value_pairs"])
        resolved_count = len(ranking_assessment["resolved_value_pairs"])
        if unresolved_count:
            st.warning(
                f"{unresolved_count} of {unresolved_count + resolved_count} pairwise value comparisons "
                "remain unresolved because ranges overlap. The current order is exploratory, "
                "not a defensible final ranking."
            )
        st.caption(
            f"Resolved value comparisons: {resolved_count}. Engineering feasibility is a separate review."
        )
        if score:
            missing_inputs = [
                name.replace("_", " ") for name, criterion in score.criterion_inputs.items()
                if criterion.value is None
            ]
            if missing_inputs:
                st.write("Missing or scenario-only scoring inputs: " + ", ".join(missing_inputs) + ".")
            customer = score.dimension_intervals.get("customer")
            business = score.dimension_intervals.get("business")

            def value_card(label: str, interval, note: str) -> str:
                value = f"{interval.lower_bound:.1f}–{interval.upper_bound:.1f}" if interval else "Unavailable"
                return (f'<div class="value-card"><div class="value-label">{escape(label)}</div>'
                        f'<div class="value-number">{escape(value)}</div>'
                        f'<div class="value-sub">{escape(note)}</div></div>')

            st.markdown(
                '<div class="value-grid">'
                + value_card("Customer value", customer, "Scenario range from recorded inputs")
                + value_card("Business value", business, "Scenario range under selected policy")
                + '<div class="value-card feasibility"><div class="value-label">Engineering feasibility</div>'
                + f'<div class="value-number">{escape(score.feasibility_status.replace("_", " ").title())}</div>'
                + '<div class="value-sub">Separate review required</div></div></div>',
                unsafe_allow_html=True,
            )
            st.caption(
                f"Combined value range {score.lower_bound:.1f}–{score.upper_bound:.1f}; "
                f"feedback extraction coverage {score.coverage['processed_feedback_records']}/"
                f"{score.coverage['eligible_feedback_records']}. "
                "The order uses the lower value bound only for exploration; overlapping ranges are unresolved. "
                "Evidence claims await human entailment review and the equal-weight seed policy is unapproved. "
                "Ranges are scenarios, not measured probabilities."
            )

        with st.expander("See scoring inputs and calculation"):
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

        with st.expander("Assumptions and missing evidence"):
            st.markdown("**Assumptions**")
            for item in requirement.assumptions:
                st.write(f"- {item}")
            st.markdown("**Missing evidence**")
            for item in requirement.missing_evidence:
                st.write(f"- {item}")
            st.markdown("**Acceptance proposal**")
            st.write(requirement.acceptance_proposal.method)
            st.caption(
                f"Target: {requirement.acceptance_proposal.target or 'pending review'}; "
                f"unit: {requirement.acceptance_proposal.unit or 'pending review'}."
            )
            st.markdown("**Implementation cost**")
            st.caption(requirement.implementation_cost_missing_reason)


    return sequence


def render_history_records(database, requirement):
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
    with st.expander(f"Evidence link assessments ({len(replay['evidence_judgments'])})"):
        for item in reversed(replay["evidence_judgments"][-20:]):
            st.write(
                f"Revision {item['requirement_revision']} · {item['signal_id']} · "
                f"{item['verdict'].replace('_', ' ')} · {item['actor_id']} · {item['rationale']}"
            )
        if len(replay["evidence_judgments"]) > 20:
            st.caption("Showing the 20 most recent assessments; full records are below.")
        if not replay["evidence_judgments"]:
            st.caption("No link assessments recorded.")
    with st.expander("Inspect full revision and decision records"):
        st.json({
            "revisions": replay["revisions"],
            "decisions": replay["decisions"],
            "evidence_judgments": replay["evidence_judgments"],
        })
