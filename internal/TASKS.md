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

### 10 October 2026: local workspace database compatibility (T02/T03)

- Pulled `main` with `git pull --ff-only` to `907cac6`, preserving the existing local `WebResearchSeed` change.
- Added `ImportedEvidenceRow`, `ingestion/legacy_database.py`, `import-workspace`/`context` CLI commands, synthetic import tests and an audited UI evidence-context browser. Rebuilds canonical feedback/studies from hash-checked raw copies; retains foreign source/locator/transformation, sales/equipment/external and competitor/discovery rows as unreviewed context in an isolated snapshot namespace. Foreign SQL and decisions never execute in our active schema.
- Actual checks: `python -m pytest -q -p no:cacheprovider --basetemp .tmp/pytest` passed 14 tests, including duplicate invariance, unseen synthetic model/unknown powertrain, citation provenance, stale revisions and replay. Initial test invocation lacked the temporary parent directory; created it and reran successfully.
- `python -m bmw_pm.cli run --provider baseline` on imported data produced run `run_e4e05c6546444185bc403e545c722486`: 3,610 eligible/processed G60 US feedback records and seven candidate cards. `python -m bmw_pm.cli validate --expect-supplied-shape` passed; local artifacts are `data/processed/import-baseline-run.json` and `data/processed/validation-import.json`.
- Limits: no live LLM inference, human-labelled model-quality or physical feasibility evaluation was run. Imported context does not automatically affect scores. Equipment and external claims require claim-specific review. T03 remains partial; no prompt tuning or PM approval performed.

- Completed context import: 16 original source documents, 14,150 locators, 10,131 transformations, 36 sales observations, three equipment facts, 52 external claims, 21 source-access registry entries, 17 competitor vehicles/23 cohort links and 10 discovery leads. Zero foreign-key violations in the archive. Canonical totals: 10,128 feedback IDs, 13,771 annotations and 391 study observations. Private snapshot SHA-256 `acf80a3a4d7c24f895226cb1cadc13ef00053c40b37b6372ec50cf502b4f7b07`.
- Repeated `import-workspace`: passed exact before/after count comparison for feedback, annotations, studies, all 24,475 imported context rows, 19 audit events and seven requirement revisions; repeat took 24.0 seconds. Evidence: ignored `data/processed/import-idempotency.json`. Fixed the study adapter's repeated XML reparsing by using non-streaming access for the small aggregate workbook; formulas remain unevaluated. Final suite rerun passed 14 tests and the complete dataset validation passed.

### 10 October 2026: hosted app preparation (T09)

- Added `HostedSettings`, `hosting.py`, `ui/hosting_access.py`, protected hosted UI routing, Docker/Render persistent-disk configuration, a whitelist-only Docker context, and `scripts/prepare_hosted_database.py`. Hosted access fails closed before opening evidence; fixed server database path, separate team/setup secrets, session expiration, audited workbench reads and hash-approved one-time restore preserve the existing decision history. Raw foreign quote-locator tables are excluded from the hosted UI selector.
- Ran `python scripts/prepare_hosted_database.py` with `PYTHONPATH=src`: prepared a private 193,921,024-byte WAL-consistent snapshot under ignored `exports/hosted/`. SHA-256 `6bddcd6d6b6a94ad6f19eefd8a0138e87296ae90b9b06f299385281b52adc6da` is recorded in its local manifest. Snapshot creation recorded an export audit event. No cloud upload or provisioning occurred.
- Full private restore to `.tmp/hosted-restore/bmw_pm.db` passed integrity/reference checks, supplied dataset reconciliation, citations, unique-ID recurrence, unknown engineering inputs and audit validation. Authenticated Streamlit AppTest rendered the actual restored cards successfully; full restore/validation/UI check took 16.2 seconds on this machine (not a cloud latency result). Evidence: ignored `exports/hosted/verification.json`.
- Hosting tests cover fail-closed and incorrect-password access, unicode comparison, approved hash/tamper detection, invalid source rejection, existing-history preservation, login-before-evidence and audited hosted reads. No live inference or model-quality claim. Shared passwords do not establish personal reviewer identity.
- Deployment blocker: no Render account connection is confirmed. Docker's engine is not running, so no container-build or real HTTPS/redeploy test was run. Paid compute/disk provisioning remains unapproved. `docs/HOSTING.md` describes the concrete plan and setup; the app is not live.
### 10 October 2026: repository organization

