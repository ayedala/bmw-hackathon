/** Preview arithmetic only. Python decision/crps.py owns factor derivation and persisted scores. */
import type { CriterionInput, DimensionInterval } from "./contracts";

export const CRPS_WEIGHTS = {
  customer_impact: .25, evidence_strength: .20, frequency: .15,
  market_relevance: .15, competitive_gap: .10, future_relevance: .10, strategic_fit: .05,
} as const;
export type CrpsFactor = keyof typeof CRPS_WEIGHTS;
export const CRPS_FACTOR_LABEL: Record<CrpsFactor, string> = {
  customer_impact: "Customer Impact", evidence_strength: "Evidence Strength", frequency: "Frequency",
  market_relevance: "Market Relevance", competitive_gap: "Competitive Gap", future_relevance: "Future Relevance", strategic_fit: "Strategic Fit",
};
export interface FactorContribution {
  name: string; weight: number; lower_value: number; upper_value: number;
  lower_contribution: number; upper_contribution: number; known: boolean;
  basis: string | null; missing_reason: string | null;
}
export interface CrpsResult {
  policy_id: string; policy_revision: number; approved: boolean;
  crps_100_lower: number; crps_100_upper: number; lower_0_to_4: number; upper_0_to_4: number;
  band: "P1" | "P2" | "P3" | "P4"; band_label: string; band_basis: string;
  is_point: boolean; unknown_factors: string[]; factors: Record<string, FactorContribution>;
  dimension_intervals?: Record<string, DimensionInterval>;
}
export interface CanonicalCrps {
  result: CrpsResult;
  confidence: { value_0_to_4: number; value_0_to_100: number; components: Record<string, number>; basis: string };
  evidence_strength: {
    value: number; components: Record<string, number>; independent_groups: number; source_families: number;
    supporting_groups: number; contradicting_groups: number; duplicate_rows_excluded: number;
    rows_considered: number; newest_evidence_date: string | null; basis: string;
  };
  competitive_gap: Record<string, unknown>;
  factor_evidence_ids: Record<string, string[]>;
  calculated_at: string;
}
export interface RequirementQuality {
  requirement_id: string; passed: boolean;
  checks: { check_id: string; title: string; passed: boolean; severity: string; detail: string }[];
  blockers: { check_id: string; title: string; detail: string }[];
  warnings: { check_id: string; title: string; detail: string }[];
}

const rounded = (value: number, places: number) => Number(value.toFixed(places));
/** Never persists; no weight sliders, inferred inputs or missing-factor renormalisation. */
export function previewCrps(factors: Record<string, CriterionInput>) {
  const names = Object.keys(CRPS_WEIGHTS) as CrpsFactor[];
  if (Object.keys(factors).sort().join() !== [...names].sort().join()) throw new Error("CRPS requires exactly seven factors");
  let lower = 0, upper = 0;
  const contributions: Record<string, FactorContribution> = {};
  const unknown_factors: string[] = [];
  for (const name of names) {
    const input = factors[name]!;
    const exact = input.value != null;
    const interval = input.lower_value != null && input.upper_value != null;
    if (!exact && !interval && !input.missing_reason) throw new Error("Unknown factor needs a reason");
    if ((exact || interval) && !input.basis) throw new Error("Known factor needs a basis");
    if (exact && (input.lower_value != null || input.upper_value != null)) throw new Error("Exact and interval cannot coexist");
    if (!exact && ((input.lower_value == null) !== (input.upper_value == null))) throw new Error("Both bounds required");
    const lo = exact ? input.value! : interval ? input.lower_value! : 0;
    const hi = exact ? input.value! : interval ? input.upper_value! : 4;
    if (![lo, hi].every(Number.isFinite) || lo < 0 || hi > 4 || lo > hi) throw new Error("Invalid factor bounds");
    const weight = CRPS_WEIGHTS[name];
    if (!exact && !interval) unknown_factors.push(name);
    lower += weight * lo; upper += weight * hi;
    contributions[name] = { name, weight, lower_value: lo, upper_value: hi,
      lower_contribution: rounded(weight * lo, 6), upper_contribution: rounded(weight * hi, 6),
      known: exact || interval, basis: input.basis, missing_reason: input.missing_reason };
  }
  const crps_100_lower = rounded(lower * 25, 4), crps_100_upper = rounded(upper * 25, 4);
  return { lower_0_to_4: rounded(lower, 6), upper_0_to_4: rounded(upper, 6), crps_100_lower, crps_100_upper,
    is_point: !unknown_factors.length && Math.abs(crps_100_upper - crps_100_lower) < 1e-9,
    band: crps_100_lower >= 80 ? "P1" : crps_100_lower >= 65 ? "P2" : crps_100_lower >= 50 ? "P3" : "P4",
    factors: contributions, unknown_factors };
}

export function previewDecisionConfidence(strength: CanonicalCrps["evidence_strength"]) {
  const components = { evidence_strength: strength.value, consistency: strength.components.consistency ?? 0,
    source_diversity: strength.components.source_diversity ?? 0, recency: strength.components.recency ?? 0 };
  const value = components.evidence_strength * .45 + components.consistency * .25 + components.source_diversity * .20 + components.recency * .10;
  return { value_0_to_4: rounded(value, 4), value_0_to_100: rounded(value * 25, 2) };
}
