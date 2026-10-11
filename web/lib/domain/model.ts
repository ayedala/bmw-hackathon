/**
 * UI view models. These are derived groupings over the contracts in
 * ./contracts.ts — they are not new persisted entities. Every view model
 * keeps the contract IDs it was built from so the PM can trace back.
 *
 *   Source → Evidence → Hypothesis → Finding → Customer need → Requirement
 *          → Score snapshot → PM decision → Audit event
 */
import type {
  AuditEvent,
  Decision,
  PlanningContextSource,
  PolicyVersion,
  PriorityAssessment,
  ProcessedEvidence,
  RequirementRevision,
  ResearchRun,
  Signal,
  SuccessorProposal,
  SourceFamily,
  Stance,
  Topic,
  VehicleProfile,
  WebResearchSeedRecord,
} from "./contracts";

export const MARKETS = ["US", "DE", "CN", "EU"] as const;
export type MarketCode = (typeof MARKETS)[number];

export const MARKET_LABEL: Record<MarketCode, string> = {
  DE: "Germany",
  US: "United States",
  CN: "China",
  EU: "Europe (excl. DE)",
};

/** Where a record came from. Shown on every evidence row. */
export type Provenance = "bmw_record" | "pipeline" | "curated_seed" | "synthetic";

/** Feedback signals use a family that the external pipeline does not have. */
export type UiSourceFamily = SourceFamily | "supplied_feedback";

export type EvidenceKind = "external_claim" | "customer_feedback";

export interface EvidenceItem {
  id: string;
  kind: EvidenceKind;
  provenance: Provenance;
  claim: string;
  excerpt: string;
  excerpt_language: "de" | "en";
  brand: string;
  vehicle: string;
  market: MarketCode;
  topic: Topic;
  subtopic: string;
  source_name: string;
  source_title: string;
  source_url: string | null;
  source_family: UiSourceFamily;
  /** Human-readable locator, e.g. "chars 1112–1199" or "Feedback_Explorer!E412". */
  locator: string;
  quality: number | null;
  independence_group: string;
  duplicate_of: string | null;
  published_at: string | null;
  retrieved_at: string;
  numeric_value: number | null;
  numeric_unit: string | null;
  limitation: string | null;
  /** The original record exactly as stored, for the raw view. */
  raw: ProcessedEvidence | Signal | WebResearchSeedRecord | Record<string, unknown>;
}

export interface HypothesisLink {
  evidence_id: string;
  stance: Stance;
  note: string;
}

export interface Hypothesis {
  id: string;
  statement: string;
  topic: Topic;
  market: MarketCode;
  links: HypothesisLink[];
}

export type HypothesisStatus = "supported" | "contested" | "not_supported" | "insufficient";

export interface Finding {
  id: string;
  title: string;
  summary: string;
  topic: Topic;
  market: MarketCode;
  hypothesis_ids: string[];
  customer_need: string;
  requirement_ids: string[];
  updated_at: string;
}

export type BenchmarkPosition = "ahead" | "parity" | "behind" | "no_evidence";

export interface BenchmarkCell {
  position: BenchmarkPosition;
  summary: string;
  evidence_ids: string[];
}

export interface CompetitorBenchmark {
  vehicle: string;
  is_reference: boolean;
  cells: Record<string, BenchmarkCell>;
}

export const BENCHMARK_TOPICS = [
  { key: "charging", label: "Charging & trip planning" },
  { key: "controls", label: "Climate controls" },
  { key: "connected", label: "Connected services" },
  { key: "comfort", label: "Seating & comfort" },
  { key: "assistance", label: "Driver assistance" },
] as const;
export type BenchmarkTopic = (typeof BENCHMARK_TOPICS)[number]["key"];

/**
 * One successor requirement: the stored RequirementRevision plus the
 * authored SuccessorProposal (configs/successor_proposals_v1.json) that
 * explains it, its PM priority history and decisions.
 */
export interface RequirementBundle {
  /** Short, stable display ID (e.g. REQ-CTL-01); requirement.requirement_id is the contract ID. */
  display_id: string;
  domain: string;
  topic: string;
  /** Markets the authored proposal is scoped to. Others are deliberately not transferred. */
  scope_markets: MarketCode[];
  /** Revisions oldest → newest. */
  revisions: RequirementRevision[];
  proposal: SuccessorProposal;
  /** Saved PM priority assessments, oldest → newest (any revision). */
  assessments: PriorityAssessment[];
  decisions: Decision[];
  finding_ids: string[];
  benchmark_topic: BenchmarkTopic | null;
  /** What is known per out-of-scope market and what a transfer would need. */
  market_context: Partial<Record<MarketCode, string>>;
}

export interface Dataset {
  generated_at: string;
  vehicle: {
    family: string;
    generation: string;
    successor_label: string;
    horizon: string;
  };
  planning: {
    version: string;
    status: string;
    window: string;
    primary_market: MarketCode;
  };
  policy: PolicyVersion;
  profile: VehicleProfile;
  planning_context: PlanningContextSource[];
  evidence: EvidenceItem[];
  hypotheses: Hypothesis[];
  findings: Finding[];
  requirements: RequirementBundle[];
  benchmark: CompetitorBenchmark[];
  audit: AuditEvent[];
  research_runs: ResearchRun[];
  data_notes: string[];
  source_files: { path: string; records: number; status: "loaded" | "missing" | "invalid" }[];
}
