# UI implementation rules

Follow internal/AGENTS.md. The UI is a review surface for the model, not the primary sprint deliverable.

- Use Streamlit unless the user chooses another stack. Call core services; do not duplicate scoring logic.
- Show requirement status, scope, support, counterevidence, source locators, assumptions, coverage and value interval together.
- Show “unknown” and “pending review” plainly; do not replace with reassuring green states or zeroes.
- Support approve, reject, edit, challenge and defer with a reason. Show the revision being changed and handle stale-version conflicts.
- Identify live, cached replay and synthetic illustration accurately. Persist decisions outside session state.
- Do not expose raw personal data by default. Evidence exports and views must generate audit events.
- Keep rank changes linked to the actual score/evidence diff. Do not independently generate a persuasive explanation after sorting.
