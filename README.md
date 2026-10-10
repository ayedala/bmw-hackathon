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

The Python/SQLite core ingests feedback and customer-study workbooks, builds candidates with a deterministic keyword baseline or a bounded structured model call, scores them under an unapproved exploratory policy, and records local review revisions and audit events. A Streamlit interface displays evidence and score breakdowns. The stored baseline run produced seven US G60 candidates from 3,610 eligible feedback IDs. This is a software demonstration, not measured extraction accuracy or a BMW-approved priority order. Sales, equipment, and public web facts have not yet been linked into these cards.

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
