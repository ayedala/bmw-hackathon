# BMW Product Decision Lab

A local decision-support prototype for turning customer evidence into reviewable requirements for future BMW vehicles. The first working scope is 5 Series G60 feedback from the US; F70 and G70 are used to check whether the method transfers to other vehicles.

## Approach

1. **Preserve and reconcile evidence.** Keep the supplied files unchanged and record source hashes, spreadsheet rows, cells, pages, and any cleaning transformations. Multiple annotation rows for one feedback ID remain one feedback record for recurrence counts.
2. **Extract customer signals.** Identify distinct complaints, aspirations, praise, and context with exact text spans. Treat source text as evidence, never as an instruction. A valid span locates the text; human review must still decide whether it supports the claim.
3. **Draft customer outcomes.** Group related signals into solution-neutral requirement candidates. Show supporting and preservation evidence, scope, assumptions, missing facts, and proposed ways to test the outcome.
4. **Prioritize transparently.** Deterministic code calculates value ranges from a versioned policy. Unknown criteria keep their weight and widen the range. Engineering feasibility and implementation cost stay separate until reviewed inputs exist.
5. **Keep the product manager in control.** Review actions and edits create an auditable decision history. New evidence or changed policy should lead to a new, explainable assessment rather than silently replacing an earlier decision.
6. **Measure quality.** Evaluate extraction, citation entailment, requirement usefulness, ranking agreement, transfer, and runtime on frozen, independently reviewed examples. See the [evaluation plan](docs/EVALUATION.md) for proposed measures; its targets are not measured results.

The [strategy report](docs/REPORT.md), [data audit](docs/DATA_AUDIT.md), [decision contract](docs/DECISION_ENGINE.md), and [architecture](docs/ARCHITECTURE.md) explain the evidence limits and design choices.

## Current prototype

The Python/SQLite core ingests feedback and customer-study workbooks, builds candidates with a deterministic keyword baseline or a bounded structured model call, scores them under an unapproved exploratory policy, and records local review revisions and audit events. A Streamlit workbench shows the requirement queue, outcomes, evidence scope and exact spans, score contributions, run provenance, uncertainty, review actions, and audit history. Large evidence sets are paginated. The stored baseline run produced seven US G60 candidates from 3,610 eligible feedback IDs. This is a software demonstration, not measured extraction accuracy or a BMW-approved priority order. Sales, equipment, and public web facts have not yet been linked into these cards.

## Run locally

Use Python 3.11+ and [uv](https://docs.astral.sh/uv/). Place the authorized workbooks in data/raw/provided/; those files are excluded from Git.

~~~powershell
uv sync
uv run bmw-pm ingest --input data/raw/provided --profile configs/g60.json
uv run bmw-pm run --provider baseline --profile configs/g60.json --policy configs/exploratory_equal_v1.json
uv run bmw-pm validate --expect-supplied-shape
uv run streamlit run ui/app.py
~~~

The CLI and UI default to data/processed/bmw_pm.db. For an optional live model run, install with uv sync --extra ai, set OPENAI_API_KEY and BMW_PM_OPENAI_MODEL, review the redacted input, and use bmw-pm run --provider openai --limit 20. Keep raw customer material, keys, local databases, and model responses containing personal information out of Git.

The implementation is under src/bmw_pm/; configs/ holds vehicle and scoring policies, ui/ the review interface, tests/ the software checks, and prompts/ the stage specifications. The supplied source files are required to reproduce data-specific runs and are not part of this repository.

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

The archive hash, original table, row payload hash and original locator IDs preserve foreign lineage. Import does not establish entailment or engineering feasibility: these extra channels remain unreviewed context and do not automatically populate scores or approve requirements. The model pipeline uses the rebuilt feedback records. Repeating an identical import is idempotent; different local raw bytes cause a conflict instead of an overwrite. Raw data, snapshots and import manifests remain ignored by Git.

## Hosted app

A protected Docker/Render deployment is prepared in `Dockerfile` and `render.yaml`. Read [hosting setup](docs/HOSTING.md) for account connection, generated access secrets, persistent storage, private database upload and actual verification limits. The database is uploaded separately through authenticated setup, not included in Git or the image. The app is not live until a hosting service is provisioned.
