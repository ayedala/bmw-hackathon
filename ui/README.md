# Product manager workbench

The primary interface is `app.py`, a Streamlit implementation of the [Figma workbench](https://www.figma.com/design/jSR5Jr8ho8w4m6BhawIa7T/BMW-Product-Decision-Lab---Workbench-Redesign?node-id=16-2087).

Run from the repository root with `uv run streamlit run ui/app.py`.

- **Decision desk:** vehicle/market scope, searchable proposal cards, current priority previews, editable saved assessments, revision edits and PM decisions.
- **Data & AI findings:** source inventory, actual provider mode, cross-channel context, original locators and human evidence-link assessments.
- **Audit trail:** chronological backend events, chain verification, saved priority changes and immutable revision/decision records.

Domain logic stays in `src/bmw_pm/`. The UI calls `ReviewService`, `PriorityService` and `Database`; it uses no mock decision API. Approval requires a declared reviewer ID, rationale and explicit uncertainty acknowledgement. Changing the outcome creates a new revision and does not carry the old score into it. All preview scores label saved versus illustrative ratings.

`workbench_views.py` retains the evidence, review and scoring workflows. `workbench_audit.py` renders actual events. `workbench_theme.py`, `workbench.css` and `assets/` contain the local Figma SVG assets and IBM Plex Sans font with its OFL license. No temporary Figma asset URLs are used at runtime. The layout stacks on small screens, retains keyboard focus states and respects reduced motion.

Workspace and pipeline settings are in the collapsible sidebar. Hosted access still uses `hosting_access.py`. Set `BMW_PM_DATABASE` to point the local workbench at a separate test or demonstration database. Without it, the UI uses `data/processed/decision_engine_v2.db` when available, otherwise `bmw_pm.db`.

`uv run pytest` runs the software checks, including synthetic UI flows for priority reordering, approval acknowledgement, evidence assessment, revision editing and navigation. These verify software behavior; they do not measure extraction accuracy, evidence entailment or real BMW approval.

The optional YouTube browser is a collector interface, not a second requirement approval system.

## Verification — 2026-10-10

Full regression suite: 40 passed, 1 skipped. The final affected workflow checks passed 8 tests after the export scope and panel updates. The real database copy passed all 8 integrity checks. All three workbench views rendered without AppTest exceptions; desktop and mobile layouts were inspected. git diff --check passed. These checks verify software behavior and data integrity, not model accuracy or BMW approval.
