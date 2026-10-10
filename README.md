# BMW Product Decision Lab

Preparation and coding handoff, 10 October 2026. Build window: **24 hours**.

The proposed app turns evidence into customer-facing successor-vehicle requirements, shows why they deserve attention, and lets a product manager challenge and revise them over time. The primary demonstration is the 5 Series; the 1 and 7 Series provide transfer tests.

**Current status:** supplied data inspected locally, strategy and implementation contracts prepared, primary web sources reviewed. The application, automated web collector, human-labelled evaluation set, and measured model performance are **not built yet**. No product requirement has been approved by BMW.

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

The repository contains a preparation pack, not a pre-built application. Proposed commands in the implementation plan become runnable only when their corresponding tasks are complete.

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

## First implementation instruction

Use [CODEX_KICKOFF.md](prompts/CODEX_KICKOFF.md). It starts with deterministic ingestion, traceability, and a fixed evaluation split before paid inference or frontend polish.
