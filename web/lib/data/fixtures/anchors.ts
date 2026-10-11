/**
 * Anchor records cited by configs/successor_proposals_v1.json.
 *
 * IDs, rows and the paraphrased observations come from the proposal
 * interpretations and docs/DEMO.md. The verbatim text lives only in the
 * private bmw_pm.db and is never copied into the frontend.
 */
import type { EvidenceItem } from "@/lib/domain/model";

interface Anchor {
  id: string;
  row: number | null;
  powertrain: string;
  topic: EvidenceItem["topic"];
  subtopic: string;
  claim: string;
}

const ANCHORS: Anchor[] = [
  { id: "G60-0271", row: 344, powertrain: "ICE", topic: "infotainment", subtopic: "climate_control_interaction", claim: "Reports distracting touchscreen airflow adjustment and a preference for knobs; was unaware of existing voice capability." },
  { id: "G60-0092", row: 114, powertrain: "—", topic: "comfort", subtopic: "climate_comfort", claim: "Praises climate performance and cabin comfort — a different outcome from control usability." },
  { id: "G60-0051", row: 59, powertrain: "BEVE", topic: "range", subtopic: "real_world_range", claim: "Multi-topic record: remote commands shown as successful without effect, inaccurate range estimates in cold weather, window rattle and creaking trim." },
  { id: "G60-0078", row: 95, powertrain: "BEVE", topic: "range", subtopic: "real_world_range", claim: "Reports a successful 20-mile daily commute with home charging." },
  { id: "G60-0320", row: null, powertrain: "—", topic: "comfort", subtopic: "seat_comfort", claim: "Reports difficulty finding a comfortable seating position." },
  { id: "G60-1877", row: null, powertrain: "—", topic: "comfort", subtopic: "seat_comfort", claim: "Reports seat-memory trouble, followed by guidance on the existing profile / save behaviour." },
  { id: "G60-2545", row: null, powertrain: "—", topic: "infotainment", subtopic: "assistance_state", claim: "Describes confusing cancel / resume behaviour of driver assistance." },
  { id: "G60-1602", row: null, powertrain: "—", topic: "infotainment", subtopic: "assistance_state", claim: "Reports a frightening parking-assistance event. Potentially severe — routed to qualified review regardless of rank." },
  { id: "G60-3055", row: null, powertrain: "—", topic: "comfort", subtopic: "interior_space", claim: "Reports bottles tipping over and blocked phone access in the front console." },
];

export const ANCHOR_IDS = new Set(ANCHORS.map((a) => a.id));

export function anchorEvidence(): EvidenceItem[] {
  return ANCHORS.map((a) => ({
    id: a.id,
    kind: "customer_feedback",
    provenance: "bmw_record",
    claim: a.claim,
    excerpt: "Verbatim held in the private bmw_pm.db (supplied, anonymised). Not copied into this workspace; the observation above paraphrases the proposal's interpretation.",
    excerpt_language: "en",
    brand: "BMW",
    vehicle: `5 Series G60${a.powertrain !== "—" ? ` ${a.powertrain}` : ""} (US)`,
    market: "US",
    topic: a.topic,
    subtopic: a.subtopic,
    source_name: "G60 customer feedback (supplied)",
    source_title: "G60_feedback_hackathon.xlsx · Feedback_Explorer",
    source_url: null,
    source_family: "supplied_feedback",
    locator: a.row ? `Feedback_Explorer row ${a.row} · ${a.id}` : `${a.id} · row in bmw_pm.db`,
    quality: null,
    independence_group: a.id,
    duplicate_of: null,
    published_at: null,
    retrieved_at: "2026-10-10T08:00:00Z",
    numeric_value: null,
    numeric_unit: null,
    limitation: "Supplied-anonymised record: author ownership and expertise unknown, observation date not supplied. One record is not prevalence.",
    raw: {
      record_kind: "anchor_reference",
      source_record_id: a.id,
      row: a.row,
      cited_by: "configs/successor_proposals_v1.json",
    },
  }));
}
