/**
 * Requirement bundles built from configs/successor_proposals_v1.json — the
 * authored US 5 Series (G60) successor proposals on origin/main.
 *
 * Proposal text and seed factor ratings are authored draft data. Real anchors
 * and extracted signals are loaded from the evidence database. As in
 * bmw_pm.decision.planning.proposal_for, the curated US
 * hypotheses are never transferred to another vehicle or market.
 */
import type { RequirementEvidenceLink, RequirementRevision, Signal, SuccessorProposal, SuccessorProposalFile } from "@/lib/domain/contracts";
import { hashString } from "@/lib/domain/scoring";
import type { BenchmarkTopic, MarketCode, RequirementBundle } from "@/lib/domain/model";

interface DomainMeta {
  display_id: string;
  topic: string;
  finding_ids: string[];
  benchmark_topic: BenchmarkTopic | null;
  powertrains: string[];
  alternatives: string[];
  de: string;
}

const META: Record<string, DomainMeta> = {
  controls_usability: {
    display_id: "REQ-CTL-01",
    topic: "infotainment",
    finding_ids: ["FND-CTL-01"],
    benchmark_topic: "controls",
    powertrains: ["ICE", "PHEV", "BEV"],
    alternatives: ["Dedicated tactile controls", "Persistent climate shortcuts", "Discoverable voice path"],
    de: "ADAC expert criticism of touchscreen climate and Euro NCAP 2026 HMI context exist; no German verbatims are linked.",
  },
  software_reliability: {
    display_id: "REQ-CON-02",
    topic: "infotainment",
    finding_ids: ["FND-CON-01"],
    benchmark_topic: "connected",
    powertrains: ["ICE", "PHEV", "BEV"],
    alternatives: ["Pending / confirmed / failed command states", "Local vehicle connectivity fallback", "Actionable recovery prompts"],
    de: "No German connected-service customer evidence is captured.",
  },
  charging_and_range: {
    display_id: "REQ-TRP-03",
    topic: "range",
    finding_ids: ["FND-TRP-01"],
    benchmark_topic: "charging",
    powertrains: ["BEV", "PHEV"],
    alternatives: ["Condition-aware arrival-energy prediction", "Range band instead of a single value", "Faster charging hardware (separate engineering question)"],
    de: "ADAC i5 test notes are German context, not a German customer sample. Compare test conditions before transfer.",
  },
  ride_and_comfort: {
    display_id: "REQ-SEA-04",
    topic: "comfort",
    finding_ids: ["FND-SEA-01"],
    benchmark_topic: "comfort",
    powertrains: ["ICE", "PHEV", "BEV"],
    alternatives: ["Guided seat and lumbar setup", "Profile-linked seat memory with confirmation", "Ergonomic hardware change (only after root cause)"],
    de: "No German seating evidence is linked.",
  },
  driver_assistance: {
    display_id: "REQ-ADS-05",
    topic: "assistance",
    finding_ids: ["FND-ADS-01"],
    benchmark_topic: "assistance",
    powertrains: ["ICE", "PHEV", "BEV"],
    alternatives: ["Distinct available / active / limited states", "Predictable cancel and resume feedback", "Handover confirmation"],
    de: "Euro NCAP assessment context only; no German assistance reports are linked.",
  },
  storage_and_practicality: {
    display_id: "REQ-STO-06",
    topic: "practicality",
    finding_ids: ["FND-STO-01"],
    benchmark_topic: null,
    powertrains: ["ICE", "PHEV", "BEV"],
    alternatives: ["Adaptive cupholder retention", "Relocated phone charging tray"],
    de: "No German storage evidence is linked.",
  },
  noise_and_refinement: {
    display_id: "REQ-NVH-07",
    topic: "comfort",
    finding_ids: ["FND-NVH-01"],
    benchmark_topic: "comfort",
    powertrains: ["ICE", "PHEV", "BEV"],
    alternatives: ["Targeted trim and window seal fixes", "Customer noise-reporting and service path"],
    de: "No German owner reports of cabin refinement are linked.",
  },
};

const CN = "No China verbatims are supplied; the China customer study is aggregate context only. Zero signals cannot establish no need.";
const EU = "No European verbatims outside Germany are linked. Euro NCAP 2026 HMI context applies to controls and assistance only.";

