# BMW Product Decision Lab

Preparation and working prototype, 10 October 2026. Build window: **24 hours**.

The proposed app turns evidence into customer-facing successor-vehicle requirements, shows why they deserve attention, and lets a product manager challenge and revise them over time. The primary demonstration is the 5 Series; the 1 and 7 Series provide transfer tests.

**Current status:** a local Python/SQLite decision-engine slice ingests the supplied feedback and customer-study workbooks, extracts candidate signals, drafts seven G60 US requirement candidates with exact source links, computes customer and business scenario ranges, keeps feasibility unknown, and records PM reviews in an audit chain. The default extractor is a deterministic keyword baseline. Live AI extraction is optional and has not been quality-evaluated. Sales/equipment adapters, automated web enrichment, a human-labelled evaluation set, and measured model accuracy are still pending. No product requirement has been approved by BMW.

## Start here

1. Read [AGENTS.md](AGENTS.md), then [the strategy report](docs/REPORT.md).
2. Follow [the 24-hour plan](docs/IMPLEMENTATION_PLAN.md) and [TASKS.md](TASKS.md).
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

The Streamlit sidebar accepts the SQLite path (default `data/processed/bmw_pm.db`). The baseline's counts are unique feedback records in the selected corpus, never estimated customer prevalence. The exploratory policy is unapproved; its bounds expose missing impact and business evidence. Feasibility remains a separate unknown until engineering review. For optional live extraction, install `uv sync --extra ai`, set `OPENAI_API_KEY` and `BMW_PM_OPENAI_MODEL`, then run `bmw-pm run --provider openai --limit 20`. Keep customer text local unless your team has approved hosted processing.

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

Continue with [TASKS.md](TASKS.md). The next quality gate is a grouped, independently labelled evaluation split before tuning prompts or declaring model accuracy. Sales, equipment and sourced web claims should then enrich the business dimension with scoped facts rather than guessed values.
