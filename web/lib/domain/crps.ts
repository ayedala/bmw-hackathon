/** Deterministic CRPS v2. Missing ratings retain their full weight as a range. */
export const CRPS_POLICY_VERSION = "crps-framework-v1";

export const CRPS_WEIGHTS = {
  customer_impact: 0.25,
  evidence_strength: 0.20,
  frequency: 0.15,
  market_relevance: 0.15,
  competitive_gap: 0.10,
  future_relevance: 0.10,
  strategic_fit: 0.05,
} as const;

export const EVIDENCE_WEIGHTS = {
  source_quality: 0.30,
  source_diversity: 0.25,
  consistency: 0.20,
  volume: 0.15,
  recency: 0.10,
} as const;

export type CrpsDimension = Exclude<keyof typeof CRPS_WEIGHTS, "evidence_strength">;
export type EvidenceDimension = keyof typeof EVIDENCE_WEIGHTS;
export type RatingBasis = "missing" | "source_review" | "reviewer_judgment";

export interface CrpsRating {
  value: number | null;
  basis: RatingBasis;
  explanation: string;
  evidence_ids: string[];
}

export interface CrpsInputs extends Record<CrpsDimension, CrpsRating> {
  evidence: Record<EvidenceDimension, CrpsRating>;
  feasibility: "unknown" | "very_high" | "high" | "medium" | "low" | "very_low";
  feasibility_explanation: string;
}

export interface ScoreInterval {
  lower: number;
  upper: number;
  value: number | null;
}

export interface CrpsResult {
  policy_version: typeof CRPS_POLICY_VERSION;
  evidence_strength: ScoreInterval;
  customer_priority: ScoreInterval;
  priority_band: "P1 Critical" | "P2 High" | "P3 Medium" | "P4 Low" | "P5 Watch" | null;
  contributions: Record<keyof typeof CRPS_WEIGHTS, ScoreInterval>;
  missing_inputs: string[];
  feasibility: CrpsInputs["feasibility"];
}

export interface CrpsAssessment {
  assessment_id: string;
  requirement_id: string;
  requirement_revision: number;
  sequence: number;
  policy_version: typeof CRPS_POLICY_VERSION;
  inputs: CrpsInputs;
  result: CrpsResult;
  actor_id: string;
  rationale: string;
  recorded_at: string;
}

const missingRating = (): CrpsRating => ({ value: null, basis: "missing", explanation: "", evidence_ids: [] });
export function emptyCrpsInputs(): CrpsInputs {
  return {
    customer_impact: missingRating(),
    evidence: {
      source_quality: missingRating(), source_diversity: missingRating(),
      consistency: missingRating(), volume: missingRating(), recency: missingRating(),
    },
    frequency: missingRating(), market_relevance: missingRating(),
    competitive_gap: missingRating(), future_relevance: missingRating(),
    strategic_fit: missingRating(), feasibility: "unknown", feasibility_explanation: "",
  };
}

const round4 = (value: number) => Math.round((value + Number.EPSILON) * 10000) / 10000;

function interval(values: Record<string, CrpsRating>, weights: Record<string, number>): ScoreInterval {
  let known = 0;
  let unknownWeight = 0;
  for (const [key, weight] of Object.entries(weights)) {
    const value = values[key]?.value;
    if (value === undefined) throw new Error(`Missing rating: ${key}`);
    if (value === null) unknownWeight += weight;
    else known += value * weight;
  }
  const lower = round4(known);
  return { lower, upper: round4(known + 100 * unknownWeight), value: unknownWeight ? null : lower };
}

export function validateCrpsInputs(inputs: CrpsInputs): void {
  const dimensions = Object.keys(CRPS_WEIGHTS).filter((key) => key !== "evidence_strength") as CrpsDimension[];
  const ratings = [...dimensions.map((key) => inputs[key]), ...Object.keys(EVIDENCE_WEIGHTS).map((key) => inputs.evidence[key as EvidenceDimension])];
  for (const item of ratings) {
    if (item.value === null) {
      if (item.basis !== "missing" || item.explanation || item.evidence_ids.length) throw new Error("Unknown ratings cannot have a basis or references.");
    } else if (!Number.isFinite(item.value) || item.value < 0 || item.value > 100 || item.basis === "missing" || !item.explanation.trim() ||
      (item.basis === "source_review" && item.evidence_ids.length === 0)) {
      throw new Error("Every rating needs a 0-100 value, basis and explanation; source-reviewed ratings also need source IDs.");
    }
  }
  if (inputs.feasibility !== "unknown" && !inputs.feasibility_explanation.trim()) throw new Error("Feasibility needs an explanation.");
  if (inputs.frequency.value !== null && inputs.frequency.basis !== "source_review")
    throw new Error("Frequency requires a source-reviewed eligible population, not reviewer judgment.");
}

export function evaluateCrps(inputs: CrpsInputs): CrpsResult {
  validateCrpsInputs(inputs);
  const evidence = interval(inputs.evidence, EVIDENCE_WEIGHTS);
  const contributions = {} as CrpsResult["contributions"];
  for (const [name, weight] of Object.entries(CRPS_WEIGHTS) as [keyof typeof CRPS_WEIGHTS, number][]) {
    const score = name === "evidence_strength" ? evidence : interval({ [name]: inputs[name as CrpsDimension] }, { [name]: 1 });
    contributions[name] = { lower: round4(score.lower * weight), upper: round4(score.upper * weight),
      value: score.value === null ? null : round4(score.value * weight) };
  }
  const parts = Object.values(contributions);
  const lower = round4(parts.reduce((sum, part) => sum + part.lower, 0));
  const upper = round4(parts.reduce((sum, part) => sum + part.upper, 0));
  const complete = parts.every((part) => part.value !== null);
  const band = !complete ? null : lower >= 80 ? "P1 Critical" : lower >= 65 ? "P2 High" : lower >= 50 ? "P3 Medium" : lower >= 35 ? "P4 Low" : "P5 Watch";
  return {
    policy_version: CRPS_POLICY_VERSION,
    evidence_strength: evidence,
    customer_priority: { lower, upper, value: complete ? lower : null },
    priority_band: band,
    contributions,
    missing_inputs: [
      ...(Object.keys(CRPS_WEIGHTS).filter((key) => key !== "evidence_strength" && inputs[key as CrpsDimension].value === null)),
      ...Object.keys(EVIDENCE_WEIGHTS).filter((key) => inputs.evidence[key as EvidenceDimension].value === null).map((key) => `evidence.${key}`),
    ],
    feasibility: inputs.feasibility,
  };
}
