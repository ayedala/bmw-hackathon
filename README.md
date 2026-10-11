# BMW Product Decision Lab

> Current workflow: [Evidence-grounded drafts and explicit PM decisions](docs/DRAFT_DECISION_SUPPORT.md). Future scenarios and AI provisional priorities are restored as labelled drafts. Quotations remain exact; only reviewer input can adopt, approve, reject or confirm a priority. This supersedes the earlier evidence-only restriction.

A local decision-support prototype for turning customer evidence into reviewable requirements for future BMW vehicles. The first working scope is 5 Series G60 feedback from the US; F70 and G70 are used to check whether the method transfers to other vehicles.

## Repository map

```text
src/bmw_pm/
  data_pipeline/      # Search, ingestion, cleaning and source provenance
    feedback.py       # Supplied feedback workbooks
    studies.py        # Aggregate customer studies
    legacy_database.py
    web_research/     # Optional public-web collector, local dependencies
    youtube_research/ # Optional video/transcript collector, local dependencies
  intelligence/       # Bounded AI extraction and labelled offline baseline
  decision/           # Deterministic requirement consolidation and scoring
  review/             # PM actions and immutable edits
  storage/            # SQLite persistence and application audit history
  contracts.py        # Shared typed data contracts
  pipeline.py         # Orchestrates the modules
  cli.py              # Application commands
ui/                   # Primary PM review workbench
configs/              # Versioned scope, taxonomy and scoring policies
prompts/              # Extraction and proposed stage contracts
scripts/              # Local diagnostics and hosting utilities
research/             # Curated source seeds; collection code is in data_pipeline/
tests/                # Core regression checks
docs/                 # Architecture, challenge assessment and design documents
internal/             # Historical development plans and agent guidance
```

Each application module has a README explaining its inputs, responsibilities and limits. Start with the [module guide](src/bmw_pm/README.md), [file inventory](docs/FILE_INVENTORY.md) or [cleanup and challenge report](docs/REPOSITORY_REVIEW.md).

The collectors remain independently runnable. The workbench now includes a **YouTube research** workspace for local credential/runtime readiness, generation-scoped discovery, saved-run/source review, and an explicit combine action. The combined pipeline consumes validated saved YouTube excerpts and BMW study/sales/equipment context with separate provenance. The current available video run has no usable transcripts, so the real-data demo makes no video-derived claims. The successor layer adds seven evidence-anchored US G60 draft requirements and editable provisional priorities.

## Approach

1. **Preserve and reconcile evidence.** Keep the supplied files unchanged and record source hashes, spreadsheet rows, cells, pages, and any cleaning transformations. Multiple annotation rows for one feedback ID remain one feedback record for recurrence counts.
2. **Extract customer signals.** Identify distinct complaints, aspirations, praise, and context with exact text spans. Treat source text as evidence, never as an instruction. A valid span locates the text; human review must still decide whether it supports the claim.
3. **Draft customer outcomes.** Group related signals into solution-neutral requirement candidates. Show supporting and preservation evidence, scope, assumptions, missing facts, and proposed ways to test the outcome.
4. **Prioritize transparently.** Deterministic code calculates value ranges from a versioned policy. Unknown criteria keep their weight and widen the range. Engineering feasibility and implementation cost stay separate until reviewed inputs exist.
5. **Keep the product manager in control.** Review actions and edits create an auditable decision history. New evidence or changed policy should lead to a new, explainable assessment rather than silently replacing an earlier decision.
6. **Measure quality.** Evaluate extraction, citation entailment, requirement usefulness, ranking agreement, transfer, and runtime on frozen, independently reviewed examples. See the [evaluation plan](docs/EVALUATION.md) for proposed measures; its targets are not measured results.

The [strategy report](docs/REPORT.md), [data audit](docs/DATA_AUDIT.md), [decision contract](docs/DECISION_ENGINE.md), and [architecture](docs/ARCHITECTURE.md) explain the evidence limits and design choices.

## Current prototype

The supplied Figma-style frontend is now the primary workbench: **Decision desk** for the searchable proposal queue, **Data & AI findings** for source inspection and evidence-link assessment, **YouTube research** for transcript-backed discovery and evidence fusion, and **Audit trail** for traceable human actions. Use the header Vehicle/Market selectors. The local default is the original combined BMW database; set `BMW_PM_DATABASE` to review a separate demonstration copy. Every screen calls the real evidence and review services.

The [current demo and handover](docs/DRAFT_DECISION_SUPPORT.md) adds seven evidence-linked US 5 Series drafts for the assumed 2029–2031 scenario, transparent AI provisional scores, editable PM criteria/ratings/weights/manual ranks, separate priority confirmation, immutable decision references and a private Markdown export. Run `python scripts/demo_successor.py` to generate an isolated real-data draft portfolio with **no new decisions**. Decisions require explicit reviewer input in the UI or CLI; the original database receives no test approvals.