/** Signals per domain, split by polarity, used as RequirementEvidenceLinks. */
function linksFor(domain: string, signals: Signal[]): { support: Signal[]; counter: Signal[]; context: Signal[] } {
  const own = signals.filter((s) => s.need_domain === domain);
  return {
    support: own.filter((s) => s.polarity === "complaint" || s.polarity === "aspiration"),
    counter: own.filter((s) => s.polarity === "praise"),
    context: own.filter((s) => s.polarity === "mixed" || s.polarity === "observation"),
  };
}

function toLink(signal: Signal, role: RequirementEvidenceLink["role"]): RequirementEvidenceLink | null {
  const span = signal.evidence_spans[0];
  if (!span) return null;
  return {
    signal_id: signal.signal_id,
    role,
    atomic_claim: signal.atomic_claim,
    locator: span.locator,
    exact_span_checked: true,
    semantic_entailment: "unreviewed",
    provenance: "supplied_anonymized",
    author_expertise: "unknown",
  };
}

function revisionFrom(p: SuccessorProposal, meta: DomainMeta, signals: Signal[], eligible: number): RequirementRevision {
  const { support, counter, context } = linksFor(p.domain, signals);
  return {
    schema_version: "1",
    requirement_id: `req-${hashString(`g60-us-${p.domain}`)}${hashString(p.outcome)}`,
    revision: 1,
    title: p.title,
    customer_outcome: p.outcome,
    scope: { models: ["G60"], countries: ["US"], powertrains: meta.powertrains, use_cases: [] },
    use_conditions: ["Conditions limited to those stated in linked US feedback; a reviewed test protocol is pending."],
    acceptance_proposal: { method: p.validation, target: null, unit: null },
    target_status: "pending_engineering_review",
    supporting_signal_ids: [...p.anchor_ids, ...support.map((s) => s.signal_id)],
    counter_signal_ids: counter.map((s) => s.signal_id),
    context_signal_ids: context.map((s) => s.signal_id),
    evidence_links: [
      ...support.map((s) => toLink(s, "supports")),
      ...counter.map((s) => toLink(s, "preserves")),
      ...context.map((s) => toLink(s, "context")),
    ].filter((l): l is RequirementEvidenceLink => l !== null),
    context_observation_ids: [],
    alternatives: meta.alternatives,
    assumptions: [
      p.future_assumption,
      "Feedback IDs are records, not verified unique people or customers.",
      "Seed factor ratings are illustrative PM judgements, not measured impacts.",
    ],
    missing_evidence: [
      "Engineering feasibility and implementation cost are not supplied.",
      "Semantic entailment of linked evidence still needs human assessment.",
      `Revisit when: ${p.review_trigger}`,
    ],
    feasibility: "unknown",
    implementation_cost: null,
    implementation_cost_missing_reason: "Not supplied",
    lifecycle_status: "needs_review",
    supersedes_revision: null,
    created_by: "pipeline:baseline_no_ai + successor_us_g60_v1",
    created_at: "2026-10-10T14:22:00Z",
    denominator_feedback_records: eligible,
    processed_feedback_records: eligible,
    support_count: new Set(support.map((s) => s.feedback_record_id)).size,
    counter_count: new Set(counter.map((s) => s.feedback_record_id)).size,
  };
}

export function buildRequirements(file: SuccessorProposalFile, signals: Signal[], eligible: number, resolvedAnchors: Set<string>): RequirementBundle[] {
  return file.proposals
    .filter((p) => META[p.domain] && p.anchor_ids.every((id) => resolvedAnchors.has(id)))
    .map((p) => {
      const meta = META[p.domain]!;
      const revision = revisionFrom(p, meta, signals, eligible);
      const market_context: Partial<Record<MarketCode, string>> = { DE: meta.de, CN, EU };
      return {
        display_id: meta.display_id,
        domain: p.domain,
        topic: meta.topic,
        scope_markets: ["US"],
        revisions: [revision],
        proposal: p,
        assessments: [],
        decisions: [],
        finding_ids: meta.finding_ids,
        benchmark_topic: meta.benchmark_topic,
        market_context,
      };
    });
}