- Moved agent instructions, the task and decision registers, the implementation plan, and the Codex kickoff into `internal/`; kept runtime prompt specifications under `prompts/`. Rewrote the root `README.md` around the project approach. The root `AGENTS.md` is intentionally absent, so coding agents must read `internal/AGENTS.md` explicitly during development.
- Updated path references and the preparation validator to inspect repository-owned Markdown and to tolerate removal of `internal/` for submission. `scripts/validate_preparation.py` passed all 12 checks across 29 Markdown files; `pytest -q -p no:cacheprovider` passed 12 software tests; `git diff --check` passed. No model-quality measurement was made.

### 10 October 2026: merge integration and hosting

- Included the remaining `WebResearchSeed` typed contract and integrated main's `internal/` reorganization. Retained both the import/hosting instructions and the updated project overview; preserved all task-board validation notes at `internal/TASKS.md`.
- `python -m pytest -q -p no:cacheprovider --basetemp .tmp/pytest-merge` passed 19 software tests before the documentation merge. Private databases/exports remain excluded from Git. Hosting is prepared, not deployed.

### 10 October 2026: YouTube search failure recovery (T10 supporting fix)

- Acceptance: retry transient YouTube HTTP 429/5xx responses within a bounded budget; retain discovered videos on rate/quota interruption; checkpoint each search page; display a specific blocked-search message; redact credentials from new HTTP diagnostics.
- Changed `youtube_research_agent/agent.py`, frontend status messaging, regression tests and temporary-output ignore rules. No provider or evidence extraction policy changed.
- Verification: `.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .test-tmp-rate-limit-approved` from the YouTube folder passed 16 tests, including retry exhaustion, credential redaction, partial discovery preservation and empty blocked-run status. Initial sandbox test attempts hit Windows temporary-directory permissions; the approved run passed.
- The local review server was restarted. Live YouTube recovery and actual Google quota status remain unverified; no full paid research run was launched. Dataset reconciliation, unseen-model, unknown-input, revision and replay checks were not rerun for this isolated search transport/UI fix. Existing quote/timestamp and duplicate selection tests passed.

### 10 October 2026: transcript IP-block handling and reuse (T10 supporting fix)

- Acceptance: the first IpBlocked/RequestBlocked stops all further live transcript requests in that run; cached transcripts remain usable and origins are explicit. Cache keys include video ID and ordered requested languages; corrupt or mismatched cache entries are ignored. Original legacy transcripts are preserved.
- Changed agent, frontend blocked status, README and tests. Newly retrieved captions are written atomically to a cache within the existing ignored output directory. No claim of live model replay: cached captions still pass to extraction normally.
- Verification: `.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .test-tmp-transcript-approved` passed 18 tests. New tests verify one blocked network attempt, subsequent uncached skip, subsequent cached processing, language isolation and corrupted-cache rejection. Live transcript availability was not tested; no attempt was made to bypass YouTube restrictions. Dataset reconciliation, unseen-model, unknown-input, revision and audit replay checks were not run for this isolated transport change.

### 10 October 2026: confirmed daily YouTube search quota exhaustion

- Latest local diagnostic explicitly reports HTTP 429 with quota metric Search Queries and limit Search Queries per day. No live transcript retrieval occurred in that run.
- Daily quota responses now avoid transient retries; frontend explains daily allowance exhaustion separately from IP blocking and OpenAI tokens. HTML responses disable browser caching.
- Verification: YouTube suite passed 19 tests with `.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .test-tmp-daily-quota` (approved outside sandbox). Added daily-limit no-retry regression. Google quota increase/reset and a successful live run remain unverified. Broader dataset/revision/replay acceptance checks not rerun for this transport-message fix.

### 10 October 2026: authorized file analysis fallback (T10 supporting slice)

- Acceptance: analyze timestamped subtitles or transcribe authorized media without YouTube network requests; preserve original bytes and SHA-256, maintain timestamp quote validation, reuse content-identical media transcriptions, expose results in saved runs and report failed provider access honestly.
- Added typed Upload contract, subtitle timing parser, official OpenAI whisper-1 segment transcription adapter, local ignored media cache, isolated upload runs, asynchronous HTTP upload route with size/origin validation, and Analyze a file form. Model/source provenance and unknown metadata remain explicit. No web access controls are bypassed.
- Verification: `.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .test-tmp-upload-http` passed 32 tests. Fixture-based tests cover preserved uploads, rejected unsupported/unauthorized input, subtitle timing, source unknowns, quote rejection, media cache reuse, provider failure and HTTP routing/origin protection. `python -m compileall -q upload_research.py web.py` passed.
- Limitations: no authorized real media file was available, so live speech transcription and extraction were not run; account model access is unverified. This fallback requires file input and does not restore automatic YouTube discovery. Browser automation unavailable; HTML/server response verified by HTTP. Broader dataset reconciliation, unseen-model, unknown-input, revision and replay evaluation checks were not rerun for this input adapter. No accuracy measurement is claimed.