The Python/SQLite core ingests feedback and customer-study workbooks, builds candidates with a deterministic keyword baseline or a bounded structured model call, scores them under an unapproved exploratory policy, and records local review revisions and audit events. The combined engine aligns BMW feedback with saved YouTube findings, relevant study observations and imported sales/equipment/web context in one versioned requirement card. A Streamlit workbench shows the requirement queue, outcomes, evidence scope and exact spans, score contributions, run provenance, uncertainty, review actions, and audit history. Large evidence sets are paginated. The earlier feedback-only baseline produced seven US G60 candidates from 3,610 eligible feedback IDs. This is a software demonstration, not measured extraction accuracy or a BMW-approved priority order.

## Run locally

Use Python 3.11+ and [uv](https://docs.astral.sh/uv/). Place the authorized workbooks in data/raw/provided/; those files are excluded from Git.

~~~powershell
uv sync --extra data
uv run bmw-pm ingest --input data/raw/provided --profile configs/g60.json
uv run bmw-pm run --provider baseline --profile configs/g60.json --policy configs/exploratory_equal_v1.json
uv run bmw-pm validate --expect-supplied-shape
uv run streamlit run ui/app.py
~~~

The CLI and UI default to data/processed/bmw_pm.db. For an optional live model run, install with uv sync --extra ai, set OPENAI_API_KEY and BMW_PM_OPENAI_MODEL, review the redacted input, and use bmw-pm run --provider openai --limit 20. Keep raw customer material, keys, local databases, and model responses containing personal information out of Git.

### Guided AI decision website

The product-facing website has three journeys: **Assess my idea**, **Find the next improvement**, and **Compare several ideas**. It covers BMW 1 Series F70, 5 Series G60 and 7 Series G70, with a chosen market, powertrain and objective.

```powershell
uv sync --extra ai --extra data
uv run streamlit run ui/agent.py
```

The earlier `uv run streamlit run ui/mocktest.py` command now opens this same website. The database must already be imported using the commands above. Open **App settings**, enter your API key, and select **Save and test connection**. **Remember on this computer** stores it in the local, unencrypted, Git-ignored `.env.advisor` file; leave this unchecked for session-only use. Failed setup preserves the previous connection. Return to Decision Studio to assess an idea, recommend an improvement or compare ideas. Users do not choose the underlying AI model: `BMW_PM_OPENAI_MODEL` is configured on the server and must support Responses, web search and structured outputs. Keys are never included in reports. See [connection setup](docs/ADVISOR.md#configure-the-app) for details.

Each run reads scoped local evidence, builds a research plan, searches public sources, and produces a cited decision brief with alternatives, competitor findings, delivery risks and economic gaps. The page retains the result across interactions and lets you download its evidence/provenance as JSON. **Costs & revenue** also calculates conditional scenarios from explicit user assumptions using the existing financial engine. Missing costs or causal sales lift are not invented. API failures remain visible. See [the guided agent workflow](docs/ADVISOR.md) for scope, data handling and validation limits. The detailed PM review workbench remains at `ui/app.py`.

The BMW Group Report 2025 is stored as five dated planning-context entries. Run `uv run bmw-pm sync-report-context` to load them into an existing database; new `bmw-pm run` calls sync them automatically. The UI's **BMW report context** tab shows the applicable entries, citations, considerations and limitations for each requirement. These entries do not change feedback counts or criterion scores. See [report context](docs/REPORT_CONTEXT.md).

Run `uv run bmw-pm sync-public-datasets` to add official NHTSA complaint/recall summaries, U.S. Department of Energy public charging counts, and a small set of sourced technology/competitor notes. These appear in the **Public datasets** card tab and remain review context rather than automatic score multipliers. See [public datasets](docs/PUBLIC_DATASETS.md) for scope, gaps and other proposed sources.

The implementation is under src/bmw_pm/; configs/ holds vehicle and scoring policies, ui/ the review interface, tests/ the software checks, and prompts/ the stage specifications. The supplied source files are required to reproduce data-specific runs and are not part of this repository.

## Use the combined BMW + YouTube engine

The private Drive data is stored locally under ignored `data/raw/provided/`, with a hash-verified `drive_manifest.json` preserving Drive IDs and original URLs. `bmw-pm ingest` imports all three feedback files and the study workbook, plus sales values with exact cells and all equipment pages with page locators. Sales formulas are never executed: supplied cached results are explicitly labelled and missing caches fail validation. Equipment pages are discovery context; derivative-specific availability is not inferred from flattened tables. The `data` dependency extra includes PDF extraction, AES reading and embedded-font support.

Choose G60, F70 or G70 in the workbench's **Vehicle research scope**, or use `--profile configs/f70.json` / `--profile configs/g70.json`. F70 uses all supplied feedback countries and ICE only; G60 and G70 default to US feedback. The model profiles keep evidence scope separate. Original Drive source links are available in the Evidence tab.

Run YouTube research or authorized file analysis through the existing `youtube_research_agent` interface. Then build combined cards:

```powershell
uv run bmw-pm run --provider baseline --full
# Or explicitly select one or several saved research directories:
uv run bmw-pm run --provider baseline --youtube-run youtube_research_agent/output/browser --full
uv run bmw-pm validate
```

With no `--youtube-run`, the engine discovers saved `output/*/evidence.json` runs automatically. `--youtube-run` can be repeated. Previously imported findings remain available in the selected database. `bmw-pm import-youtube <directory>` imports findings without rebuilding cards. The Streamlit sidebar's **Combined engine → Build combined results** performs the same synthesis locally. Its Evidence tab displays the combined assessment and original cross-channel citations.

The importer independently checks every quote and timestamp against `transcripts/<video_id>.json`, retains original source/evidence/transcript bytes in SQLite, and reports rejected findings. Matching uses the versioned keyword taxonomy, with exact generation filtering. Repeated observations from the same video do not create extra customer records. A YouTube-only concern can create a provisional card; its customer reach stays unknown. Positive assessments remain preservation evidence; differing assessments trigger review rather than an automatic contradiction verdict. Studies and imported business/technical facts supply context, with original scope and limitations visible. External evidence never receives an invented severity, expertise, feasibility or ranking bonus.

New evidence changes the corpus manifest and can create an immutable revision for an unreviewed candidate. Reviewed requirements retain their stored wording; incorporating changed evidence requires an explicit PM edit. Unmatched YouTube findings are retained and reported for manual alignment. This fusion implementation uses deterministic theme alignment, not a measured model-quality improvement. A blocked or empty YouTube run adds no claims; obtain a successful transcript/extraction run to demonstrate video-derived evidence. BMW workbooks/private databases are required separately and remain excluded from Git.

## Import another local evidence workspace

Use the compatibility adapter instead of opening the foreign-schema database as our active database:

```powershell
$env:PYTHONPATH = "src"
python -m bmw_pm.cli import-workspace "C:/path/to/other/bmw-hackathon"
python -m bmw_pm.cli validate --expect-supplied-shape
python -m bmw_pm.cli run --provider baseline
python -m bmw_pm.cli context sales_observation --limit 36
```

The active database remains `data/processed/bmw_pm.db`. The adapter copies original raw files with hash checks, preserves a consistent SQLite snapshot under `data/processed/imports/`, and rebuilds feedback and studies through our canonical adapters. Foreign evidence, source locators, transformations, sales, equipment, external claims, source access restrictions, competitor cohorts and discovery leads are retained as typed `ImportedEvidenceRow` records. Read these through `evidence_context` or the UI's Imported evidence context panel; reads are audited. Source database SQL, triggers, keys and foreign agent code are never imported into the active application.

The archive hash, original table, row payload hash and original locator IDs preserve foreign lineage. Import does not establish entailment or engineering feasibility: these extra channels remain unreviewed context and do not automatically populate scores or approve requirements. The combined pipeline links relevant imported context alongside rebuilt feedback and YouTube evidence. Repeating an identical import is idempotent; different local raw bytes cause a conflict instead of an overwrite. Raw data, snapshots and import manifests remain ignored by Git.

## Financial scenarios for update decisions

The separate [business-case calculator](docs/BUSINESS_CASES.md) accepts private,
hashed cost, revenue, adoption and sales-lift assumptions for each proposed
update. It reports downside/base/upside annual cash flow, discounted value,
break even sales lift, evidence and scope gates, and unresolved comparisons.
The current database has no approved feature-level finance inputs, so it does
not yet identify a profit-maximizing update. Run
`python scripts/evaluate_business_cases.py --template runs/business-cases.json`
with `PYTHONPATH=src` to create the blank private worksheet.

## Hosted app

A protected Docker/Render deployment is prepared in `Dockerfile` and `render.yaml`. Read [hosting setup](docs/HOSTING.md) for account connection, generated access secrets, persistent storage, private database upload and actual verification limits. The database is uploaded separately through authenticated setup, not included in Git or the image. The app is not live until a hosting service is provisioned.

## Feature implementation costs

The decision workbench and the advisor's Costs & revenue tab now provide a source-labelled feature cost scenario form. It separates parts and assembly per equipped vehicle from engineering, tooling and validation paid once, then shows low/base/high totals at the entered volume. Public DOE/BLS figures are displayed as benchmarks, not BMW quotes. See [the estimator guide](docs/FEATURE_COST_ESTIMATOR.md).
