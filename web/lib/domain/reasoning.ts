/**
 * The real reasoning chain: EVIDENCE -> FINDING -> CUSTOMER NEED -> REQUIREMENT.
 *
 * These types mirror the artifacts written by
 * `src/bmw_pm/data_pipeline/web_research/build_synthesis.py` and validated by
 * its `validate_traceability.py`. They are loaded from
 * `src/bmw_pm/data_pipeline/web_research/data/processed/`:
 *
 *   external_evidence.jsonl    979 rows   canonical evidence
 *   findings.jsonl              20 rows   each cites evidence_ids
 *   customer_needs.jsonl        15 rows   each cites finding_ids
 *   requirements.jsonl          14 rows   each cites need_ids
 *   requirement_scores.jsonl    14 rows   one per requirement
 *
 * When those files are present they are authoritative. The fixture graph in
 * `lib/data/fixtures/graph.ts` is a fallback for demo checkouts without the
 * artifacts, and the loader reports which was used so the UI can say so.
 *
 * Nothing here repairs provenance. A reference that does not resolve is
 * recorded as a validation issue and surfaced, because silently dropping a
 * dangling link would make the chain look sounder than it is.
 */

import type { ProcessedEvidence } from "./contracts";

/** A finding as written to findings.jsonl. */
export interface ArtifactFinding {
  finding_id: string;
  schema_version: string;
  topic: string;
  finding_kind:
    | "bmw_strength"
    | "bmw_weakness"
    | "competitor_strength"
    | "customer_friction"
    | "market_trend";
  title: string;
  summary: string;
  evidence_ids: string[];
  source_count: number;
  independent_source_count: number;
  average_source_quality: number;
  confidence: string;
  stance_summary: {
    rows: number;
    by_source_family: Record<string, number>;
    numeric_rows: number;
  };
  brands_covered: string[];
  vehicles_covered: string[];
  markets_covered: string[];
  contradicts: string[];
  notes: string;
  created_at: string;
}

/** A customer need as written to customer_needs.jsonl. */
export interface ArtifactCustomerNeed {
  need_id: string;
  schema_version: string;
  topic: string;
  statement: string;
  rationale: string;
  finding_ids: string[];
  evidence_ids: string[];
  importance: string;
  confidence: string;
  customer_context: string;
  target_market: string;
  created_at: string;
}

/** A requirement as written to requirements.jsonl. */
export interface ArtifactRequirement {
  requirement_id: string;
  schema_version: string;
  topic: string;
  title: string;
  requirement: string;
  need_ids: string[];
  finding_ids: string[];
  evidence_ids: string[];
  customer_value: string;
  differentiation: string;
  confidence: string;
  independent_source_count: number;
  rough_effort: string;
  rough_cost: string;
  validation_method: string;
  assumptions: string[];
  missing_evidence: string[];
  status: string;
  created_at: string;
}

/** A score row as written to requirement_scores.jsonl (four-factor policy). */
export interface ArtifactRequirementScore {
  requirement_id: string;
  schema_version: string;
  policy_id: string;
  derived_from: string;
  approved: boolean;
  deviation: string;
  weights: Record<string, number>;
  components_0_to_4: Record<string, number>;
  reach_basis: Record<string, unknown>;
  weighted_score_0_to_4: number;
  created_at: string;
}

/** Why a reference could not be resolved. Never silently repaired. */
export interface TraceabilityIssue {
  severity: "blocker" | "warning";
  from_kind: "finding" | "need" | "requirement" | "score";
  from_id: string;
  field: string;
  missing_ids: string[];
  detail: string;
}

/** A finding with its evidence resolved and its stance split out. */
export interface ResolvedFinding {
  artifact: ArtifactFinding;
  /** Evidence rows that exist in the canonical store, in artifact order. */
  supporting: ProcessedEvidence[];
  /** Evidence from findings this one contradicts - shown, never hidden. */
  contradicting: ProcessedEvidence[];
  /** Evidence ids cited by the artifact that are not in the store. */
  unresolved_evidence_ids: string[];
  /** Independent groups among supporting rows, excluding duplicates. */
  independent_groups: string[];
  source_families: string[];
  /** Findings that disagree with this one, resolved to ids present in the set. */
  contradicts: string[];
}

export interface ResolvedNeed {
  artifact: ArtifactCustomerNeed;
  findings: ResolvedFinding[];
  unresolved_finding_ids: string[];
}

export interface ResolvedRequirement {
  artifact: ArtifactRequirement;
  needs: ResolvedNeed[];
  findings: ResolvedFinding[];
  /** Union of evidence reached through the needs, deduplicated. */
  evidence: ProcessedEvidence[];
  contradicting: ProcessedEvidence[];
  score: ArtifactRequirementScore | null;
  unresolved_need_ids: string[];
  independent_groups: string[];
  source_families: string[];
}

