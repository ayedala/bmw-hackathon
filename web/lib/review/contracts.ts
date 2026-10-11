/**
 * Shapes exchanged with the Python review bridge.
 *
 * These are transport types only. Every review rule - what may be edited, when
 * approval needs an uncertainty acknowledgement, whether a revision is stale -
 * lives in bmw_pm.review.ReviewService and is deliberately not restated here.
 */

/** Actions the bridge accepts. `state` and `audit` are reads. */
import type { RequirementRevision, Decision } from "../domain/contracts";
import type { CanonicalCrps, RequirementQuality } from "../domain/crps";

export const REVIEW_ACTIONS = ["canonical", "import_canonical", "state", "decide", "edit", "judge_link", "challenge", "reassess", "audit"] as const;
export type ReviewAction = (typeof REVIEW_ACTIONS)[number];

/**
 * Why a review action failed. The frontend branches on these: none of them
 * permits falling back to local state as the authority.
 */
export type ReviewErrorCode =
  | "backend_unavailable"
  | "requirement_not_found"
  | "stale_revision"
  | "request_conflict"
  | "invalid_request"
  | "internal";

export interface ReviewError {
  type: "error";
  code: ReviewErrorCode;
  message: string;
}

/** Authoritative backend state for one requirement. */
export interface RequirementState {
  requirement_id: string;
  present: boolean;
  detail?: string;
  revision?: number;
  lifecycle_status?: string;
  feasibility?: string;
  requirement?: RequirementRevision;
  revisions?: RequirementRevision[];
  decisions?: Decision[];
  crps?: CanonicalCrps | null;
  quality?: RequirementQuality | null;
  challenges?: CanonicalChallenge[];
  score?: Record<string, unknown> | null;
  decision?: Record<string, unknown> | null;
  judgments?: Record<string, Record<string, unknown>>;
  readiness?: Record<string, unknown> | null;
  readiness_note?: string | null;
}

export interface RetrievedItem {
  item_id: string; kind: string; role: string; relevance: number;
  relevance_basis: string; applicability: string; payload: Record<string, unknown>;
}
export interface ChallengeResolution {
  resolution_id: string; challenge_id: string; requirement_id: string; requirement_revision: number;
  accepted: boolean; actor_id: string; rationale: string; request_id: string; recorded_at: string;
  score_snapshot_id: string | null;
}
export interface CanonicalChallenge {
  challenge_id: string; requirement_id: string; requirement_revision: number;
  hypothesis: string; rationale: string; actor_id: string; request_id: string; created_at: string;
  before: CanonicalCrps; after: CanonicalCrps;
  factor_changes: { factor: string; before: unknown; after: unknown; evidence_ids: string[]; reason: string }[];
  retrieval: { supporting: RetrievedItem[]; opposing: RetrievedItem[]; context: RetrievedItem[];
    excluded_evidence_ids: string[]; searched_counts: Record<string, number>; method: string };
  gaps: string[]; explanation: string[]; evidence_ids: string[];
  resolution?: ChallengeResolution | null;
}
export interface CanonicalEvent {
  type: "canonical";
  requirements: { requirement: RequirementRevision; crps: CanonicalCrps; quality: RequirementQuality;
    lineage: Record<string, unknown> }[];
}
export interface ImportEvent { type: "import_canonical"; [key: string]: unknown }
export interface ChallengeEvent { type: "challenge"; challenge: CanonicalChallenge; state: RequirementState }
export interface ReassessmentEvent { type: "reassessment" | "reassess"; resolution: ChallengeResolution; state: RequirementState }

export interface StateEvent {
  type: "state";
  requirements: RequirementState[];
}

export interface DecisionEvent {
  type: "decision";
  decision: Record<string, unknown>;
  state: RequirementState;
}

export interface EditEvent {
  type: "edit";
  decision: Record<string, unknown>;
  revision: Record<string, unknown>;
  state: RequirementState;
}

export interface JudgmentEvent {
  type: "judgment";
  judgment: Record<string, unknown>;
  state: RequirementState;
}

export interface AuditEvent {
  type: "audit";
  valid: boolean;
  checkpoint: string;
  events: Array<Record<string, unknown>>;
}

export type ReviewResult =
  | StateEvent
  | DecisionEvent
  | EditEvent
  | JudgmentEvent
  | AuditEvent
  | CanonicalEvent
  | ImportEvent
  | ChallengeEvent
  | ReassessmentEvent
  | ReviewError;

/** HTTP status for each failure, so callers do not have to infer one. */
export const STATUS_FOR_CODE: Record<ReviewErrorCode, number> = {
  invalid_request: 400,
  requirement_not_found: 404,
  stale_revision: 409,
  request_conflict: 409,
  internal: 500,
  backend_unavailable: 503,
};

export function isReviewError(result: ReviewResult): result is ReviewError {
  return result.type === "error";
}
