/**
 * Derived labels. Every rule is written here once so that the same concept
 * always looks and behaves the same across screens, and so that each label
 * can explain itself in a tooltip.
 */
import type { Decision, PriorityAssessment, PriorityFactors, RequirementRevision, Stance } from "./contracts";
import type {
  EvidenceItem,
  Finding,
  Hypothesis,
  HypothesisStatus,
  MarketCode,
  RequirementBundle,
} from "./model";

/* ---------------------------------------------------------------- */
/* Priority (CRPS = bmw_pm.decision.planning.priority_score)          */
/* ---------------------------------------------------------------- */

export type Priority = "P1" | "P2" | "P3" | "P4" | "Watch";
export const PRIORITIES: Priority[] = ["P1", "P2", "P3", "P4", "Watch"];

export const PRIORITY_RULE =
  "CRPS = 25 × [impact·w + evidence·w + market fit·w + (4 − uncertainty)·w]. P1 ≥70, P2 ≥60, P3 ≥50, P4 below. Watch: uncertainty rated 4, so the order is not decision-grade.";

export function priorityOf(score: number | null, factors: PriorityFactors | null): Priority {
  if (score === null || !factors) return "Watch";
  if (factors.uncertainty >= 4) return "Watch";
  if (score >= 70) return "P1";
  if (score >= 60) return "P2";
  if (score >= 50) return "P3";
  return "P4";
}

export const priorityRank = (p: Priority) => PRIORITIES.indexOf(p);

export function formatScore(score: number | null): string {
  return score === null ? "—" : score.toFixed(1);
}

export const FACTOR_LABEL: Record<keyof PriorityFactors, string> = {
  impact: "Customer impact",
  evidence: "Evidence",
  relevance: "Market fit",
  uncertainty: "Uncertainty",
};

export const FACTOR_HINT: Record<keyof PriorityFactors, string> = {
  impact: "0 = no demonstrated improvement · 4 = repeatedly blocked core use case",
  evidence: "0 = no traceable evidence · 4 = independent, reviewed, matched evidence",
  relevance: "0 = outside the planning scope · 4 = central to the market and 2029–2031 scenario",
  uncertainty: "0 = well understood · 4 = conclusion could easily reverse. Counts against priority.",
};

/* ---------------------------------------------------------------- */
/* Evidence balance                                                  */
/* ---------------------------------------------------------------- */

export interface Balance {
  supporting: number;
  contradicting: number;
  neutral: number;
  independent_sources: number;
  total: number;
}

export function balanceOf(links: { stance: Stance; evidence: EvidenceItem | undefined }[]): Balance {
  const groups = new Set<string>();
  const balance: Balance = { supporting: 0, contradicting: 0, neutral: 0, independent_sources: 0, total: 0 };
  for (const { stance, evidence } of links) {
    if (!evidence || evidence.duplicate_of) continue;
    balance.total += 1;
    if (stance === "supports") balance.supporting += 1;
    else if (stance === "contradicts") balance.contradicting += 1;
    else balance.neutral += 1;
    groups.add(evidence.independence_group);
  }
  balance.independent_sources = groups.size;
  return balance;
}

/** Evidence strength 0–100: quality-weighted, independence-aware, contradiction-penalised. */
export const EVIDENCE_STRENGTH_RULE =
  "Mean source quality of non-duplicate evidence × net support share (supporting − contradicting over decisive records), scaled by independent-source coverage (saturates at 6 groups).";

export function evidenceStrength(links: { stance: Stance; evidence: EvidenceItem | undefined }[]): number {
  const valid = links.filter((l) => l.evidence && !l.evidence.duplicate_of);
  if (valid.length === 0) return 0;
  const qualities = valid.map((l) => l.evidence?.quality ?? 50);
  const meanQuality = qualities.reduce((a, b) => a + b, 0) / qualities.length;
  const b = balanceOf(valid);
  const decisive = b.supporting + b.contradicting;
  const net = decisive === 0 ? 0 : Math.max(0, (b.supporting - b.contradicting) / decisive);
  const coverage = Math.min(b.independent_sources / 6, 1);
  return Math.round(meanQuality * (0.4 + 0.6 * net) * (0.5 + 0.5 * coverage));
}

/* ---------------------------------------------------------------- */
/* Confidence (separate from priority)                               */
/* ---------------------------------------------------------------- */

export type Confidence = "High" | "Medium" | "Low";

export const CONFIDENCE_RULE =
  "High: evidence rated ≥3, uncertainty ≤1, ≥4 independent sources and contradictions below 35%. Low: evidence ≤1, uncertainty ≥3 or fewer than 2 independent sources. Otherwise Medium.";

export function confidenceOf(factors: PriorityFactors | null, balance: Balance): Confidence {
  if (!factors) return "Low";
  const decisive = balance.supporting + balance.contradicting;
  const contradictionShare = decisive === 0 ? 0 : balance.contradicting / decisive;
  if (factors.evidence <= 1 || factors.uncertainty >= 3 || balance.independent_sources < 2) return "Low";
  if (factors.evidence >= 3 && factors.uncertainty <= 1 && balance.independent_sources >= 4 && contradictionShare < 0.35) return "High";
  return "Medium";
}

export function confidenceForHypothesis(balance: Balance): Confidence {
  // The current theme links are classified from extracted polarity, without
  // human entailment review. Record volume alone cannot raise confidence.
  void balance;
  return "Low";
}

/* ---------------------------------------------------------------- */
/* Hypothesis status                                                 */
/* ---------------------------------------------------------------- */

