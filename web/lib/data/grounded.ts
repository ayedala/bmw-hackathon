import type { Signal, Topic } from "@/lib/domain/contracts";
import type { EvidenceItem, Finding, Hypothesis, RequirementBundle } from "@/lib/domain/model";
import type { LiveFeedback } from "./live";

const TOPIC: Record<string, Topic> = {
  controls_usability: "infotainment",
  software_reliability: "infotainment",
  charging_and_range: "range",
  ride_and_comfort: "comfort",
  driver_assistance: "infotainment",
  storage_and_practicality: "comfort",
  noise_and_refinement: "comfort",
};

function locator(signal: Signal): string {
  const source = signal.evidence_spans[0]?.locator;
  if (!source) return "Source span unavailable";
  return [source.sheet, source.cell_range].filter(Boolean).join("!") || source.section || "Source span unavailable";
}

export function groundedEvidence(signals: Signal[], anchors: LiveFeedback[]): EvidenceItem[] {
  const byRecord = new Map(anchors.map((a) => [a.source_record_id, a]));
  const domainByRecord = new Map(signals.map((signal) => [signal.feedback_record_id, signal.need_domain]));
  const now = new Date().toISOString();
  const anchorItems: EvidenceItem[] = [...byRecord.values()].map((record) => {
    const source = record.row_locators[0];
    return {
      id: record.source_record_id,
      kind: "customer_feedback",
      provenance: "bmw_record",
      claim: "Supplied customer feedback anchor; interpretation requires review.",
      excerpt: record.redacted_text,
      excerpt_language: "en",
      brand: "BMW",
      vehicle: `5 Series G60 ${record.powertrain || ""} (US)`.trim(),
      market: "US",
      topic: TOPIC[domainByRecord.get(record.record_id) || ""] || "comfort",
      subtopic: domainByRecord.get(record.record_id) || "source_anchor",
      source_name: "G60 customer feedback",
      source_title: "G60_feedback_hackathon.xlsx · Feedback_Explorer",
      source_url: null,
      source_family: "supplied_feedback",
      locator: [source?.sheet, source?.cell_range].filter(Boolean).join("!") || record.source_record_id,
      quality: null,
      independence_group: record.record_id,
      duplicate_of: null,
      published_at: null,
      retrieved_at: now,
      numeric_value: null,
      numeric_unit: null,
      limitation: "Redacted source text. Author identity and observation date were not supplied; one feedback ID is not a person or prevalence estimate.",
      raw: { ...record },
    };
  });
  const signalItems: EvidenceItem[] = signals.map((signal) => ({
    id: signal.signal_id,
    kind: "customer_feedback",
    provenance: "bmw_record",
    claim: signal.atomic_claim,
    excerpt: signal.evidence_spans[0]?.text || "",
    excerpt_language: "en",
    brand: "BMW",
    vehicle: `5 Series G60 ${signal.vehicle_scope.powertrain || ""} (US)`.trim(),
    market: "US",
    topic: TOPIC[signal.need_domain] || "comfort",
    subtopic: signal.need_domain,
    source_name: "G60 customer feedback",
    source_title: "G60_feedback_hackathon.xlsx · Feedback_Explorer",
    source_url: null,
    source_family: "supplied_feedback",
    locator: locator(signal),
    quality: null,
    independence_group: signal.feedback_record_id,
    duplicate_of: null,
    published_at: null,
    retrieved_at: now,
    numeric_value: null,
    numeric_unit: null,
    limitation: "Exact extracted span; whether it supports this proposed requirement remains unreviewed. Feedback IDs are not verified unique people.",
    raw: signal,
  }));
  return [...anchorItems, ...signalItems];
}

/** A theme view over validated spans. Polarity is not semantic entailment. */
export function groundedGraph(bundles: RequirementBundle[], signals: Signal[]): { hypotheses: Hypothesis[]; findings: Finding[] } {
  const hypotheses: Hypothesis[] = [];
  const findings: Finding[] = [];
  for (const bundle of bundles) {
    const seen = new Set<string>();
    const links = signals
      .filter((signal) => signal.need_domain === bundle.domain)
      .filter((signal) => {
        if (seen.has(signal.feedback_record_id)) return false;
        seen.add(signal.feedback_record_id);
        return true;
      })
      .map((signal) => ({
        evidence_id: signal.signal_id,
        stance: signal.polarity === "complaint" || signal.polarity === "aspiration" ? "supports" as const : "neutral" as const,
        note: `Extracted ${signal.polarity}; relevance to the proposed outcome is unreviewed.`,
      }));
    const hypothesisId = `HYP-${bundle.display_id}`;
    const findingId = `FND-${bundle.display_id}`;
    hypotheses.push({ id: hypothesisId, statement: bundle.proposal.interpretation, topic: TOPIC[bundle.domain] || "comfort", market: "US", links });
    findings.push({
      id: findingId,
      title: bundle.proposal.title,
      summary: `Unreviewed theme in US G60 feedback. ${bundle.proposal.interpretation}`,
      topic: TOPIC[bundle.domain] || "comfort",
      market: "US",
      hypothesis_ids: [hypothesisId],
      customer_need: bundle.proposal.outcome,
      requirement_ids: [bundle.display_id],
      updated_at: bundle.revisions[0]?.created_at || new Date().toISOString(),
    });
    bundle.finding_ids = [findingId];
  }
  return { hypotheses, findings };
}
