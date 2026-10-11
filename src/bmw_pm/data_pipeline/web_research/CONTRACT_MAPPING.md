# External evidence chain: why it is separate, and how to merge it later

## Why these artifacts are additive rather than written into `src/bmw_pm`

`src/bmw_pm/contracts.py` already models the whole chain — `Signal`,
`RequirementRevision`, `RequirementEvidenceLink`, `ScoreSnapshot`,
`PolicyVersion`, `Decision`, `AuditEvent` — and `decision/scoring.py` already
scores requirements against `configs/exploratory_equal_v1.json`.

Those contracts are purpose-built for the **supplied internal feedback
dataset**, and four fields make them unable to hold public web evidence without
editing a shared file:

| Contract field | Constraint | Why web evidence cannot satisfy it |
|---|---|---|
| `Signal.signal_type` | `Literal["customer_feedback"]` | web research is not customer feedback |
| `Signal.feedback_record_id` | required | there is no feedback record behind a scraped page |
| `RequirementEvidenceLink.provenance` | `Literal["supplied_anonymized"]` | public pages are not supplied or anonymised |
| `SourceLocator.source_hash` | `^[0-9a-f]{64}$` | the pipeline stores canonical URL + char offsets, not an archive hash |
| `RequirementRevision.denominator_feedback_records` | required, `ge=0` | there is no feedback-record denominator for a web corpus |

Widening those `Literal`s would modify a shared teammate file and risks
`tests/test_scoring.py` and `tests/test_provenance.py`. So this chain is kept
additive and parallel, and this document is the conversion contract.

**Nothing in `src/`, `tests/`, `configs/`, `web/` or the canonical evidence file
was modified.**

## Field mapping, for whoever reconciles the two chains

### finding → `Signal`

A finding is an aggregate, so one finding maps to one `Signal` per supporting
evidence row, or to a single `Signal` whose `atomic_claim` is the finding title.

| finding field | `Signal` field | note |
|---|---|---|
| `finding_id` | `signal_id` | prefix differs (`FND-` vs their scheme) |
| — | `feedback_record_id` | **needs a value**; use the evidence `source_url` or a synthetic external id |
| — | `signal_type` | needs a new member, e.g. `"external_research"` |
| `topic` | `need_domain` | vocabularies already align closely |
| `title` | `atomic_claim` | |
| `summary` | `customer_outcome` | |
| `finding_kind` | `polarity` | `bmw_weakness`/`customer_friction` → `complaint`; `bmw_strength` → `praise`; `market_trend` → `observation`; findings with `contradicts` → `mixed` |
| `vehicles_covered`, `markets_covered` | `vehicle_scope` | |
| `evidence_ids` | `evidence_spans[].record_id` | the pipeline holds `source_start_char`/`source_end_char`, which map to `EvidenceSpan.start`/`end` |

The pipeline's `source_start_char`/`source_end_char` were built for exactly this
purpose: every evidence row addresses a verbatim span of the captured page, so
`EvidenceSpan` can be populated without re-deriving anything.

### requirement → `RequirementRevision`

| requirement field | `RequirementRevision` field |
|---|---|
| `requirement_id` | `requirement_id` |
| `title` | `title` |
| `requirement` | `customer_outcome` |
| `validation_method` | `acceptance_proposal.method` |
| `assumptions` | `assumptions` |
| `missing_evidence` | `missing_evidence` |
| `status: "draft_unapproved"` | `lifecycle_status: "draft"` |
| `rough_effort`, `rough_cost` | `feasibility` + `implementation_cost_missing_reason` |
| `finding_ids` | `supporting_signal_ids` |
| findings listed in `contradicts` | `counter_signal_ids` |
| `need_ids` | no equivalent — the internal chain has no customer-need layer |
| — | `denominator_feedback_records`, `processed_feedback_records` | **no web equivalent**; would need a declared external denominator |

`customer_needs.jsonl` has **no counterpart** in the internal contracts. If the
team wants the need layer, it is a new contract rather than a mapping.

## Scoring: reused weights, one declared deviation

`requirement_scores.jsonl` reuses the four criteria and their 0.25 weights
verbatim from `configs/exploratory_equal_v1.json`, so external and internal
requirements are scored on the same axes.

One criterion is redefined, and every emitted score carries the deviation text:

| criterion | weight | definition used |
|---|---:|---|
| `customer_impact` | 0.25 | their anchors, unchanged |
| `evidence_backed_reach` | 0.25 | **deviation** — independent public sources ÷ widest-supported requirement in the batch, × 4. Their approved definition is a share of eligible internal feedback records, which web evidence cannot supply |
| `strategic_contribution` | 0.25 | their anchors, unchanged |
| `competitive_outlook_need` | 0.25 | their anchors, unchanged |

Every score is `"approved": false` and carries `policy_id`,
`derived_from`, the weights, the 0–4 components and the reach formula, so no
number is unexplained. `configs/exploratory_equal_v1.json` was **not** edited.

## What these artifacts deliberately do not claim

- **No customer prevalence.** 30 independent public sources cannot establish
  what share of BMW customers hold a view. Findings report independent-source
  counts, never population shares.
- **No approved targets.** Every requirement is `draft_unapproved` with a
  `validation_method` rather than a number to hit, and the numeric targets that
  do appear are quoted from the evidence, not set here.
- **No engineering authority.** `rough_effort` and `rough_cost` are coarse
  planning bands, not estimates.
- **Contradictions preserved.** Findings that disagree cite each other in
  `contradicts`; the validator fails if a reference does not resolve.
