/**
 * Reasoning graph: hypotheses → findings, aligned with the authored successor
 * proposals (configs/successor_proposals_v1.json), plus the cohort benchmark.
 *
 * Evidence IDs come from four origins:
 *   G60-xxxx          supplied BMW feedback records cited as proposal anchors
 *   EXT-xxxxxxxxxxxx  external_research_pipeline output (real, span-verified)
 *   seed-/ctx-        curated research seeds and planning context (real URLs)
 *   SIG-/EXT-SYN-     synthetic illustration fixtures
 * A link whose evidence is not loaded is ignored by the counters.
 */
import type { CompetitorBenchmark, Finding, Hypothesis } from "@/lib/domain/model";

const s = (evidence_id: string, note = "") => ({ evidence_id, stance: "supports" as const, note });
const c = (evidence_id: string, note = "") => ({ evidence_id, stance: "contradicts" as const, note });
const n = (evidence_id: string, note = "") => ({ evidence_id, stance: "neutral" as const, note });

export const HYPOTHESES: Hypothesis[] = [
  {
    id: "HYP-CTL-01",
    statement: "Everyday climate adjustment is hard because of control access, not missing functionality.",
    topic: "infotainment",
    market: "US",
    links: [
      s("G60-0271", "Distracting airflow adjustment; prefers knobs."),
      s("SIG-US-1412", "Seat heating needs several taps."),
      s("SIG-US-1419", "Asks for dedicated temperature / fan controls."),
      s("SIG-US-1427", "Defrost not reachable quickly."),
      s("seed-W03-02", "ADAC reviewer: touchscreen climate operation more cumbersome (DE test)."),
      s("EXT-SYN-yt-touch", "Video review criticises touch-only fan control."),
      c("SIG-US-1433", "Voice control preferred once discovered."),
      c("EXT-SYN-review-voice", "Voice climate commands reliable in test."),
      n("G60-0092", "Praises climate performance — a different outcome."),
      n("SIG-US-1440", "Display quality praised; separate from control effort."),
      n("seed-W05-01", "Euro NCAP 2026 assesses essential-control placement; context, not a mandate."),
    ],
  },
  {
    id: "HYP-CTL-02",
    statement: "Part of the reported difficulty is discoverability of existing voice control.",
    topic: "infotainment",
    market: "US",
    links: [
      s("G60-0271", "Unaware of existing voice capability."),
      s("SIG-US-1433", "Voice works well once learned."),
      s("EXT-SYN-review-voice"),
      c("SIG-US-1427", "Defrost urgency is not solved by discovery alone."),
    ],
  },
  {
    id: "HYP-CON-01",
    statement: "Remote commands report success before the vehicle confirms the action.",
    topic: "infotainment",
    market: "US",
    links: [
      s("G60-0051", "Remote commands labelled successful without the expected effect."),
      s("SIG-US-1611", "App reported locked; doors were open."),
      s("SIG-US-1618", "Remote climate reported started; cabin not conditioned."),
      s("EXT-SYN-app-delay", "App reviews report delayed lock / charging status."),
      c("SIG-US-1626", "OTA update fixed earlier app issues."),
    ],
  },
  {
    id: "HYP-TRP-01",
    statement: "Range estimates lose credibility on cold-weather and long trips, while commuting is unaffected.",
    topic: "range",
    market: "US",
    links: [
      s("G60-0051", "Inaccurate range estimates and cold-weather difficulty."),
      s("SIG-US-1538", "Estimate collapses on highway trips."),
      s("SIG-US-1545", "Winter range far below displayed estimate."),
      c("G60-0078", "Successful 20-mile commute with home charging."),
      c("SIG-US-1551", "Commuting with home charging is never an issue."),
      c("EXT-248fb5b9fc68", "ADAC: Munich–Berlin feasible with two 20-minute stops."),
      n("EXT-2106b67c3bcc", "Heat pump fitted — reduces, but does not explain, winter loss."),
      n("seed-W03-01", "ADAC 500 km test range; conditions need inspection."),
      n("ctx-iea-gevo", "IEA scenarios: plan with several EV / charging trajectories."),
    ],
  },
  {
    id: "HYP-TRP-02",
    statement: "Charging-stop duration adds to long-trip cost but is secondary to planning uncertainty.",
    topic: "charging",
    market: "US",
    links: [
      s("SIG-US-1188", "Road-trip stops longer than expected."),
      s("EXT-aa0a8979ac24", "ADAC: still a 400 V system."),
      s("EXT-6d16f75ad45b", "ADAC: high charging power falls quickly."),
      s("EXT-SYN-a6-time", "A6 e-tron ≈21 min 10–80% (manufacturer)."),
      s("EXT-SYN-taycan-time", "Taycan ≈18 min 10–80% (manufacturer)."),
      s("SIG-US-1203", "Public charging start-up unreliable."),
      c("EXT-7ad2eca3a501", "ADAC measured 207 kW peak — competitive for 400 V."),
      c("EXT-861b66b47c47", "ADAC: 184 km added in 20 min."),
      c("seed-W04-01", "EQE 320 4MATIC: 32 min 10–80% (US spec)."),
      n("EXT-SYN-repost-207", "Duplicate of the ADAC 207 kW claim; excluded from counts."),
      n("ctx-mbusa-eqe", "EQE lists electric-navigation support; packaging context only."),
    ],
  },
  {
    id: "HYP-SEA-01",
    statement: "Seating complaints are partly a setup and memory-discoverability problem, not seat hardware.",
    topic: "comfort",
    market: "US",
    links: [
      s("G60-0320", "Cannot find a comfortable position."),
      s("G60-1877", "Memory trouble, resolved with guidance on existing profiles."),
      s("SIG-US-1720", "Lumbar settings do not help."),
      s("SIG-US-1727", "Shared car: seat position lost; memory button confusing."),
      c("G60-0092", "Praises cabin comfort."),
      c("SIG-US-1733", "600 miles in a day without discomfort."),
    ],
  },
  {
    id: "HYP-ADS-01",
    statement: "Assistance states and cancel / resume behaviour are not understood by drivers.",
    topic: "infotainment",
    market: "US",
    links: [
      s("G60-2545", "Confusing cancel / resume behaviour."),
      s("G60-1602", "Frightening parking-assistance event — severe, needs qualified review."),
      s("SIG-US-1801", "Cannot tell active from available."),
      c("SIG-US-1809", "Adaptive cruise praised for commuting."),
    ],
  },
  {
    id: "HYP-STO-01",
    statement: "Front storage does not secure everyday drinks while keeping the phone accessible.",
    topic: "comfort",
    market: "US",
    links: [s("G60-3055", "Bottles tip; phone access blocked."), s("SIG-US-1901"), s("SIG-US-1907")],
  },
  {
    id: "HYP-NVH-01",
    statement: "Local trim noises, not overall cabin noise, drive refinement complaints.",
    topic: "comfort",
    market: "US",
    links: [
      s("G60-0051", "Window rattle and creaking trim."),
      s("SIG-US-1950", "Rear window trim rattle on rough roads."),
      c("SIG-US-1956", "Cabin very quiet at highway speed."),
      c("EXT-SYN-review-noise", "Test ranks the i5 among the quietest at 130 km/h."),
    ],
  },
];