export function hypothesisStatus(balance: Balance): HypothesisStatus {
  const decisive = balance.supporting + balance.contradicting;
  if (decisive < 3) return "insufficient";
  const share = balance.supporting / decisive;
  if (share >= 0.7) return "supported";
  if (share <= 0.35) return "not_supported";
  return "contested";
}

export const HYPOTHESIS_STATUS_LABEL: Record<HypothesisStatus, string> = {
  supported: "Concern observed",
  contested: "Mixed signals",
  not_supported: "Few concerns",
  insufficient: "Few records",
};

/* ---------------------------------------------------------------- */
/* PM decision status (state machine in docs/HUMAN_REVIEW_AND_AUDIT) */
/* ---------------------------------------------------------------- */

export type DecisionStatus = "draft" | "under_review" | "approved" | "rejected" | "challenged" | "deferred";

export const DECISION_STATUS_LABEL: Record<DecisionStatus, string> = {
  draft: "Draft",
  under_review: "Under review",
  approved: "Approved",
  rejected: "Rejected",
  challenged: "Challenged",
  deferred: "Deferred",
};

export function decisionStatus(latest: RequirementRevision, decisions: Decision[]): DecisionStatus {
  const forRevision = decisions.filter((d) => d.requirement_revision === latest.revision);
  const last = forRevision[forRevision.length - 1];
  if (!last) return latest.lifecycle_status === "draft" ? "draft" : "under_review";
  switch (last.action) {
    case "approve":
      return "approved";
    case "reject":
      return "rejected";
    case "challenge":
      return "challenged";
    case "defer":
      return "deferred";
    case "edit":
      return "under_review";
  }
}

/* ---------------------------------------------------------------- */
/* Lookups                                                            */
/* ---------------------------------------------------------------- */

export function latestRevision(bundle: RequirementBundle): RequirementRevision {
  const latest = bundle.revisions[bundle.revisions.length - 1];
  if (!latest) throw new Error(`requirement ${bundle.display_id} has no revisions`);
  return latest;
}

/** Latest saved PM assessment for the current revision, if any. */
export function currentAssessment(bundle: RequirementBundle): PriorityAssessment | null {
  const rev = latestRevision(bundle).revision;
  const forRev = bundle.assessments.filter((a) => a.requirement_revision === rev);
  return forRev[forRev.length - 1] ?? null;
}

/** Factors in force: saved PM assessment for this revision, else the authored seed. */
export function currentFactors(bundle: RequirementBundle): { factors: PriorityFactors; basis: "saved" | "seed"; assessment: PriorityAssessment | null } {
  const assessment = currentAssessment(bundle);
  return assessment ? { factors: assessment.factors, basis: "saved", assessment } : { factors: bundle.proposal.factors, basis: "seed", assessment: null };
}

export function inScope(bundle: RequirementBundle, market: MarketCode) {
  return bundle.scope_markets.includes(market);
}

export function hypothesisLinks(h: Hypothesis, evidenceById: Map<string, EvidenceItem>) {
  return h.links.map((l) => ({ ...l, evidence: evidenceById.get(l.evidence_id) }));
}

export function findingLinks(
  f: Finding,
  hypothesesById: Map<string, Hypothesis>,
  evidenceById: Map<string, EvidenceItem>,
) {
  const seen = new Set<string>();
  const out: { stance: Stance; evidence: EvidenceItem | undefined; note: string; hypothesis_id: string; evidence_id: string }[] = [];
  for (const hid of f.hypothesis_ids) {
    const h = hypothesesById.get(hid);
    if (!h) continue;
    for (const link of h.links) {
      if (seen.has(link.evidence_id)) continue;
      seen.add(link.evidence_id);
      out.push({ ...link, hypothesis_id: hid, evidence: evidenceById.get(link.evidence_id) });
    }
  }
  return out;
}

export const TOPIC_LABEL: Record<string, string> = {
  charging: "Charging",
  infotainment: "Infotainment",
  comfort: "Comfort",
  range: "Range",
  market_trend: "Market trend",
  assistance: "Driver assistance",
  practicality: "Practicality",
};

export const FAMILY_LABEL: Record<string, string> = {
  government_statistics: "Government",
  independent_test_org: "Independent test",
  official_manufacturer: "Manufacturer",
  professional_review: "Professional review",
  market_report: "Market report",
  youtube_review: "YouTube",
  customer_forum: "Customer forum",
  reddit: "Reddit",
  app_review: "App review",
  dealer: "Dealer",
  other: "Other",
  supplied_feedback: "Customer feedback",
};

export const PROVENANCE_LABEL = {
  bmw_record: "BMW record",
  pipeline: "Pipeline",
  curated_seed: "Curated seed",
  synthetic: "Synthetic",
} as const;

export const PROVENANCE_HINT = {
  bmw_record: "Supplied BMW customer-feedback record cited as an anchor by the successor proposals. Verbatim text stays in the private database.",
  pipeline: "Extracted by external_research_pipeline from a scraped page; exact span verified.",
  curated_seed: "Curated discovery note in research/web_evidence_seed.jsonl; needs snapshot and locator validation.",
  synthetic: "Synthetic illustration for the demo. Not a real customer record or captured source.",
} as const;

export function humanize(value: string) {
  return value.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

export function formatDate(iso: string | null) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric", timeZone: "Europe/Berlin" });
}

export function formatDateTime(iso: string) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-GB", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Berlin",
  });
}

export function formatTime(iso: string) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "Europe/Berlin" });
}