export interface ReasoningGraph {
  /** True when the real artifacts were loaded; false when using fixtures. */
  authoritative: boolean;
  findings: ResolvedFinding[];
  needs: ResolvedNeed[];
  requirements: ResolvedRequirement[];
  issues: TraceabilityIssue[];
  counts: {
    evidence: number;
    findings: number;
    needs: number;
    requirements: number;
    scores: number;
    orphan_findings: number;
    orphan_needs: number;
  };
}

const EMPTY_GRAPH: ReasoningGraph = {
  authoritative: false,
  findings: [],
  needs: [],
  requirements: [],
  issues: [],
  counts: {
    evidence: 0,
    findings: 0,
    needs: 0,
    requirements: 0,
    scores: 0,
    orphan_findings: 0,
    orphan_needs: 0,
  },
};

/** Independence group for a row, falling back to its URL then its id. */
function groupOf(row: ProcessedEvidence): string {
  return (
    row.independence_group ||
    row.source_url ||
    row.evidence_id ||
    "unknown"
  );
}

/** Rows that count as independent confirmation: duplicates are excluded. */
function independentRows(rows: ProcessedEvidence[]): ProcessedEvidence[] {
  return rows.filter((row) => !row.duplicate_of);
}

function uniqueBy<T, K>(items: T[], key: (item: T) => K): T[] {
  const seen = new Set<K>();
  const out: T[] = [];
  for (const item of items) {
    const value = key(item);
    if (seen.has(value)) continue;
    seen.add(value);
    out.push(item);
  }
  return out;
}

/**
 * Resolve the artifacts into a navigable graph and collect every dangling
 * reference as an issue.
 *
 * Resolution is strictly one-directional: a finding may only cite evidence, a
 * need may only cite findings, a requirement may only cite needs. Links are
 * never invented to fill a gap.
 */
