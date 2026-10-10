/**
 * SYNTHETIC ILLUSTRATION — customer feedback signals for the demo.
 *
 * Shaped exactly like bmw_pm.contracts.Signal (provider_mode baseline_no_ai,
 * one EvidenceSpan per signal, sheet_range locator). The text is written for
 * demonstration; it is not quoted from the supplied G60 workbook. Real
 * signals come from `bmw-pm run` and live in bmw_pm.db.
 */
import type { Polarity, Signal, Topic } from "@/lib/domain/contracts";
import type { EvidenceItem, MarketCode } from "@/lib/domain/model";

export const SYNTHETIC_FEEDBACK_SOURCE_ID = "synthetic-feedback-demo";
const SYNTHETIC_HASH = "5e7a1c0d".repeat(8);
const RUN_ID = "run-demo-baseline-20261010";

export const DOMAIN_OUTCOME: Record<string, string> = {
  controls_usability: "Occupants can complete frequently used control tasks with low visual and manual effort.",
  software_reliability:
    "Occupants can rely on vehicle software and connected functions to work consistently during normal use.",
  charging_and_range: "Electric-vehicle users can complete intended journeys and charging stops with predictable effort.",
  ride_and_comfort: "Occupants remain comfortable in their seating position and intended journey conditions.",
  noise_and_refinement: "Occupants experience an appropriately quiet and refined cabin in the stated driving conditions.",
  storage_and_practicality: "Occupants can carry and organize everyday items needed for intended journeys.",
  driver_assistance: "Drivers can use assistance functions predictably without avoidable supervision burden.",
};

export const DOMAIN_TOPIC: Record<string, Topic> = {
  controls_usability: "infotainment",
  software_reliability: "infotainment",
  charging_and_range: "charging",
  ride_and_comfort: "comfort",
  noise_and_refinement: "comfort",
  storage_and_practicality: "comfort",
  driver_assistance: "infotainment",
};

interface Spec {
  row: number;
  domain: keyof typeof DOMAIN_OUTCOME;
  subtopic: string;
  market: MarketCode;
  powertrain: "BEV" | "PHEV" | "ICE";
  polarity: Polarity;
  claim: string;
  text: string;
}

const SPECS: Spec[] = [
  // Climate controls
  { row: 1412, domain: "controls_usability", subtopic: "climate_control_interaction", market: "US", powertrain: "ICE", polarity: "complaint", claim: "Seat heating takes several taps every cold morning.", text: "Seat heating takes three taps, in winter I do it every single morning." },
  { row: 1419, domain: "controls_usability", subtopic: "physical_controls", market: "US", powertrain: "PHEV", polarity: "aspiration", claim: "Owner wants dedicated controls for temperature and fan.", text: "Please bring back real buttons for temperature and fan speed." },
  { row: 1427, domain: "controls_usability", subtopic: "climate_control_interaction", market: "US", powertrain: "BEV", polarity: "complaint", claim: "Defrost is hard to reach quickly in the touchscreen.", text: "When the windshield fogs up I need the defrost right away, not three menus deep." },
  { row: 1433, domain: "controls_usability", subtopic: "voice_assistant", market: "US", powertrain: "BEV", polarity: "praise", claim: "Voice control handles climate requests well once discovered.", text: "Once I learned I can just say 'I'm cold' it works better than any button." },
  { row: 1440, domain: "controls_usability", subtopic: "display_usability", market: "US", powertrain: "ICE", polarity: "praise", claim: "The curved display is clear and responsive.", text: "The curved display is sharp and reacts quickly." },

  // Connected services / remote commands
  { row: 1611, domain: "software_reliability", subtopic: "connected_services", market: "US", powertrain: "BEV", polarity: "complaint", claim: "App reported the car locked, but it was not.", text: "The app said locked, I walked back and the doors were open." },
  { row: 1618, domain: "software_reliability", subtopic: "connected_services", market: "US", powertrain: "PHEV", polarity: "complaint", claim: "Remote pre-conditioning shows success without starting.", text: "Remote climate says started, car is still hot when I get in." },
  { row: 1626, domain: "software_reliability", subtopic: "software_reliability", market: "US", powertrain: "ICE", polarity: "praise", claim: "Over-the-air updates fixed earlier app issues.", text: "The last remote update fixed the bugs I had in the first months." },

  // Trip energy and range
  { row: 1538, domain: "charging_and_range", subtopic: "real_world_range", market: "US", powertrain: "BEV", polarity: "complaint", claim: "Range estimate drops faster than displayed on highway trips.", text: "The estimate says I can make it and 50 miles later it suggests a charging stop." },
  { row: 1545, domain: "charging_and_range", subtopic: "real_world_range", market: "US", powertrain: "BEV", polarity: "complaint", claim: "Winter range is much lower than the displayed estimate.", text: "In January the range number is just wrong, I lose a third on the interstate." },
  { row: 1551, domain: "charging_and_range", subtopic: "real_world_range", market: "US", powertrain: "BEV", polarity: "praise", claim: "Range is never an issue for a daily commute with home charging.", text: "For my commute with a charger at home range is never a topic." },
  { row: 1188, domain: "charging_and_range", subtopic: "charging_stop_duration", market: "US", powertrain: "BEV", polarity: "complaint", claim: "Road-trip charging stops feel long for the price class.", text: "Road trips are fine but the stops are longer than I expected for a car at this price." },
  { row: 1203, domain: "charging_and_range", subtopic: "plug_and_charge", market: "US", powertrain: "BEV", polarity: "complaint", claim: "Public charging start-up is unreliable on some networks.", text: "Plug and charge only works at some stations, at others I still need two apps and a card." },

  // Seating
  { row: 1720, domain: "ride_and_comfort", subtopic: "front_seat_comfort", market: "US", powertrain: "ICE", polarity: "complaint", claim: "Driver cannot find a comfortable lumbar setting.", text: "Tried every lumbar setting and still get back pain after an hour." },
  { row: 1727, domain: "ride_and_comfort", subtopic: "seat_comfort", market: "US", powertrain: "PHEV", polarity: "complaint", claim: "Shared car: seat position lost after spouse drives.", text: "My wife drives it and I have to redo my seat every time, the memory button confuses me." },
  { row: 1733, domain: "ride_and_comfort", subtopic: "seat_comfort", market: "US", powertrain: "BEV", polarity: "praise", claim: "Seats are comfortable on long drives.", text: "Did 600 miles in a day and felt fine, best seats I have had." },

  // Driver assistance
  { row: 1801, domain: "driver_assistance", subtopic: "assistance_state", market: "US", powertrain: "ICE", polarity: "complaint", claim: "Unclear whether adaptive cruise is active or only available.", text: "I can never tell if cruise is on or just ready, the icons look the same to me." },
  { row: 1809, domain: "driver_assistance", subtopic: "assistance_state", market: "US", powertrain: "BEV", polarity: "praise", claim: "Adaptive cruise makes highway commuting easier.", text: "Adaptive cruise on the highway is excellent, makes my commute so much easier." },

  // Storage
  { row: 1901, domain: "storage_and_practicality", subtopic: "interior_space", market: "US", powertrain: "ICE", polarity: "complaint", claim: "Large bottles do not fit the cupholders securely.", text: "My 32 oz bottle tips over in the cupholder on every turn." },
  { row: 1907, domain: "storage_and_practicality", subtopic: "interior_space", market: "US", powertrain: "BEV", polarity: "complaint", claim: "Phone tray is blocked when cups are in use.", text: "With two coffees in the holders I cannot get my phone off the charger." },

  // Noise
  { row: 1950, domain: "noise_and_refinement", subtopic: "cabin_noise", market: "US", powertrain: "BEV", polarity: "complaint", claim: "Rattle from the rear window trim on rough roads.", text: "There is a rattle from the rear window trim on rough pavement." },
  { row: 1956, domain: "noise_and_refinement", subtopic: "cabin_noise", market: "US", powertrain: "ICE", polarity: "praise", claim: "Cabin is very quiet at highway speed.", text: "At 75 it is quieter than my previous 7 Series." },
];

