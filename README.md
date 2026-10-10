# BMW Product Decision Lab

Preparation and working prototype, 10 October 2026. Build window: **24 hours**.

The proposed app turns evidence into customer-facing successor-vehicle requirements, shows why they deserve attention, and lets a product manager challenge and revise them over time. The primary demonstration is the 5 Series; the 1 and 7 Series provide transfer tests.

**Current status:** a local Python/SQLite decision-engine slice ingests the supplied feedback and customer-study workbooks, extracts candidate signals, drafts seven G60 US requirement candidates with exact source links, computes customer and business scenario ranges, keeps feasibility unknown, and records PM reviews in an audit chain. The default extractor is a deterministic keyword baseline. The structured OpenAI extractor is available for bounded runs but has not been quality-evaluated. The supplied sales/equipment facts and public web claims are not yet linked to requirement cards; a separate YouTube research module has been added but is not integrated into this decision path. A frozen human-labelled set, sensitivity analysis and measured model accuracy are pending. No product requirement or scoring policy has been approved by BMW.

## Start here

1. Read [AGENTS.md](AGENTS.md), then [the strategy report](docs/REPORT.md).
2. Follow the current priority in [TASKS.md](TASKS.md); [the implementation plan](docs/IMPLEMENTATION_PLAN.md) distinguishes working commands from planned work.
3. Before changing a pipeline stage, read its contract below. Keep the root agent instructions short; do not inject every document into every model call.

| Document | Purpose |
|---|---|
| [Data audit](docs/DATA_AUDIT.md) | Actual files, row counts, biases, missing data and cleaning rules |
| [Decision engine](docs/DECISION_ENGINE.md) | Evidence quality, scoring, uncertainty, conflicts and trade-offs |
| [Data contracts](docs/DATA_CONTRACTS.md) | Entities, schemas, invariants and validation boundaries |
| [Architecture](docs/ARCHITECTURE.md) | Small modular implementation and runtime responsibilities |
| [Human review and audit](docs/HUMAN_REVIEW_AND_AUDIT.md) | PM controls, versioning, access events and two-year lifecycle |
| [Evaluation](docs/EVALUATION.md) | Blind tests, baselines, accuracy, latency and release gates |
| [Web research](docs/WEB_RESEARCH.md) | Retrieved sources, bounded collection and factual comparisons |
| [Vehicle transfer](docs/MODEL_TRANSFER.md) | Exact configuration changes for other vehicles and markets |
| [Demo](docs/DEMO.md) | Evidence-led presentation and judge challenge scenario |
| [Decisions](DECISIONS.md) | Proposed defaults and unresolved questions |
| [Prompt contracts](prompts/README.md) | Stage-specific runtime prompt requirements |
| [Codex kickoff](prompts/CODEX_KICKOFF.md) | Copyable first implementation task |

The repository contains the preparation pack and the first implementation slice. `TASKS.md` records what remains incomplete.

## Run the local decision-engine slice

From the repository root, with the authorized workbooks in `data/raw/provided/`:

```powershell
uv sync
uv run bmw-pm ingest --input data/raw/provided --profile configs/g60.json
uv run bmw-pm run --provider baseline --profile configs/g60.json --policy configs/exploratory_equal_v1.json
uv run bmw-pm validate --expect-supplied-shape
uv run streamlit run ui/app.py
```

The Streamlit sidebar accepts the SQLite path (default `data/processed/bmw_pm.db`). The baseline's counts are unique feedback records in the selected corpus, never estimated customer prevalence. The exploratory policy is unapproved; only reach is data-derived in the current real run, while impact and both business criteria remain unknown. Feasibility remains separate and unknown until engineering review. For a bounded live extraction run, install `uv sync --extra ai`, set `OPENAI_API_KEY` and `BMW_PM_OPENAI_MODEL`, review the locally redacted excerpts, then run `bmw-pm run --provider openai --limit 20`. The user authorized sending locally redacted excerpts for this project; keep original customer text local and out of Git.

Working CLI commands are `ingest`, `run`, `list`, `review`, `edit`, `verify-audit`, `validate` and `replay`. An `evaluate` command, decision-report `export`, resumable live jobs and an offline replay package are **not implemented**. The 12 passing tests and the local `validate --expect-supplied-shape` report establish software/structural behavior, not model accuracy.

## Source data stays local

The supplied BMW archive, briefing, slide images, extracted customer records and local data profiles are excluded from Git. The repository is public, and the feedback contains customer narratives. Each teammate must obtain the challenge files through the team's authorized channel and place the ZIP and briefing at the paths shown in the inspection command below. This keeps the shared handoff useful without publishing the raw records. The web research sources and cited URLs are included in the repository.

## Local evidence and reproducibility

The eight archive files and the separate briefing were copied unchanged to `data/raw/provided/`. SHA-256 hashes and workbook structure are in `research/local/profile.json`; ID-level feedback diagnostics are in `research/local/feedback_profile.json`. Both folders are ignored by Git. Supplied customer content must not be committed or publicly hosted by accident.

The supplied slide images are retained under `data/raw/briefing-slides/` with a hash manifest. The scripts under `scripts/` inspect the sources and validate this preparation pack; they are not the production ingestion implementation. They require Python, `openpyxl`, and `pypdf`. Run from this repository root:

```powershell
python scripts/inspect_supplied_data.py --zip 'D:/Legion 5/Downloads/drive-download-20261010T130119Z-1-001.zip' --briefing 'D:/Legion 5/Downloads/BMW_Hackathon_Briefing_Short.pdf'
python scripts/profile_feedback.py
python scripts/validate_preparation.py
```

Use your Python environment, or the bundled Python executable reported by Codex's workspace-dependency tool. The inspected briefing has no extractable text layer; its two pages were rendered with bundled PDFium and read visually. Option-list extraction is suitable for discovery but requires table-level visual validation before factual use.

## Next implementation instruction

Begin with **T04 in [TASKS.md](TASKS.md)**: freeze the grouped 120-record development/test/transfer manifest and obtain independent human labels before changing extraction prompts. Then compare the keyword baseline with bounded live AI extraction on the same examples. Add scoped sales, verified equipment and sourced public claims to actual requirement cards before populating business ratings. Record PM objectives and weights only after the BMW PM reviews them; do not infer feasibility or expertise.

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
