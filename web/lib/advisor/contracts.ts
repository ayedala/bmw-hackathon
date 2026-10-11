// Wire types mirror bmw_pm.advisor.contracts / bridge; Python validates every input.
export type Journey = "idea" | "improve" | "compare";
export type Vehicle = "F70" | "G60" | "G70";
export interface AdvisorRequest {
  journey: Journey; model_code: Vehicle; market: string; powertrain: "ALL" | "ICE" | "PHEV" | "BEV";
  model_year: number; question: string; ideas: string[]; objective: string;
  planning_years: number; currency: string; budget: number | null;
}
export interface EvidenceItem {
  evidence_id: string; channel: string; title: string; text: string; selection_reason: string;
  scope: Record<string, unknown>; locator: Record<string, unknown>; limitations: string[];
}
export interface Claim {
  text: string; basis: "evidence" | "inference" | "assumption" | "unknown";
  evidence_ids: string[]; explanation: string;
}
export interface Option {
  option_id: string; title: string; proposal: string; customer_case: Claim[]; competitors: Claim[];
  feasibility: Claim; cost_outlook: Claim; revenue_outlook: Claim;
  delivery_steps: string[]; risks: string[]; validation_needed: string[];
}
export interface AdvisorResult {
  run_id: string; created_at: string; mode: "live_ai"; model_id: string; prompt_version: string;
  packet: { request: AdvisorRequest; feedback_records: number; evidence: EvidenceItem[]; fingerprint: string; limitations: string[];
    topics: {domain: string; outcome: string; eligible_records: number; supporting_records: number; praise_records: number; context_records: number}[] };
  plan: { focus_domains: string[]; search_terms: string[]; research_questions: string[]; rationale: string };
  research: {text: string; sources: EvidenceItem[]; search_actions: string[]; response_id: string; model_id: string};
  report: {headline: string; summary: string; options: Option[]; preferred_option_id: string | null;
    recommendation: Claim; comparison: Claim[]; follow_up_questions: string[]};
  steps: string[]; usage: Record<string, unknown>[];
}
export interface SourceCatalog {
  database_backend: "sqlite" | "postgres";
  database_available: boolean; connection_configured: boolean;
  scopes: {model_code: string; market: string; powertrain: string; feedback_records: number}[];
  youtube_findings: number; youtube_videos: number; saved_youtube_runs: number; video_memories: number;
}
export interface SyncResult {runs: number; inserted: number; accepted: number; rejected: number; failed_runs: number; memories_inserted: number}
export interface EvaluationSignal {need_domain: string; atomic_claim: string; customer_outcome: string; polarity: "complaint" | "praise" | "aspiration" | "observation" | "mixed"; evidence_text: string; use_context?: string | null; uncertainties?: string[]}
export interface EvaluationLabel {reviewer_id: string | null; reviewed_at?: string | null; review_status: "unlabelled" | "labelled"; signals: EvaluationSignal[]; abstention_reason: string | null; difficulty: string | null; adjudication?: {reviewer_id: string; reviewed_at?: string | null; reason: string; signals: EvaluationSignal[]; abstention_reason: string | null} | null}
export interface EvaluationSnapshot {
  available: boolean; message?: string; evaluation_id?: string; corpus_hash?: string; total?: number;
  counts?: {total: number; unlabelled: number; provisional: number; gold_ready: number; second_reviewed: number};
  items?: {record_id: string; split: string; model: string; double_label: boolean; status: string}[];
  case?: {record_id: string; text: string; model: string; country: string | null; powertrain: string | null;
    source_label: string | null; split: string; double_label: boolean; content_hash: string;
    review?: EvaluationLabel | null; primary?: EvaluationLabel; secondary?: EvaluationLabel | null};
  role?: "primary" | "secondary" | "adjudicator"; file_version?: string;
  baseline?: Record<string, {records: number; statuses: Record<string, number>; gold_ready: number; scored_records: number;
    metrics: {records: number; precision: number | null; recall: number | null; f1: number | null; definition: string} | null}>;
  limitations?: string[];
}
export type StudioEvent =
  | {type: "progress"; message: string}
  | {type: "error"; message: string}
  | {type: "result"; result: AdvisorResult}
  | {type: "catalog"; catalog: SourceCatalog}
  | {type: "sync"; sync: SyncResult; catalog: SourceCatalog}
  | {type: "scenarios"; rows: Record<string, string | number>[]}
  | {type: "memory"; memory: {memory_id: string; inserted: boolean; video_id: string; characters: number; transcript_sha256: string}; catalog: SourceCatalog}
  | {type: "evaluation"; evaluation: EvaluationSnapshot};
export type Operation = "catalog" | "analyze" | "sync" | "scenarios" | "memory" | "evaluation";
export const VEHICLES = {F70: "BMW 1 Series", G60: "BMW 5 Series", G70: "BMW 7 Series"} as const;
export const MARKETS = {US: "United States", GB: "United Kingdom", DE: "Germany", CN: "China", JP: "Japan", KR: "South Korea"} as const;