const RANGE_SUBTOPICS = new Set(["wltp_range", "real_world_range", "winter_range", "energy_consumption"]);

function signalFromSpec(spec: Spec): Signal {
  const id = `SIG-${spec.market}-${String(spec.row).padStart(4, "0")}`;
  return {
    schema_version: "1",
    signal_id: id,
    feedback_record_id: `SYN-${spec.market}-${String(spec.row).padStart(4, "0")}`,
    signal_type: "customer_feedback",
    need_domain: spec.domain,
    atomic_claim: spec.claim,
    customer_outcome: DOMAIN_OUTCOME[spec.domain] ?? "",
    polarity: spec.polarity,
    severity_label: null,
    use_context: null,
    vehicle_scope: { model: "G60", country: spec.market, powertrain: spec.powertrain },
    evidence_spans: [
      {
        record_id: `SYN-${spec.market}-${String(spec.row).padStart(4, "0")}`,
        locator: {
          schema_version: "1",
          source_id: SYNTHETIC_FEEDBACK_SOURCE_ID,
          source_hash: SYNTHETIC_HASH,
          locator_type: "sheet_range",
          sheet: "Feedback_Explorer",
          cell_range: `E${spec.row}`,
          page: null,
          section: null,
          exact_quote: spec.text,
          extracted_value: null,
          normalized_text_hash: null,
        },
        text: spec.text,
        start: 0,
        end: spec.text.length,
      },
    ],
    extraction_status: "validated",
    run_id: RUN_ID,
    provider_mode: "baseline_no_ai",
  };
}

export const SYNTHETIC_SIGNALS: Signal[] = SPECS.map(signalFromSpec);

export function feedbackEvidence(signals: Signal[]): EvidenceItem[] {
  return signals.map((signal, index) => {
    const spec = SPECS[index];
    const span = signal.evidence_spans[0];
    const market = (signal.vehicle_scope.country ?? "DE") as MarketCode;
    return {
      id: signal.signal_id,
      kind: "customer_feedback",
      provenance: "synthetic",
      claim: signal.atomic_claim,
      excerpt: span?.text ?? "",
      excerpt_language: "en",
      brand: "BMW",
      vehicle: `5 Series G60 ${signal.vehicle_scope.powertrain ?? ""} (US)`.trim(),
      market,
      topic: RANGE_SUBTOPICS.has(spec?.subtopic ?? "") ? "range" : (DOMAIN_TOPIC[signal.need_domain] ?? "comfort"),
      subtopic: spec?.subtopic ?? signal.need_domain,
      source_name: "G60 customer feedback (synthetic)",
      source_title: `Feedback record ${signal.feedback_record_id}`,
      source_url: null,
      source_family: "supplied_feedback",
      locator: `${span?.locator.sheet ?? ""}!${span?.locator.cell_range ?? ""}`,
      quality: null,
      independence_group: signal.feedback_record_id,
      duplicate_of: null,
      published_at: null,
      retrieved_at: "2026-10-10T09:00:00Z",
      numeric_value: null,
      numeric_unit: null,
      limitation:
        "Supplied-anonymized record; author ownership and expertise unknown. Observation date not supplied.",
      raw: signal,
    };
  });
}
