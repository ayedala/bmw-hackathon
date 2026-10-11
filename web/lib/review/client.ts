"use client";

import {
  isReviewError,
  type RequirementState,
  type ReviewAction,
  type ReviewError,
  type ReviewResult,
} from "./contracts";

/**
 * Client for the review API.
 *
 * The browser is not the authority for PM actions. This module's job is to ask
 * the backend and report exactly what came back, including why an action could
 * not be recorded. It never fabricates a success.
 */

async function call(action: ReviewAction, payload: unknown, method: "GET" | "POST"): Promise<ReviewResult> {
  try {
    const response = await fetch(
      `/api/review?action=${action}`,
      method === "GET"
        ? { method, cache: "no-store" }
        : {
            method,
            cache: "no-store",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload ?? {}),
          },
    );
    const body: unknown = await response.json().catch(() => null);
    if (body && typeof body === "object" && "type" in body) return body as ReviewResult;
    return {
      type: "error",
      code: response.status === 503 ? "backend_unavailable" : "internal",
      message: `The review service returned HTTP ${response.status}.`,
    };
  } catch {
    // A network failure is not a reason to treat local state as authoritative.
    return {
      type: "error",
      code: "backend_unavailable",
      message: "The review service could not be reached.",
    };
  }
}

export function fetchState(requirementIds: string[] = []): Promise<ReviewResult> {
  return call("state", { requirement_ids: requirementIds }, "POST");
}

export function fetchAudit(): Promise<ReviewResult> {
  return call("audit", {}, "POST");
}

export interface DecidePayload {
  requirement_id: string;
  expected_revision: number;
  action: "approve" | "reject" | "defer" | "challenge";
  rationale: string;
  actor_id: string;
  request_id: string;
  uncertainty_acknowledged?: boolean;
}

export function postDecision(payload: DecidePayload): Promise<ReviewResult> {
  return call("decide", payload, "POST");
}

export interface EditPayload {
  requirement_id: string;
  expected_revision: number;
  changes: Record<string, unknown>;
  rationale: string;
  actor_id: string;
  request_id: string;
}

export function postEdit(payload: EditPayload): Promise<ReviewResult> {
  return call("edit", payload, "POST");
}

export interface JudgePayload {
  requirement_id: string;
  expected_revision: number;
  signal_id: string;
  verdict: "supports" | "does_not_support" | "context_only";
  rationale: string;
  actor_id: string;
  request_id: string;
}

export function postJudgment(payload: JudgePayload): Promise<ReviewResult> {
  return call("judge_link", payload, "POST");
}

/**
 * Which requirements the backend can actually record decisions for.
 *
 * The web app's requirement cards and the review database are populated by
 * different pipelines, so a card may have no backend revision. Callers use this
 * to say so plainly rather than recording a decision that looks authoritative
 * and is not.
 */
export interface BackendAvailability {
  reachable: boolean;
  reason: string | null;
  statesById: Map<string, RequirementState>;
}

export async function probeBackend(requirementIds: string[] = []): Promise<BackendAvailability> {
  const result = await fetchState(requirementIds);
  if (isReviewError(result)) {
    return { reachable: false, reason: result.message, statesById: new Map() };
  }
  if (result.type !== "state") {
    return {
      reachable: false,
      reason: `The review service answered a state request with ${result.type}.`,
      statesById: new Map(),
    };
  }
  const statesById = new Map<string, RequirementState>();
  for (const state of result.requirements) {
    if (state.present) statesById.set(state.requirement_id, state);
  }
  return { reachable: true, reason: null, statesById };
}

export type { ReviewError, ReviewResult, RequirementState };
export { isReviewError };
