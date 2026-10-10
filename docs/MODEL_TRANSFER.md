# Transfer to other vehicles, markets and unseen data

## Default and held-out scope

Use G60 for the first full path because its supplied family sales are highest and its feedback covers ICE, PHEV and BEVE. G68 is a related regional variant, not an alias for G60. The supplied study has China G68 summaries but there is no G68 feedback file or separate equipment PDF.

Ingest F70 and G70 now, freeze transfer test IDs, and withhold their blind labels from prompt development. Switching a dropdown alone does not demonstrate generalization.

## Configuration versus core logic

| Change for another vehicle | Exact configuration change | What should remain unchanged |
|---|---|---|
| Model family and derivatives | Alias map, generation, body/variant scope and predecessor links | Source lineage and requirement schema |
| Powertrain applicability | Allowed powertrains and feature applicability rules | Evidence validation and unknown handling |
| Market coverage | Country-to-sales-region map, source availability and selected planning scenario | Regional scoring and missingness semantics |
| Product positioning | PM-authored objectives, anchored value rubric, elicited weights | Scoring arithmetic and policy versioning |
| Equipment | New trim/option mappings, market/date-scoped baseline | Table-fact schema and source locators |
| Competitors | Comparable class, price band, market, model year, powertrain and tests | Comparison eligibility rules |
| Language | Locale-aware preprocessing, translation record and multilingual gold examples | Exact original evidence preservation |
| Taxonomy | Extend domain labels and mapping examples where needed | Atomic signals and open `other` category |
| Engineering constraints | Reviewed constraints, dependencies, cost/effort evidence | Commitment gate and conditional approvals |
| Evaluation | New blind examples and transfer baselines | Metric definitions and honest coverage reporting |

Keep these in a versioned `VehicleProfile`/`PolicyVersion`; avoid `if model == 'G70': priority += 20`. Do not fine-tune a separate model for each vehicle within this sprint.

## F70 adjustments

Use the provided ICE-only feedback scope. Charging/range requirements for battery-electric vehicles are inapplicable unless the PM explicitly opens a future-BEV scenario, which then needs new evidence and cannot inherit current sales proportions. The supplied F70 sales sheet has zeros for CN/US; this is source context, not proof that future demand is impossible.

Candidate positioning themes such as affordability, compact-car practicality and control usability are hypotheses to test against data, not default higher weights. F70's GB/JP-heavy sample needs its own coverage panel. All supplied feedback is Source A, so source-type transfer performance cannot be assumed from G60's mixture.

## G70 adjustments

Include ICE/PHEV/BEV context and the G70 study/option list. Candidate customer roles such as driver and rear passenger may require distinct use cases; do not assume every 7 Series owner uses a chauffeur. Its US-heavy sample does not establish global luxury priorities. If PM strategy values rear comfort or premium materials, encode and justify the objective, then measure how evidence supports it.

## G68 and China

Preserve G68 as distinct from G60. Use the supplied China study, W01 as historical product context, and newly collected China-specific sources where available. Keep missing verbatims and missing current equipment verification visible. Do not transfer US complaints, owner rates or DE option availability as if locally observed. Chinese-language collection requires actual language evaluation, not translation by country stereotype.

## Unseen judge data procedure

1. Inspect file type, size, encoding, headers, units and sample records locally.
2. Detect schema matches; propose mappings with confidence reasons, confirming only ambiguous semantics.
3. Assign a new immutable source/version and preserve raw fields.
4. Run validation and reconciliation; quarantine unknown units, model aliases and malformed records.
5. Reuse the same extraction schema and scoring policy unless a documented scope change requires a new profile.
6. Extract a small batch, validate evidence links, report out-of-domain and abstention rates.
7. Recompute affected proposals and scores with an explicit input diff.
8. Present transfer metrics and uncovered assumptions before claiming comparable quality.

If the new data omits sales, offer regional evidence ranking without invented business exposure. If it omits dates, disable trend inference. If it concerns a new generation, do not silently join predecessor equipment. An app that states these limits and proceeds with supported work demonstrates controlled transfer.

## Transfer acceptance

Must pass the same provenance, deduplication, missingness, prompt-injection and revision tests. Report F70/G70 extraction and grounding separately, with small-sample uncertainty and compared to the G60 test set. A performance drop should trigger better mappings, examples or annotation; do not hide it with changed metrics or weaker thresholds.
