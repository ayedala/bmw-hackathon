/**
 * Shapes exchanged with the Python review bridge.
 *
 * These are transport types only. Every review rule - what may be edited, when
 * approval needs an uncertainty acknowledgement, whether a revision is stale -
 * lives in bmw_pm.review.ReviewService and is deliberately not restated here.
 */

/** Actions the bridge accepts. `state` and `audit` are reads. */
export const REVIEW_ACTIONS = ["state", "decide", "edit", "judge_link", "audit"] as const;
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
  requirement?: Record<string, unknown>;
  score?: Record<string, unknown> | null;
  decision?: Record<string, unknown> | null;
  judgments?: Record<string, Record<string, unknown>>;
  readiness?: Record<string, unknown> | null;
  readiness_note?: string | null;
}

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
