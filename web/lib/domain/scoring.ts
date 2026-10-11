/**
 * Deterministic value scoring — a line-for-line TypeScript port of
 * src/bmw_pm/decision/scoring.py (reach_input, score_requirement,
 * rank_scores, assess_ranking).
 *
 * This legacy internal-feedback score and the four-factor priority helpers
 * below are retained for explicit demo mode only. Canonical requirements and
 * challenges use the Python seven-factor CRPS payload; web/lib/domain/crps.ts
 * is an arithmetic-only parity helper, never a competing score authority.
 */
import type {
  CriterionInput,
  DimensionInterval,
  PolicyVersion,
  PriorityFactors,
  PriorityPolicy,
  RequirementRevision,
  ScoreSnapshot,
} from "./contracts";

const round = (value: number, digits: number) => {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
};

export function knownInput(value: number, basis: string): CriterionInput {
  return { value, lower_value: null, upper_value: null, basis, missing_reason: null };
}

export function unknownInput(missing_reason: string): CriterionInput {
  return { value: null, lower_value: null, upper_value: null, basis: null, missing_reason };
}

export function intervalInput(lower: number, upper: number, basis: string): CriterionInput {
  return { value: null, lower_value: lower, upper_value: upper, basis, missing_reason: null };
}

export function isUnknown(input: CriterionInput | undefined): boolean {
  if (!input) return true;
  return input.value === null && input.lower_value === null;
}

/** Port of scoring.reach_input. */
export function reachInput(args: {
  support_count: number;
  eligible_count: number;
  processed_count: number;
  saturation_share: number;
}): CriterionInput {
  const { support_count, eligible_count, processed_count, saturation_share } = args;
  if (Math.min(support_count, eligible_count, processed_count) < 0) {
    throw new Error("reach counts cannot be negative");
  }
  if (support_count > processed_count || processed_count > eligible_count) {
    throw new Error("reach counts must satisfy support <= processed <= eligible");
  }
  if (eligible_count === 0) {
    return unknownInput("No eligible feedback records exist in the selected scope.");
  }
  const unprocessed = eligible_count - processed_count;
  const lowerShare = support_count / eligible_count;
  const upperShare = (support_count + unprocessed) / eligible_count;
  const lower = round(4 * Math.min(lowerShare / saturation_share, 1), 12);
  const upper = round(4 * Math.min(upperShare / saturation_share, 1), 12);
  const basis =
    `${support_count} unique supporting feedback IDs / ${eligible_count} eligible IDs; ` +
    `${processed_count} IDs processed; saturation_share=${saturation_share}. ` +
    "This is collected-corpus recurrence, not customer prevalence.";
  if (Math.abs(lower - upper) < 1e-12) return knownInput(lower, basis);
  return intervalInput(lower, upper, basis);
}

function bounds(input: CriterionInput): [number, number] {
  if (input.value !== null) return [input.value, input.value];
  if (input.lower_value !== null && input.upper_value !== null) {
    return [input.lower_value, input.upper_value];
  }
  return [0, 4];
}

