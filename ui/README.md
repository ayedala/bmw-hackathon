# Product manager workbench

The primary interface is `app.py`, a Streamlit implementation of the [Figma workbench](https://www.figma.com/design/jSR5Jr8ho8w4m6BhawIa7T/BMW-Product-Decision-Lab---Workbench-Redesign?node-id=16-2087).

Run from the repository root with `uv run streamlit run ui/app.py`.

- **Decision desk:** vehicle/market scope, searchable proposal cards, current priority previews, editable saved assessments, revision edits and PM decisions.
- **Data & AI findings:** source inventory, actual provider mode, cross-channel context, original locators and human evidence-link assessments.
- **YouTube research:** generation-scoped discovery, transcript-validated findings, saved-run review and an explicit action to combine a selected run with BMW feedback/studies/context. Credential readiness is shown without exposing key values; live discovery stays disabled until the local runtime and keys are configured.
- **Audit trail:** chronological backend events, chain verification, saved priority changes and immutable revision/decision records.

Domain logic stays in `src/bmw_pm/`. The UI calls `ReviewService`, `PriorityService` and `Database`; it uses no mock decision API. Seven real-data-anchored US G60 future drafts separate quotations, interpretations, future assumptions, conflicts and unknowns. AI provisional ranking, PM-entered draft assessments and explicit priority confirmation remain separate. PMs can edit criteria, ratings, weights, manual rank and rationale. The UI and exports share one ranking function.

Final decisions on future drafts require explicit adoption into a stored revision. Approval requires a declared reviewer ID, rationale and uncertainty acknowledgement. Changing the outcome creates a revision and does not carry the old score into it. Evidence-link assessments remain scoped to the reviewed revision. Saving an edit or priority invalidates the prepared export. Full instructions and the real-data story: [current handover](../docs/DRAFT_DECISION_SUPPORT.md).

`workbench_views.py` retains the evidence, review and scoring workflows. `workbench_audit.py` renders actual events. `workbench_theme.py`, `workbench.css` and `assets/` contain the local Figma SVG assets and IBM Plex Sans font with its OFL license. No temporary Figma asset URLs are used at runtime. The layout stacks on small screens, retains keyboard focus states and respects reduced motion.

Workspace and pipeline settings are in the collapsible sidebar. Hosted access still uses `hosting_access.py`. Set `BMW_PM_DATABASE` to point the local workbench at a separate test or demonstration database. The default is the original `data/processed/bmw_pm.db`, preserving all three vehicle scopes and the combined evidence. Test approvals are recorded only in isolated copies.

`uv run pytest` runs the software checks, including synthetic UI flows for priority reordering, approval acknowledgement, evidence assessment, revision editing and navigation. These verify software behavior; they do not measure extraction accuracy, evidence entailment or real BMW approval.

The YouTube collector remains an evidence source, not a second requirement approval system. In the workbench, open **YouTube research** to inspect saved runs or configure/start a probe. Install its separate dependencies and place credentials in `src/bmw_pm/data_pipeline/youtube_research/.env`; the UI checks whether required values exist but never displays them. After a run, select **Combine this run with BMW evidence** to revalidate transcript quotes and link supported findings into the shared decision cards.

## Verification — 2026-10-10

The prior integrated regression suite passed 55 tests; the YouTube research workspace adds 3 focused passing tests for credential readiness, saved-run provenance and rendering before requirements exist. A real-data rehearsal passed adoption, editable AI inputs, PM draft priority, explicit confirmation, acknowledged approval, rejection, export, evidence view and audit navigation on a private copy, with zero AppTest exceptions. All 10 data/provenance validation checks passed. Current-session browser visual QA was unavailable; the supplied responsive CSS/assets are retained. These checks verify software behavior and data integrity, not model accuracy or BMW approval.
