# Remaining-work implementation plan

The user confirmed a 24-hour build window and reported more than 12 hours remaining when this sequence was agreed. Stack: Python, SQLite and Streamlit with a provider-neutral extraction boundary. `TASKS.md` is the status source of truth. Do not restart completed bootstrap or claim the original hour-by-hour schedule still describes actual progress.

## Ordered milestones from the working slice

| Order | Deliverable | Acceptance evidence |
|---|---|---|
| 1 | Freeze 120 grouped development/test/transfer IDs and content hashes; hide legacy labels | Reproducible manifest, 30 double-labelled difficult records and adjudicated disagreements |
| 2 | Run bounded resumable structured AI extraction against the keyword baseline | Same frozen examples, valid exact spans, recorded abstentions/failures/model/tokens/latency and human-rated metrics |
| 3 | Add sales observations, 10–20 verified equipment facts and 3–4 permitted public-source claims | Each fact has source locator and scope; accepted/quarantined units reconcile; at least one fact reaches a card |
| 4 | Have the BMW PM review 10–12 cards, about 15 paired preferences, criterion anchors/objectives and swing weights | Versioned reviewer judgments; impact/business inputs use linked evidence and PM rationale; unknown feasibility stays separate |
| 5 | Implement deterministic sensitivity and demonstrate one PM challenge/new revision/historical replay | Changed contributions and unresolved pairs recompute from stored inputs; prior decision remains reconstructable |
| 6 | Measure G60/F70/G70 quality, adversarial cases, runtime and costs; freeze export and offline demo | Evaluation report with denominators, baseline and failure cases; one five-minute path works without live APIs |

The recently added YouTube research module is standalone; only validated, scoped findings imported into the decision engine count as web enrichment. If time slips, reduce source and card breadth before cutting evaluation, provenance or PM decision history.

## Working slice and next demonstration

The first G60 US baseline run already produced seven requirements with exact spans and score intervals from 3,610 eligible records. Local review, revisions and audit replay exist. It has not yet demonstrated a scored change after new external evidence or a BMW PM challenge. Build that demonstration using a positive, negative, mixed and ambiguous packet; preserve ID/row locators and both revisions.

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

## CLI status

Implemented commands: `ingest`, `run`, `list`, `review`, `edit`, `verify-audit`, `validate` and `replay`. The local database validation and 12 tests pass. The commands below are future interfaces, not current CLI functionality:

```text
bmw-pm evaluate --split-manifest <path> --run-id <id>
bmw-pm export --run-id <id> --reviewed-only
```

Current run example: `bmw-pm ingest --input data/raw/provided --profile configs/g60.json`, then `bmw-pm run --provider baseline --profile configs/g60.json --policy configs/exploratory_equal_v1.json`; `bmw-pm validate --expect-supplied-shape` checks the resulting database. Live AI uses `--provider openai --limit N` (maximum 50 per run) after locally redacted text is reviewed and credentials/model ID are configured. Implement resumable record-level persistence before depending on live runs for the final demo. Do not install a general agent framework or vector database for this slice.

## Stop conditions and failure handling

- Parser ambiguity: quarantine affected facts and continue unaffected inputs.
- Model/API unavailable: continue deterministic ingestion/tests; use a labelled replay only if a real prior run exists. A synthetic mock does not count as model quality evidence.
- Inference exceeds budget: stop new requests, preserve completed coverage and report partial scope. Do not silently omit failures.
- Weak extraction: improve on development cases and narrow the supported taxonomy/scope with disclosure.
- No PM evaluator: report team proxy labels and show the review workflow; do not claim BMW validation.
- Low transfer performance: document the observed failure, adjust mapping using development data, and preserve the original blind result.

## Definition of done

The real provided data can be traced through normalized evidence to AI-generated, human-checked customer requirements. At least one scoped public source enriches an actual argument. A visible PM-reviewed policy deterministically calculates priorities with unknowns and regional gaps. A PM challenge creates a versioned decision and a reconstructable history. Held-out metrics, transfer checks and runtime are measured and reported with sample sizes. The presentation demonstrates this path and identifies what remains unvalidated.
