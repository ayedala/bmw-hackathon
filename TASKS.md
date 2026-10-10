# Task board

Update this board with actual outcomes and evidence. Preparation completed on 10 October 2026; application implementation has not started.

## Completed preparation

- [x] Read the user's constraints and visually inspect both briefing pages.
- [x] Extract and hash eight archive files without modifying originals.
- [x] Inspect all feedback IDs, source/country/powertrain distributions and duplicate patterns.
- [x] Inspect study block layouts and all 206 US distribution sums.
- [x] Inspect sales granularity and representative equipment table/legend.
- [x] Review primary web sources and prepare scoped evidence seeds.
- [x] Write strategy, contracts, evaluation plan, PM workflow and coding instructions.
- [x] Validate local document links, nine source-file hashes, workbook counts, demo row IDs, survey distributions and illustrative arithmetic; compile inspection scripts. Results: `research/local/preparation_validation.json`. This verifies the preparation pack only, not model quality.

## P0: ship the complete path

- [ ] T01 Bootstrap environment, package, schemas, minimal persistence and run manifest.
- [ ] T02 Implement idempotent feedback adapter and annotation grouping; reconcile 10,128 IDs.
- [ ] T03 Implement survey/sales adapters and a verified equipment-fact subset with exact locators.
- [ ] T04 Freeze grouped development/test/transfer manifests; label the initial gold set.
- [ ] T05 Implement bounded structured extraction and evidence-span/reference validators.
- [ ] T06 Implement requirement drafting, support/counterevidence and assumption tracking.
- [ ] T07 Implement anchored scoring policy, unknown intervals and deterministic sensitivity.
- [ ] T08 Implement review transitions, immutable revisions, atomic audit events and replay.
- [ ] T09 Build thin UI and protected evidence drill-down; label scope/coverage and replay mode.
- [ ] T10 Import real public sources and demonstrate cleaning/applicability checks.
- [ ] T11 Run held-out evaluations, adversarial cases, transfer and latency/cost measurements.
- [ ] T12 Freeze demo, export decision report and prepare evidence-led presentation.

Dependencies: T01 → T02/T03 → T05 → T06 → T07 → T08/T09. Freeze T04 before tuning T05. T10 can begin once source contracts exist and must feed T06 before the final demo. T11 depends on frozen artifacts and splits; T12 depends on actual validation.

## P1 only after P0

- [ ] Expand full-corpus model processing if measured cost/time allow.
- [ ] Improve multilingual or unseen-schema robustness based on observed failures.
- [ ] Add embeddings only after retrieval evaluation demonstrates a need.
- [ ] Expand gold annotations and PM preference judgments.

## Per-task completion note

Record task ID, changed files, command actually run, result, evidence artifact/run ID, unresolved limits and next step. A checkbox must not imply a model evaluation or PM approval that never occurred.
