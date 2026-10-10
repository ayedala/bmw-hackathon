# 24-hour implementation plan

The user confirmed a 24-hour build window. This schedule starts when implementation begins; it is not a claim that these tasks are already completed. Stack default: Python, SQLite, Streamlit, provider-neutral structured LLM calls. Optimize for one working path and measured quality.

## Hour-by-hour milestones

| Elapsed time | Deliverable | Acceptance evidence |
|---|---|---|
| 0–2 h | Repo bootstrap, typed core, local DB, tiny synthetic fixture, run manifest, frozen split plan | One source can be ingested and cited; no hosted inference required |
| 2–5 h | Feedback/study/sales adapters, verified equipment subset, deduplication, initial gold annotations | Supplied counts reconcile; raw labels preserved; unknown metadata explicit |
| 5–9 h | Bounded extraction, span validator, basic grouping, baseline and small dev evaluation | Atomic signals trace to sources; mixed sentiment preserved; failures visible |
| 9–12 h | Requirement drafting, counterevidence, policy and deterministic score intervals | Representative cards and reproducible contributions; no invented costs/targets |
| 12–15 h | Thin review UI, decisions, versioning, access/change audit, export | Approve/edit/challenge persists and changes exact revision; replay works |
| 15–18 h | Small web collector, scoped facts, F70/G70 transfer, second evidence cycle | Real fetched source reaches a card; mismatched comparison flagged |
| 18–21 h | Locked quality evaluation, adversarial tests, measured performance, fixes on dev only | Metrics report with sample sizes, baselines and failures |
| 21–24 h | Demo freeze, reproducible replay, presentation, judge rehearsal | Five-minute path works offline; claims match measured results |

Annotating the small gold set should happen as soon as ingestion is stable. If the team has multiple people, a human can annotate while another implements. This plan does not authorize autonomous subagent spawning or require parallel infrastructure.

## First vertical slice

Take a small G60 evidence packet including one positive, one negative, one mixed and one ambiguous comment. Preserve ID/row locators, extract signals, draft one requirement, validate evidence, calculate a policy-based score interval, have the PM challenge a premise, and save a second revision with an audit event. Do this before scaling to the full feedback corpus.

Use synthetic fixtures for unit tests and real records for a clearly labelled demo sample. No demo card should be hardcoded as the production output for a particular model or row. Persist model outputs and lineage so the path can be replayed.

## Minimum versus stretch

| Minimum in 24 hours | Stretch only after minimum passes |
|---|---|
| All supplied files inventoried; feedback/study/sales normalized; 10–20 equipment facts verified | General PDF equipment matrix extraction |
| G60 representative stratified extraction run with disclosed coverage | All 4,000 G60 IDs processed and validated |
| 6–10 reviewed requirement cards across different domains | Large requirement catalogue |
| 3–4 working public-source imports; target 6–10 if straightforward | Broad autonomous market monitoring |
| Explicit criteria/weights, missingness intervals, basic scenario comparison | Learned ranking or constrained portfolio optimizer |
| One PM review flow and two versioned evidence cycles | Multi-user enterprise approval chains |
| 120-record initial evaluation and tiny transfer slices | Expanded gold set and more languages |
| Local app, cached replay and export | Deployment and enterprise identity |

If time slips, reduce source breadth, number of requirements and UI detail. Preserve traceability, real model execution, unknown handling, PM control, held-out tests and honest metrics. Do not sacrifice these to make more cards or animations.

## Smallest viable persistence

Use a handful of tables initially: sources; canonical records; typed artifacts/evidence links; requirement revisions; policies/profiles; decisions; audit events; runs. Complex object payloads may be versioned JSON with validated schemas. Avoid implementing a separate ORM/table for every contract before the vertical slice works.

## Planned command contract

These commands are **not implemented yet**. Implement them or update this section to match the final CLI; do not tell the user they work until verified.

```text
python -m bmw_pm.cli ingest --input data/raw/provided --profile configs/g60.yaml
python -m bmw_pm.cli run --profile configs/g60.yaml --sample-manifest <path>
python -m bmw_pm.cli evaluate --split-manifest <path> --run-id <id>
python -m bmw_pm.cli replay --run-id <id>
python -m bmw_pm.cli export --run-id <id> --reviewed-only
python -m pytest
streamlit run ui/app.py
```

Use an environment template with provider key names, model IDs and budget settings, without actual credentials. Check provider availability and documented API syntax before implementation. Do not install an agent framework or vector database as the first step.

## Stop conditions and failure handling

- Parser ambiguity: quarantine affected facts and continue unaffected inputs.
- Model/API unavailable: continue deterministic ingestion/tests; use a labelled replay only if a real prior run exists. A synthetic mock does not count as model quality evidence.
- Inference exceeds budget: stop new requests, preserve completed coverage and report partial scope. Do not silently omit failures.
- Weak extraction: improve on development cases and narrow the supported taxonomy/scope with disclosure.
- No PM evaluator: report team proxy labels and show the review workflow; do not claim BMW validation.
- Low transfer performance: document the observed failure, adjust mapping using development data, and preserve the original blind result.

## Definition of done

The real provided data can be traced through normalized evidence to AI-generated, validated customer requirements. At least one public source enriches an actual argument. A visible policy deterministically calculates priorities with unknowns and regional gaps. A PM can challenge/change a requirement, producing a versioned decision and a reconstructable history. Held-out metrics, transfer checks and runtime are measured and reported. The presentation demonstrates this path and identifies what remains unvalidated.