export const FINDINGS: Finding[] = [
  {
    id: "FND-CTL-01",
    title: "Climate adjustment effort is an access and discoverability problem",
    summary:
      "Owners report distracting touchscreen airflow, seat-heating and defrost adjustment. The anchor record G60-0271 also shows the owner was unaware of voice control, so onboarding is part of the problem. Climate performance itself is praised.",
    topic: "infotainment",
    market: "US",
    hypothesis_ids: ["HYP-CTL-01", "HYP-CTL-02"],
    customer_need: "Change temperature, fan speed and demisting without menu hunting while driving.",
    requirement_ids: ["REQ-CTL-01"],
    updated_at: "2026-10-10T19:40:00Z",
  },
  {
    id: "FND-CON-01",
    title: "Remote commands show success without vehicle confirmation",
    summary:
      "Customers see 'success' for lock or climate commands that did not take effect. This supports truthful pending / confirmed / failed states. It does not establish a failure rate or a network root cause.",
    topic: "infotainment",
    market: "US",
    hypothesis_ids: ["HYP-CON-01"],
    customer_need: "Trust that a remote command actually happened, or know how to recover.",
    requirement_ids: ["REQ-CON-02"],
    updated_at: "2026-10-10T19:40:00Z",
  },
  {
    id: "FND-TRP-01",
    title: "Trip energy is unpredictable on cold and long journeys",
    summary:
      "Range estimates lose credibility on highway and winter trips, while commuters with home charging report no issue. Charging-stop duration trails 800 V rivals but is a secondary cost. Long-trip planning and daily commuting must be evaluated separately.",
    topic: "range",
    market: "US",
    hypothesis_ids: ["HYP-TRP-01", "HYP-TRP-02"],
    customer_need: "Judge before departure whether a trip is practical and where to charge.",
    requirement_ids: ["REQ-TRP-03"],
    updated_at: "2026-10-10T19:44:39Z",
  },
  {
    id: "FND-SEA-01",
    title: "Seat comfort complaints mix ergonomics with setup discoverability",
    summary:
      "Some drivers cannot find or retain a comfortable position; one was resolved with guidance on existing seat memory. Long-distance comfort is otherwise praised, so the hardware should not be changed for satisfied customers.",
    topic: "comfort",
    market: "US",
    hypothesis_ids: ["HYP-SEA-01"],
    customer_need: "Find a comfortable seating position quickly and get it back every time.",
    requirement_ids: ["REQ-SEA-04"],
    updated_at: "2026-10-10T19:40:00Z",
  },
  {
    id: "FND-ADS-01",
    title: "Assistance states and handover are not understood",
    summary:
      "Drivers cannot tell available from active assistance and find cancel / resume confusing. One potentially severe parking-assistance report needs qualified review regardless of rank. Adaptive cruise itself is valued.",
    topic: "infotainment",
    market: "US",
    hypothesis_ids: ["HYP-ADS-01"],
    customer_need: "Always know what the assistance is doing and how to take back control.",
    requirement_ids: ["REQ-ADS-05"],
    updated_at: "2026-10-10T19:40:00Z",
  },
  {
    id: "FND-STO-01",
    title: "Front storage fails everyday drinks and phone access",
    summary: "Bottles tip over and cups block the phone charger. A concrete daily irritation, supported by few records.",
    topic: "comfort",
    market: "US",
    hypothesis_ids: ["HYP-STO-01"],
    customer_need: "Secure everyday drinks and reach the phone at the same time.",
    requirement_ids: ["REQ-STO-06"],
    updated_at: "2026-10-10T19:40:00Z",
  },
  {
    id: "FND-NVH-01",
    title: "Refinement is valued; complaints concern local trim noises",
    summary:
      "Owners and tests praise overall cabin quiet. Complaints point to specific window and trim rattles, which supports preservation plus targeted fixes rather than more insulation everywhere.",
    topic: "comfort",
    market: "US",
    hypothesis_ids: ["HYP-NVH-01"],
    customer_need: "Keep the quiet cabin and get intrusive rattles fixed.",
    requirement_ids: ["REQ-NVH-07"],
    updated_at: "2026-10-10T19:40:00Z",
  },
];

