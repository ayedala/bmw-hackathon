/**
 * TypeScript mirrors of the Pydantic domain contracts.
 *
 * Sources of truth:
 *   - src/bmw_pm/contracts.py              (requirements, scores, decisions, audit)
 *   - external_research_pipeline/models.py (ProcessedEvidence and vocabularies)
 *
 * Field names are kept identical (snake_case) so a JSON payload from either
 * Python package can be consumed without a mapping layer.
 */

/* ------------------------------------------------------------------ */
/* src/bmw_pm/contracts.py                                             */
/* ------------------------------------------------------------------ */

export type LocatorType = "sheet_range" | "page_region" | "url_span";

export interface SourceLocator {
  schema_version: string;
  source_id: string;
  source_hash: string;
  locator_type: LocatorType;
  sheet: string | null;
  cell_range: string | null;
  page: number | null;
  section: string | null;
  exact_quote: string | null;
  extracted_value: string | null;
  normalized_text_hash: string | null;
}

export type Polarity = "complaint" | "praise" | "aspiration" | "observation" | "mixed";
export type ProviderMode = "baseline_no_ai" | "live_ai" | "cached_replay";

export interface EvidenceSpan {
  record_id: string;
  locator: SourceLocator;
  text: string;
  start: number;
  end: number;
}

export interface Signal {
  schema_version: string;
  signal_id: string;
  feedback_record_id: string;
  signal_type: "customer_feedback";
  need_domain: string;
  atomic_claim: string;
  customer_outcome: string;
  polarity: Polarity;
  severity_label: string | null;
  use_context: string | null;
  vehicle_scope: { model: string | null; country: string | null; powertrain: string | null };
  evidence_spans: EvidenceSpan[];
  extraction_status: "validated";
  run_id: string;
  provider_mode: ProviderMode;
}

export interface RequirementScope {
  models: string[];
  countries: string[];
  powertrains: string[];
  use_cases: string[];
}

export interface AcceptanceProposal {
  method: string;
  target: number | string | null;
  unit: string | null;
}

export type EvidenceRole = "supports" | "preserves" | "context";

export interface RequirementEvidenceLink {
  signal_id: string;
  role: EvidenceRole;
  atomic_claim: string;
  locator: SourceLocator;
  exact_span_checked: boolean;
  semantic_entailment: "unreviewed" | "reviewed_supports" | "reviewed_rejects";
  provenance: "supplied_anonymized";
  author_expertise: "unknown";
}

export type TargetStatus = "pending_engineering_review" | "proposed_target" | "reviewed_target";
export type Feasibility = "unknown" | "conditional" | "feasible_reviewed" | "blocked";

export interface EvidenceReference {
  evidence_id: string; evidence_kind: "internal_feedback" | "external_web" | "youtube" | "study" | "planning_context";
  role: "supports" | "opposes" | "context";
  source_url: string | null; source_title: string | null; source_family: string | null;
  market: string | null; vehicle: string | null; topic: string | null; subtopic: string | null;
  published_at: string | null; retrieved_at: string | null; stance: string | null;
  source_quality: number | null; confidence: number | string | null;
  independence_group: string | null; duplicate_of: string | null;
  claim: string; exact_text: string; source_start_char: number | null; source_end_char: number | null;
  source_locator: Record<string, unknown>; provenance: Record<string, unknown>;
  semantic_entailment: "unreviewed" | "reviewed_supports" | "reviewed_rejects";
}

export interface RequirementRevision {
  evidence_references?: EvidenceReference[];
  topic?: string | null;
  planning_horizon?: string | null;
  need_ids?: string[];
  finding_ids?: string[];
  canonical_provenance?: Record<string, unknown>;
  schema_version: string;
  requirement_id: string;
  revision: number;
  title: string;
  customer_outcome: string;
  scope: RequirementScope;
  use_conditions: string[];
  acceptance_proposal: AcceptanceProposal;
  target_status: TargetStatus;
  supporting_signal_ids: string[];
  counter_signal_ids: string[];
  context_signal_ids: string[];
  evidence_links: RequirementEvidenceLink[];
  context_observation_ids: string[];
  alternatives: string[];
  assumptions: string[];
  missing_evidence: string[];
  feasibility: Feasibility;
  implementation_cost: null;
  implementation_cost_missing_reason: string;
  lifecycle_status: "draft" | "needs_review";
  supersedes_revision: number | null;
  created_by: string;
  created_at: string;
  denominator_feedback_records: number;
  processed_feedback_records: number;
  support_count: number;
  counter_count: number;
}