/** Port of scoring.score_requirement. */
export function scoreRequirement(args: {
  requirement: RequirementRevision;
  policy: PolicyVersion;
  criterion_inputs: Record<string, CriterionInput>;
  profile_id: string;
  profile_revision: number;
  corpus_manifest_hash: string;
  run_id: string;
  extra_assumptions?: string[];
  evidence_review_status?: ScoreSnapshot["evidence_review_status"];
}): ScoreSnapshot {
  const { requirement, policy, criterion_inputs } = args;
  const expected = Object.keys(policy.criteria).sort();
  const actual = Object.keys(criterion_inputs).sort();
  if (expected.join("|") !== actual.join("|")) {
    throw new Error("criterion inputs must exactly match policy criteria");
  }
  const contributions: Record<string, [number, number]> = {};
  let lowerTotal = 0;
  let upperTotal = 0;
  for (const [name, definition] of Object.entries(policy.criteria)) {
    const input = criterion_inputs[name];
    if (!input) continue;
    const [lowerValue, upperValue] = bounds(input);
    const lowerContribution = (100 * definition.weight * lowerValue) / 4;
    const upperContribution = (100 * definition.weight * upperValue) / 4;
    contributions[name] = [round(lowerContribution, 8), round(upperContribution, 8)];
    lowerTotal += lowerContribution;
    upperTotal += upperContribution;
  }
  const dimension_intervals: Record<string, DimensionInterval> = {};
  for (const dimension of ["customer", "business"] as const) {
    const names = Object.entries(policy.criteria)
      .filter(([, definition]) => definition.dimension === dimension)
      .map(([name]) => name);
    const weight = names.reduce((sum, name) => sum + (policy.criteria[name]?.weight ?? 0), 0);
    dimension_intervals[dimension] = {
      lower_bound: round(names.reduce((s, n) => s + (contributions[n]?.[0] ?? 0), 0) / weight, 8),
      upper_bound: round(names.reduce((s, n) => s + (contributions[n]?.[1] ?? 0), 0) / weight, 8),
      criteria: names,
      missing_criteria: names.filter((n) => isUnknown(criterion_inputs[n])),
      interpretation:
        "Policy-dependent 0–100 scenario bounds within this dimension; not a probability or measured product outcome.",
    };
  }
  return {
    schema_version: "1",
    score_snapshot_id: `score-${hashString(
      JSON.stringify([requirement.requirement_id, requirement.revision, policy.policy_id, policy.revision, args.run_id, criterion_inputs]),
    )}`,
    requirement_id: requirement.requirement_id,
    requirement_revision: requirement.revision,
    policy_id: policy.policy_id,
    policy_revision: policy.revision,
    profile_id: args.profile_id,
    profile_revision: args.profile_revision,
    corpus_manifest_hash: args.corpus_manifest_hash,
    criterion_inputs,
    contributions,
    dimension_intervals,
    lower_bound: round(lowerTotal, 8),
    upper_bound: round(upperTotal, 8),
    scope: requirement.scope,
    coverage: {
      eligible_feedback_records: requirement.denominator_feedback_records,
      processed_feedback_records: requirement.processed_feedback_records,
      supporting_unique_feedback_records: requirement.support_count,
      praise_or_preservation_unique_feedback_records: requirement.counter_count,
      unit: "unique feedback ID within one supplied source file",
    },
    feasibility_status: requirement.feasibility,
    feasibility_basis:
      requirement.feasibility === "unknown"
        ? "No reviewed engineering constraints, effort, or cost were supplied. Customer comments and competitor features cannot certify feasibility."
        : "Reviewed feasibility evidence must be inspected on the requirement revision.",
    evidence_review_status: args.evidence_review_status ?? "unreviewed",
    assumptions: [
      policy.elicitation_record,
      "Additive criterion independence has not been validated.",
      ...(args.extra_assumptions ?? []),
    ],
    run_id: args.run_id,
  };
}

/** Port of scoring.rank_scores: descending lower bound, stable ID tie-break. */
export function rankScores<T extends { score: ScoreSnapshot; id: string }>(items: T[]): T[] {
  return [...items].sort((a, b) => b.score.lower_bound - a.score.lower_bound || a.id.localeCompare(b.id));
}

/** Port of scoring.assess_ranking: is the order between two items resolved by their intervals? */
export function comparisonResolved(a: ScoreSnapshot, b: ScoreSnapshot): boolean {
  return a.lower_bound > b.upper_bound || b.lower_bound > a.upper_bound;
}

/** Small deterministic non-cryptographic hash for IDs (FNV-1a, 32-bit, hex). */
export function hashString(input: string): string {
  let hash = 0x811c9dc5;
  for (let i = 0; i < input.length; i += 1) {
    hash ^= input.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(16).padStart(8, "0");
}

/* ------------------------------------------------------------------ */
/* Port of bmw_pm.decision.planning.priority_score                     */
/* ------------------------------------------------------------------ */


export const DEFAULT_PRIORITY_POLICY: PriorityPolicy = { impact: 0.35, evidence: 0.25, relevance: 0.25, uncertainty: 0.15 };

export const PRIORITY_FORMULA = "25 × [impact·w + evidence·w + market fit·w + (4 − uncertainty)·w]";

/** 0–100 weighted judgement; uncertainty is reversed, never confidence. */
export function priorityScore(f: PriorityFactors, p: PriorityPolicy): number {
  return round(25 * (f.impact * p.impact + f.evidence * p.evidence + f.relevance * p.relevance + (4 - f.uncertainty) * p.uncertainty), 4);
}

/** Points each factor contributes under the policy (sums to the score). */
export function priorityContributions(f: PriorityFactors, p: PriorityPolicy): Record<keyof PriorityFactors, number> {
  return {
    impact: 25 * f.impact * p.impact,
    evidence: 25 * f.evidence * p.evidence,
    relevance: 25 * f.relevance * p.relevance,
    uncertainty: 25 * (4 - f.uncertainty) * p.uncertainty,
  };
}

/** Normalise raw slider weights (0–100) into a policy that sums to one. */
export function normalisePolicy(raw: PriorityPolicy): PriorityPolicy {
  const total = raw.impact + raw.evidence + raw.relevance + raw.uncertainty;
  if (total <= 0) return DEFAULT_PRIORITY_POLICY;
  return { impact: raw.impact / total, evidence: raw.evidence / total, relevance: raw.relevance / total, uncertainty: raw.uncertainty / total };
}
