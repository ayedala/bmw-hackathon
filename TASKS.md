# Task board

Update this board with actual outcomes and evidence. Preparation and the first local decision-engine slice were completed on 10 October 2026. Partial tasks remain open until their acceptance evidence exists.

## Completed preparation

- [x] Read the user's constraints and visually inspect both briefing pages.
- [x] Extract and hash eight archive files without modifying originals.
- [x] Inspect all feedback IDs, source/country/powertrain distributions and duplicate patterns.
- [x] Inspect study block layouts and all 206 US distribution sums.
- [x] Inspect sales granularity and representative equipment table/legend.
- [x] Review primary web sources and prepare scoped evidence seeds.
- [x] Write strategy, contracts, evaluation plan, PM workflow and coding instructions.
- [x] Validate local document links, nine source-file hashes, workbook counts, demo row IDs, survey distributions and illustrative arithmetic; compile inspection scripts. Results: `research/local/preparation_validation.json`. This verifies the preparation pack only, not model quality.

## P0: next work in order

- [x] **T01** Bootstrap environment, package, schemas, minimal persistence and run manifest.
- [x] **T02** Implement idempotent feedback adapter and annotation grouping; reconcile 10,128 IDs.
- [ ] **T04 — next:** Freeze a hash/versioned 120-record grouped manifest: 60 G60 development, 30 blind G60 test, 15 blind F70, 15 blind G70. Team-label atomic needs, polarity, scope and exact spans without legacy labels; double-label 30 difficult records and adjudicate disagreements. Keep evaluation records out of prompt tuning.
- [ ] **T05 — partial:** The keyword baseline and bounded structured OpenAI provider validate exact spans. After T04, add per-record resumable live jobs, persisted failures/abstentions and model/latency/token metadata; compare both extractors on identical frozen examples. Human entailment review is outstanding.
- [ ] **T03 — partial:** The feedback and customer-study adapters work. Add sales observations and 10–20 manually verified, market/derivative/date-scoped equipment facts with exact cell/page/table locators. Reconcile accepted plus quarantined source units.
- [ ] **T06 — partial:** Customer-outcome candidates, support, praise/preservation, context and explicit assumptions work for feedback. Link the separately scoped study, sales, equipment and public-source facts to actual cards; obtain human review of material claims.
- [ ] **T07 — partial:** Deterministic four-criterion score intervals and customer/business views work. Only reach is data-derived in the real run. Obtain PM objectives, anchored impact/strategy/competitive ratings and swing weights; implement reproducible weight/evidence-removal sensitivity. Keep engineering feasibility and cost separate and unknown without reviewed inputs.
- [ ] **T08 — partial:** Review transitions, immutable revisions, audit events and replay work locally. Verify a PM challenge against new evidence creates a new score/revision while the earlier decision remains reconstructable; document local identity limits.
- [ ] **T09 — partial:** The thin Streamlit UI exposes evidence, score contributions, uncertainty, review and history. Add a clear run-mode/replay label and the completed evidence channels when available; check source drill-down and access/export audit behavior.
- [ ] **T10:** Import 3–4 permitted public sources with URL/date/origin and scoped claims; reject or flag mismatched model, market, year and test conditions. A standalone YouTube research module is present in the repository but is not yet integrated or verified as decision-engine evidence.
- [ ] **T11:** Run held-out extraction, human citation-entailment and requirement-quality checks; obtain BMW PM card ratings and paired preferences; report G60/F70/G70 transfer, adversarial cases, coverage, latency and token/cost basis with denominators.
- [ ] **T12:** Freeze one sourced PM challenge → new revision → deterministic sensitivity → historical replay story; export a readable decision report and a labelled offline fallback, rehearse the presentation, and verify the final pushed commit has an Entire checkpoint.

Sequence: T04 before prompt tuning or AI quality claims; then T05 and scoped T03/T10 facts; then T06/T07 PM review; then T08/T09 demonstration, T11 measurement and T12 freeze. Reduce breadth of sources/cards if time tightens; preserve traceability and honest evaluation.

## P1 only after P0

- [ ] Expand full-corpus model processing if measured cost/time allow.
- [ ] Improve multilingual or unseen-schema robustness based on observed failures.
- [ ] Add embeddings only after retrieval evaluation demonstrates a need.
- [ ] Expand gold annotations and PM preference judgments.

## Per-task completion note

Record task ID, changed files, command actually run, result, evidence artifact/run ID, unresolved limits and next step. A checkbox must not imply a model evaluation or PM approval that never occurred.

### 10 October 2026: decision-engine slice

- T01/T02: `pyproject.toml`, `src/bmw_pm/contracts.py`, `storage/database.py`, `ingestion/feedback.py`, and `pipeline.py` provide typed records, immutable storage, grouped feedback IDs, and run manifests. Fresh local ingestion into ignored `data/processed/decision_engine_v2.db` reconciled F70 2,128/4,076, G60 4,000/5,005, and G70 4,000/4,690 unique IDs/annotation rows; no quarantine. This is structural correctness, not extraction accuracy.
- T05/T06 partial: the baseline and optional structured provider emit exact-span signals; candidate construction now separates complaint/aspiration support, praise/preservation, and ambiguous/descriptive context. All links retain `semantic_entailment=unreviewed` and `author_expertise=unknown`. Fresh G60 US baseline run `run_718cff7f57b44facba7d4853f0bc59d8` processed 3,610 eligible records, emitted 2,518 signals and seven candidate requirements. No live AI model-quality evaluation or independent claim-entailment review has occurred.
- T07 partial: explicit customer and business criterion groups, dimension intervals, feasibility status, and unresolved pairwise comparisons are implemented under the unapproved equal-weight policy. Customer impact, both business criteria, and engineering feasibility remain unknown in the real run. Deterministic sensitivity scenarios still remain to implement.
- T08/T09 partial: local review/edit, immutable revisions, audit verification/replay and a thin Streamlit evidence/score/review view exist. Full evidence-change demonstration, replay-mode labelling and access/export coverage remain open.
- Software verification actually run: `.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp 'D:\ChatGPT\bmw challenge\.tmp\pytest'` passed 12 tests. `.venv\Scripts\python.exe -m bmw_pm.cli --db data/processed/decision_engine_v2.db validate --expect-supplied-shape` passed feedback/study reconciliation (10,128 IDs; 13,771 annotation rows; 185 means; 206 distributions), 2,518 citation/span checks, seven unique-ID recurrence checks, engineering unknowns and audit-chain validation. These are structural/software checks, not human-rated accuracy or PM agreement.
- No live AI comparison, independently labelled extraction/entailment result, sales/equipment/web integration, sensitivity report or F70/G70 transfer metric has been recorded. No BMW-approved requirement or policy weights are claimed.