export interface CriterionDefinition {
  dimension: "customer" | "business";
  weight: number;
  anchor_0: string;
  anchor_4: string;
}

export interface PolicyVersion {
  schema_version: string;
  policy_id: string;
  revision: number;
  name: string;
  criteria: Record<string, CriterionDefinition>;
  saturation_share: number;
  unknown_rule: string;
  approved: boolean;
  elicitation_record: string;
}

export interface CriterionInput {
  value: number | null;
  lower_value: number | null;
  upper_value: number | null;
  basis: string | null;
  missing_reason: string | null;
}

export interface DimensionInterval {
  lower_bound: number;
  upper_bound: number;
  criteria: string[];
  missing_criteria: string[];
  interpretation: string;
}

export interface ScoreSnapshot {
  schema_version: string;
  score_snapshot_id: string;
  requirement_id: string;
  requirement_revision: number;
  policy_id: string;
  policy_revision: number;
  profile_id: string;
  profile_revision: number;
  corpus_manifest_hash: string;
  criterion_inputs: Record<string, CriterionInput>;
  /** [lower, upper] contribution in score points per criterion. */
  contributions: Record<string, [number, number]>;
  dimension_intervals: Record<string, DimensionInterval>;
  lower_bound: number;
  upper_bound: number;
  scope: RequirementScope;
  coverage: Record<string, string | number>;
  feasibility_status: string;
  feasibility_basis: string;
  evidence_review_status: "unreviewed" | "human_reviewed";
  assumptions: string[];
  run_id: string;
}

export type DecisionAction = "approve" | "reject" | "edit" | "challenge" | "defer";

export interface Decision {
  schema_version: string;
  decision_id: string;
  requirement_id: string;
  requirement_revision: number;
  action: DecisionAction;
  rationale: string;
  actor_id: string;
  role: "pm" | "engineering_reviewer" | "demo_pm";
  recorded_at: string;
  policy_revision: number | null;
  score_snapshot_id: string | null;
  expected_revision: number;
  request_id: string;
}

export interface AuditEvent {
  schema_version: string;
  event_id: string;
  monotonic_sequence: number;
  recorded_at: string;
  actor_id: string;
  actor_type: string;
  action: string;
  object_type: string;
  object_id: string;
  object_revision: number | null;
  before_hash: string | null;
  after_hash: string | null;
  reason: string;
  request_id: string;
  run_id: string | null;
  previous_event_hash: string;
  event_hash: string;
  result: "success" | "failure" | "noop";
}

export interface VehicleProfile {
  schema_version: string;
  profile_id: string;
  revision: number;
  model_family: string;
  countries: string[];
  powertrains: string[];
  domain_applicability: Record<string, string[]>;
  powertrain_aliases: Record<string, string>;
  alias_assumptions: Record<string, string>;
  planning_date: string;
  launch_window: string | null;
  objectives: string[];
  uncovered_regions: string[];
  notes: string[];
}

/* ------------------------------------------------------------------ */
/* external_research_pipeline/models.py                                */
/* ------------------------------------------------------------------ */

export const SOURCE_FAMILIES = [
  "government_statistics",
  "independent_test_org",
  "official_manufacturer",
  "professional_review",
  "market_report",
  "youtube_review",
  "customer_forum",
  "reddit",
  "app_review",
  "dealer",
  "other",
] as const;
export type SourceFamily = (typeof SOURCE_FAMILIES)[number];