export function buildReasoningGraph(input: {
  evidence: ProcessedEvidence[];
  findings: ArtifactFinding[];
  needs: ArtifactCustomerNeed[];
  requirements: ArtifactRequirement[];
  scores: ArtifactRequirementScore[];
}): ReasoningGraph {
  const { evidence, findings, needs, requirements, scores } = input;
  if (findings.length === 0 && needs.length === 0 && requirements.length === 0) {
    return { ...EMPTY_GRAPH, counts: { ...EMPTY_GRAPH.counts, evidence: evidence.length } };
  }

  const issues: TraceabilityIssue[] = [];
  const evidenceById = new Map(evidence.map((row) => [row.evidence_id, row]));

  // -- findings -> evidence ------------------------------------------------ //
  const resolvedFindings = new Map<string, ResolvedFinding>();
  for (const artifact of findings) {
    const supporting: ProcessedEvidence[] = [];
    const missing: string[] = [];
    for (const id of artifact.evidence_ids) {
      const row = evidenceById.get(id);
      if (row) supporting.push(row);
      else missing.push(id);
    }
    if (missing.length > 0) {
      issues.push({
        severity: "blocker",
        from_kind: "finding",
        from_id: artifact.finding_id,
        field: "evidence_ids",
        missing_ids: missing,
        detail: `${missing.length} cited evidence id(s) are not in the canonical store.`,
      });
    }
    const independent = independentRows(supporting);
    resolvedFindings.set(artifact.finding_id, {
      artifact,
      supporting,
      contradicting: [],
      unresolved_evidence_ids: missing,
      independent_groups: Array.from(new Set(independent.map(groupOf))).sort(),
      source_families: Array.from(
        new Set(independent.map((row) => row.source_family ?? "unknown")),
      ).sort(),
      contradicts: [],
    });
  }

  // Second pass: resolve contradiction links and pull across their evidence so
  // a reviewer sees what disagrees without navigating away.
  for (const resolved of resolvedFindings.values()) {
    const present: string[] = [];
    const absent: string[] = [];
    for (const id of resolved.artifact.contradicts) {
      if (resolvedFindings.has(id)) present.push(id);
      else absent.push(id);
    }
    resolved.contradicts = present;
    if (absent.length > 0) {
      issues.push({
        severity: "warning",
        from_kind: "finding",
        from_id: resolved.artifact.finding_id,
        field: "contradicts",
        missing_ids: absent,
        detail: "Contradiction points at a finding that is not in this set.",
      });
    }
    resolved.contradicting = uniqueBy(
      present.flatMap((id) => resolvedFindings.get(id)?.supporting ?? []),
      (row) => row.evidence_id,
    );
  }

  // -- needs -> findings --------------------------------------------------- //
  const resolvedNeeds = new Map<string, ResolvedNeed>();
  for (const artifact of needs) {
    const linked: ResolvedFinding[] = [];
    const missing: string[] = [];
    for (const id of artifact.finding_ids) {
      const finding = resolvedFindings.get(id);
      if (finding) linked.push(finding);
      else missing.push(id);
    }
    if (missing.length > 0) {
      issues.push({
        severity: "blocker",
        from_kind: "need",
        from_id: artifact.need_id,
        field: "finding_ids",
        missing_ids: missing,
        detail: `${missing.length} cited finding id(s) do not exist.`,
      });
    }
    resolvedNeeds.set(artifact.need_id, {
      artifact,
      findings: linked,
      unresolved_finding_ids: missing,
    });
  }

  // -- requirements -> needs ----------------------------------------------- //
  const scoreById = new Map(scores.map((row) => [row.requirement_id, row]));
  const resolvedRequirements: ResolvedRequirement[] = [];
  for (const artifact of requirements) {
    const linkedNeeds: ResolvedNeed[] = [];
    const missing: string[] = [];
    for (const id of artifact.need_ids) {
      const need = resolvedNeeds.get(id);
      if (need) linkedNeeds.push(need);
      else missing.push(id);
    }
    if (missing.length > 0) {
      issues.push({
        severity: "blocker",
        from_kind: "requirement",
        from_id: artifact.requirement_id,
        field: "need_ids",
        missing_ids: missing,
        detail: `${missing.length} cited need id(s) do not exist.`,
      });
    }
    const reachedFindings = uniqueBy(
      linkedNeeds.flatMap((need) => need.findings),
      (finding) => finding.artifact.finding_id,
    );
    const reachedEvidence = uniqueBy(
      reachedFindings.flatMap((finding) => finding.supporting),
      (row) => row.evidence_id,
    );
    const contradicting = uniqueBy(
      reachedFindings.flatMap((finding) => finding.contradicting),
      (row) => row.evidence_id,
    );
    const independent = independentRows(reachedEvidence);
    const score = scoreById.get(artifact.requirement_id) ?? null;
    if (!score) {
      issues.push({
        severity: "warning",
        from_kind: "requirement",
        from_id: artifact.requirement_id,
        field: "score",
        missing_ids: [],
        detail: "No score row exists for this requirement.",
      });
    }
    resolvedRequirements.push({
      artifact,
      needs: linkedNeeds,
      findings: reachedFindings,
      evidence: reachedEvidence,
      contradicting,
      score,
      unresolved_need_ids: missing,
      independent_groups: Array.from(new Set(independent.map(groupOf))).sort(),
      source_families: Array.from(
        new Set(independent.map((row) => row.source_family ?? "unknown")),
      ).sort(),
    });
  }

  // -- scores pointing nowhere --------------------------------------------- //
  const requirementIds = new Set(requirements.map((row) => row.requirement_id));
  for (const score of scores) {
    if (!requirementIds.has(score.requirement_id)) {
      issues.push({
        severity: "warning",
        from_kind: "score",
        from_id: score.requirement_id,
        field: "requirement_id",
        missing_ids: [score.requirement_id],
        detail: "Score refers to a requirement that is not present.",
      });
    }
  }

  // -- orphans ------------------------------------------------------------- //
  const usedFindings = new Set(needs.flatMap((need) => need.finding_ids));
  const orphanFindings = findings.filter((row) => !usedFindings.has(row.finding_id));
  for (const orphan of orphanFindings) {
    issues.push({
      severity: "warning",
      from_kind: "finding",
      from_id: orphan.finding_id,
      field: "consumed_by_need",
      missing_ids: [],
      detail: "Finding is not cited by any customer need.",
    });
  }
  const usedNeeds = new Set(requirements.flatMap((row) => row.need_ids));
  const orphanNeeds = needs.filter((row) => !usedNeeds.has(row.need_id));
  for (const orphan of orphanNeeds) {
    issues.push({
      severity: "warning",
      from_kind: "need",
      from_id: orphan.need_id,
      field: "consumed_by_requirement",
      missing_ids: [],
      detail: "Customer need is not cited by any requirement.",
    });
  }

  return {
    authoritative: true,
    findings: Array.from(resolvedFindings.values()),
    needs: Array.from(resolvedNeeds.values()),
    requirements: resolvedRequirements,
    issues,
    counts: {
      evidence: evidence.length,
      findings: findings.length,
      needs: needs.length,
      requirements: requirements.length,
      scores: scores.length,
      orphan_findings: orphanFindings.length,
      orphan_needs: orphanNeeds.length,
    },
  };
}

export const emptyReasoningGraph = (): ReasoningGraph => ({ ...EMPTY_GRAPH });

/** Blockers only - a dangling id that makes the chain unsound. */
export function blockers(graph: ReasoningGraph): TraceabilityIssue[] {
  return graph.issues.filter((issue) => issue.severity === "blocker");
}

/** Walk a requirement backwards to its evidence, for the trace view. */
export function traceBackwards(requirement: ResolvedRequirement): {
  requirement: ArtifactRequirement;
  needs: { need: ArtifactCustomerNeed; findings: { finding: ArtifactFinding; evidence: ProcessedEvidence[] }[] }[];
} {
  return {
    requirement: requirement.artifact,
    needs: requirement.needs.map((need) => ({
      need: need.artifact,
      findings: need.findings.map((finding) => ({
        finding: finding.artifact,
        evidence: finding.supporting,
      })),
    })),
  };
}
