# Data contracts and validation boundaries

Implement these as typed Pydantic models plus generated JSON Schema. This document defines the contract; it is not an implemented migration. IDs are opaque strings, timestamps are timezone-aware UTC, and every persisted record carries `schema_version`. UI times may use Europe/Berlin.

## Shared conventions

- Unknown values are JSON null plus `missing_reason`; zero is a real observation. Use a distinct `not_applicable` status when appropriate.
- Counts are integers. Shares are numbers in [0,1]. Ordinal scores are [0,4] with their rubric version. Currency, units and test method are explicit.
- IDs link versioned objects; a requirement reference is `(requirement_id, revision)`, not a floating latest value.
- Hash original bytes using SHA-256. Hash normalized objects using a documented canonical JSON encoding. A hash identifies content, not whether the content is true.
- Retain both `observed_at`/`valid_from` and `ingested_at`/`recorded_at`. Do not fill observation dates from ingestion dates.
- Canonical model codes, country codes and powertrain codes use versioned mapping tables. Preserve raw labels.

## Entities

| Entity | Required fields and constraints |
|---|---|
| `SourceDocument` | source_id, local_or_web, original_name_or_url, sha256, mime_type, acquired_at, publication_date nullable, source_type, access_scope, origin_family_id, parser_version, rights_notes |
| `SourceLocator` | source_id, source_hash, locator_type; one of sheet+cell/range, page+bbox/table-cell, URL+section+span; exact quote or extracted value; normalized_text_hash when using offsets |
| `FeedbackRecord` | record_id, source_id, source_record_id, raw_text_ref, cleaned_text, redacted_text, raw_country, country, raw_model, model_code, powertrain_raw, powertrain, source_label, author_status, observed_at nullable, row_locators[], transformation_ids[] |
| `LegacyAnnotation` | annotation_id, feedback_record_id, raw_feedback_type, raw_level2, raw_level3, row_locator; explicitly marked supplied/unverified |
| `SurveyObservation` | survey_id, source_id, market, model, instrument_id, category_raw, category_canonical nullable, statistic_type, value or distribution, scale_endpoints nullable, respondent_n nullable, year, mapping_version, cell_locators[] |
| `SalesObservation` | model_scope[], scope_is_combined, market_raw, market_code, year, units, observation_status, source_locator; status supplied_historical or supplied_future_scenario |
| `EquipmentFact` | model, derivative/trim nullable, market, document_date, option_code nullable, feature, availability (standard/optional/unavailable/unknown), package_dependencies[], price nullable, currency nullable, tax_basis nullable, source_locator, verification_status |
| `ExternalClaim` | claim_id, subject, predicate, value/text, units, vehicle_scope, market, model_year nullable, conditions, claim_method, publication_date nullable, source_locator, applicability, origin_family_id |
| `Signal` | signal_id, feedback_record_id or external_claim_id, signal_type, need_domain, atomic_claim, customer_outcome, polarity, severity_label, use_context, vehicle_scope, evidence_spans[], extraction_status, run_id |
| `EvidenceLink` | link_id, target_id+revision, source_entity_id, locator, role, entails_claim (yes/no/uncertain), applicability, reviewer_or_verifier, verification_version |
| `RequirementRevision` | requirement_id, revision, title, customer_outcome, scope, use_conditions, acceptance_proposal, target_status, supporting_links[], counter_links[], alternatives[], assumptions[], missing_evidence[], feasibility, lifecycle_status, supersedes_revision nullable, created_by, created_at |
| `PolicyVersion` | policy_id, revision, name, criteria, anchors, value_functions, weights, regional_policy, coverage_rules, unknown_rules, elicitation_record, approved_by nullable, approved_at nullable |
| `VehicleProfile` | profile_id, revision, model_family, included_derivatives, alias_map, powertrains, region_map, planning_date, launch_window, objectives, competitor_cohort, equipment_sources, supplied_sales_scope, exclusions |
| `ScoreSnapshot` | requirement_id+revision, policy_id+revision, profile_id+revision, corpus_manifest_hash, criterion_inputs, contributions, lower_bound, upper_bound, scope, coverage, feasibility_status, assumptions, run_id |
| `Decision` | decision_id, requirement_id+revision, action, rationale, actor_id, role, recorded_at, policy_revision, score_snapshot_id, conditional_acceptance[], expected_revision |
| `RunManifest` | run_id, started_at, finished_at nullable, dataset_hashes, split_hash, code_revision/content_hash, provider+returned_model_id, model_parameters, prompt_hashes, schema_version, profile_revision, policy_revision, statuses, retries, tokens, cost_basis, durations |
| `AuditEvent` | event_id, monotonic_sequence, recorded_at, actor_id, actor_type, action, object_type+id+revision, before_hash nullable, after_hash nullable, reason, request_id, run_id nullable, previous_event_hash, event_hash, result |