export const TOPICS = ["infotainment", "charging", "comfort", "range", "market_trend"] as const;
export type Topic = (typeof TOPICS)[number];

export type Stance = "supports" | "contradicts" | "neutral";

/** Mirror of models.SUBTOPIC_ALIASES: earlier names mapped to the canonical subtopic. */
export const SUBTOPIC_ALIASES: Record<string, string> = {
  charging_infrastructure: "charging_network",
  charging_network_growth: "infrastructure_growth",
  future_customer_expectation: "customer_expectation",
  ev_adoption: "adoption_trend",
};

export interface ProcessedEvidence {
  evidence_id: string;
  source_url: string;
  source_name: string;
  source_title: string;
  source_family: SourceFamily;
  published_at: string | null;
  retrieved_at: string;
  brand: string;
  vehicle: string;
  market: string;
  topic: Topic;
  subtopic: string;
  claim: string;
  evidence_text: string;
  source_start_char: number;
  source_end_char: number;
  numeric_value: number | null;
  numeric_unit: string | null;
  source_quality: number;
  independence_group: string;
  duplicate_of: string | null;
}

export interface ResearchRun {
  run_id: string;
  started_at: string;
  finished_at: string | null;
  mode?: string;
  topic: string;
  pages_with_evidence?: number;
  pages_failed?: number;
  queries_attempted: number;
  search_results_found: number;
  pages_scraped: number;
  pages_loaded_from_cache?: number;
  evidence_records_created: number;
  evidence_duplicates_found: number;
  firecrawl_search_calls: number;
  firecrawl_scrape_calls: number;
  llm_calls: number;
}

/** research/web_evidence_seed.jsonl — curated, not yet validated. */
export interface WebResearchSeedRecord {
  record_kind: "research_seed_not_validated_external_claim";
  seed_id: string;
  source_id: string;
  url: string;
  publication_date: string | null;
  section: string;
  claim: string;
  value?: number;
  unit?: string;
  claim_method: string;
  scope: Record<string, string | number | null>;
  limitation: string;
  retrieved_on: string;
  capture_method: string;
  source_snapshot_hash: string | null;
  needs_refetch_and_locator_validation: boolean;
  reuse_review_status: string;
}

/* ------------------------------------------------------------------ */
/* src/bmw_pm/contracts.py — successor planning (origin/main 42dc8ab)  */
/* ------------------------------------------------------------------ */

/** Ordinal PM judgements 0–4. Uncertainty counts against priority. */
export interface PriorityFactors {
  impact: number;
  evidence: number;
  relevance: number;
  uncertainty: number;
}

/** Weights must sum to one. Defaults mirror PriorityPolicy() in Python. */
export interface PriorityPolicy {
  impact: number;
  evidence: number;
  relevance: number;
  uncertainty: number;
}

export interface PriorityAssessment {
  assessment_id: string;
  requirement_id: string;
  requirement_revision: number;
  sequence: number;
  factors: PriorityFactors;
  policy: PriorityPolicy;
  score: number;
  actor_id: string;
  rationale: string;
  recorded_at: string;
  request_id: string;
  interpretation: string;
}

export interface SuccessorProposal {
  domain: string;
  title: string;
  outcome: string;
  value: string;
  interpretation: string;
  future_assumption: string;
  contrary: string;
  validation: string;
  review_trigger: string;
  anchor_ids: string[];
  factors: PriorityFactors;
}

export interface SuccessorProposalFile {
  version: string;
  status: string;
  planning_window: string;
  proposals: SuccessorProposal[];
}

/** A human assessment of one candidate evidence-to-requirement link. */
export interface EvidenceLinkJudgment {
  schema_version: string;
  judgment_id: string;
  requirement_id: string;
  requirement_revision: number;
  signal_id: string;
  verdict: "supports" | "does_not_support" | "context_only";
  rationale: string;
  actor_id: string;
  recorded_at: string;
  request_id: string;
}

/** configs/planning_public_context.json */
export interface PlanningContextSource {
  title: string;
  url: string;
  observation: string;
  use: string;
}