const none = { position: "no_evidence" as const, summary: "No matched evidence collected", evidence_ids: [] };

export const BENCHMARK: CompetitorBenchmark[] = [
  {
    vehicle: "BMW i5 eDrive40",
    is_reference: true,
    cells: {
      charging: { position: "parity", summary: "400 V · 207 kW peak · ≈30 min 10–80%", evidence_ids: ["EXT-7ad2eca3a501", "EXT-aa0a8979ac24", "EXT-SYN-i5-time"] },
      controls: { position: "parity", summary: "Touch-centred climate; expert criticism", evidence_ids: ["seed-W03-02", "G60-0271"] },
      connected: { position: "parity", summary: "Unconfirmed remote-command status reported", evidence_ids: ["G60-0051"] },
      comfort: { position: "parity", summary: "Quiet at 130 km/h; seat-setup complaints", evidence_ids: ["EXT-SYN-review-noise", "G60-0320"] },
      assistance: { position: "parity", summary: "Cancel / resume confusion reported", evidence_ids: ["G60-2545"] },
    },
  },
  {
    vehicle: "Mercedes EQE",
    is_reference: false,
    cells: {
      charging: { position: "parity", summary: "Electric navigation listed · ≈32 min 10–80% (US spec)", evidence_ids: ["ctx-mbusa-eqe", "seed-W04-01"] },
      controls: none,
      connected: none,
      comfort: { position: "parity", summary: "Dual-zone standard, four-zone optional", evidence_ids: ["ctx-mbusa-eqe"] },
      assistance: none,
    },
  },
  {
    vehicle: "Audi A6 e-tron",
    is_reference: false,
    cells: {
      charging: { position: "ahead", summary: "800 V · 270 kW · ≈21 min", evidence_ids: ["EXT-SYN-a6-power", "EXT-SYN-a6-time"] },
      controls: none,
      connected: none,
      comfort: none,
      assistance: none,
    },
  },
  {
    vehicle: "Porsche Taycan",
    is_reference: false,
    cells: {
      charging: { position: "ahead", summary: "800 V · 320 kW · ≈18 min", evidence_ids: ["EXT-SYN-taycan-power", "EXT-SYN-taycan-time"] },
      controls: none,
      connected: none,
      comfort: none,
      assistance: none,
    },
  },
  {
    vehicle: "Tesla Model S",
    is_reference: false,
    cells: {
      charging: { position: "ahead", summary: "250 kW peak; no matched 10–80% figure", evidence_ids: ["EXT-SYN-models-power"] },
      controls: none,
      connected: none,
      comfort: none,
      assistance: none,
    },
  },
];