## Stable identity and idempotency

`FeedbackRecord.record_id` derives from source-content identity plus source ID; keep a separate lineage alias when the same export is repackaged with identical records. Re-ingesting an identical source hash creates no duplicate evidence. If a workbook changes, create a new source version and compute record deltas; do not treat every unchanged record as new independent evidence.

Signal deduplication key includes record_id, normalized need and context. Multiple labels for one record may yield multiple different needs; merge only identical needs. Store the mapping from all annotation rows to the canonical record.

Requirements keep a stable ID across edits. Changes to outcome, scope, target, evidence or rationale create a new immutable revision. A score links to an exact revision and policy. Historical scores are never recomputed in place.

## Example requirement shape

Illustrative schema example only, with no real approved target or evidence:

```json
{
  "schema_version": "1",
  "requirement_id": "example-climate-access",
  "revision": 1,
  "title": "Low-effort climate adjustment",
  "customer_outcome": "Occupants can adjust frequently used climate settings with low interaction effort.",
  "scope": {"models": ["G60-successor"], "markets": ["US"], "powertrains": ["ICE", "PHEV", "BEV"]},
  "use_conditions": ["Common in-car adjustment tasks; test conditions pending"],
  "acceptance_proposal": {"method": "Comparative usability study", "target": null, "unit": null},
  "target_status": "pending_engineering_review",
  "supporting_links": [],
  "counter_links": [],
  "alternatives": ["Persistent shortcuts", "Dedicated tactile controls"],
  "assumptions": ["Task set and baseline are not yet validated"],
  "missing_evidence": ["Validated supporting evidence is required before ranking"],
  "feasibility": "unknown",
  "lifecycle_status": "draft"
}
```

Empty evidence is allowed for a draft hypothesis, but not for a grounded recommendation. A validator must reject promotion of this example as evidence-backed until resolvable support exists. Proposed successor identifiers are planning objects, not BMW production model codes.

## Validation layers

1. **Transport/schema:** types, bounds, enums, JSON shape, refusal/truncation handling.
2. **Referential integrity:** source, row/page/span, requirement revision and policy references exist.
3. **Semantic support:** quote/value supports the attached claim; units and vehicle context match; absence of equipment is not inferred from a blank cell alone.
4. **Analytical validity:** denominators, uniqueness, exclusions, comparability, missingness and contribution sums.
5. **Workflow:** role and state transitions; stale-revision conflicts; no auto-approval by a model.

Schema-valid content can still be wrong. Use structured generation plus independent domain validation; handle refusals and incomplete outputs explicitly. [OpenAI Structured Outputs documentation](https://developers.openai.com/api/docs/guides/structured-outputs)

## Required export

Produce JSON/CSV requirements, a readable Markdown decision report, and a manifest. Include version IDs, customer outcome, scope, acceptance status, evidence locators, counterevidence, rationale, score policy, missing inputs, PM decisions and history links. CSV exports should neutralize formula-like text for safe spreadsheet viewing while preserving raw text in the private source store. Export only the authorized scope; record an export audit event.

## Foreign database compatibility

`ImportedEvidenceRow` carries the snapshot SHA-256, original table name, row identity, unchanged column/value payload and `imported_unreviewed` status. Original JSON column strings and nulls remain intact. Foreign locators and sources are retained in the same snapshot namespace; these are separate from canonical feedback IDs. Canonical feedback and study records are reconstructed from original workbooks using our existing contracts, retaining all annotation rows. Imported context cannot authorize a transition or substitute for reviewed scoring inputs.
