"""Derive findings, customer needs and requirements from canonical evidence.

Additive and deterministic. Reads
``data/processed/external_evidence.jsonl`` and writes three new JSONL files
beside it. The canonical evidence file is **never** modified, and
``cache_reprocess_evidence.jsonl`` is never read - cache replay is QA only.

Division of labour
------------------
The *wording* of each finding, need and requirement is authored here, grounded
in claims actually present in the evidence. Everything *derived* - which
evidence ids back a finding, how many independent sources it has, its average
source quality, its confidence band, its score - is computed from the store, so
no count or id is ever hand-written.

Evidence is selected by ``(subtopic, keyword)`` predicates rather than by id, so
the artifacts regenerate correctly as the evidence base grows.

Run from inside this folder::

    python build_synthesis.py            # write the three files
    python build_synthesis.py --dry-run  # report only
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone

import config

CREATED_AT = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

FINDINGS_PATH = config.PROCESSED_DIR / "findings.jsonl"
NEEDS_PATH = config.PROCESSED_DIR / "customer_needs.jsonl"
REQUIREMENTS_PATH = config.PROCESSED_DIR / "requirements.jsonl"
SCORES_PATH = config.PROCESSED_DIR / "requirement_scores.jsonl"

#: Reused verbatim from configs/exploratory_equal_v1.json so the external chain
#: scores on the same axes and weights as the internal one. Only
#: ``evidence_backed_reach`` is redefined - its approved definition is a share
#: of eligible internal feedback records, which public web evidence cannot
#: supply. The substitution is declared in every emitted score.
POLICY = {
    "policy_id": "exploratory_equal_external_v1",
    "derived_from": "configs/exploratory_equal_v1.json (exploratory_equal rev 1)",
    "criteria": {
        "customer_impact": 0.25,
        "evidence_backed_reach": 0.25,
        "strategic_contribution": 0.25,
        "competitive_outlook_need": 0.25,
    },
    "deviation": (
        "evidence_backed_reach is computed from independent public sources "
        "instead of the approved internal feedback-record share, which web "
        "evidence cannot supply."
    ),
    "approved": False,
}


@dataclass(frozen=True)
class Selector:
    """Picks evidence rows for one finding.

    Args:
        subtopics: restrict to these subtopics.
        any_keywords: a row's claim must contain at least one (case-insensitive).
        none_keywords: a row's claim must contain none of these.
        require_numeric: keep only rows carrying a numeric value.
        limit: cap the number of ids kept, strongest source quality first.
    """

    subtopics: tuple[str, ...]
    any_keywords: tuple[str, ...] = ()
    none_keywords: tuple[str, ...] = ()
    require_numeric: bool = False
    limit: int = 12

    def select(self, rows: list[dict]) -> list[dict]:
        out = []
        for row in rows:
            if row.get("subtopic") not in self.subtopics:
                continue
            claim = f"{row.get('claim','')} {row.get('evidence_text','')}".lower()
            if self.any_keywords and not any(k in claim for k in self.any_keywords):
                continue
            if any(k in claim for k in self.none_keywords):
                continue
            if self.require_numeric and row.get("numeric_value") is None:
                continue
            out.append(row)
        # Strongest sources first, then widest spread, then stable by id.
        out.sort(key=lambda r: (-int(r.get("source_quality", 0)), str(r.get("evidence_id"))))
        # Prefer breadth: take at most 3 rows per independence group.
        per_group: dict[str, int] = {}
        kept = []
        for row in out:
            group = row.get("independence_group")
            if per_group.get(group, 0) >= 3:
                continue
            per_group[group] = per_group.get(group, 0) + 1
            kept.append(row)
            if len(kept) >= self.limit:
                break
        return kept


@dataclass
class FindingSpec:
    """An authored finding plus the selector that grounds it."""

    key: str
    topic: str
    kind: str                      # bmw_strength | bmw_weakness | competitor_strength | market_trend | customer_friction
    title: str
    summary: str
    selector: Selector
    contradicts: tuple[str, ...] = ()
    notes: str = ""


@dataclass
class NeedSpec:
    key: str
    topic: str
    statement: str
    rationale: str
    finding_keys: tuple[str, ...]
    importance: str
    customer_context: str


@dataclass
class RequirementSpec:
    key: str
    topic: str
    title: str
    requirement: str
    need_keys: tuple[str, ...]
    customer_value: str
    differentiation: str
    rough_effort: str
    rough_cost: str
    validation_method: str
    strategic_contribution: int      # 0-4 on the policy anchors
    competitive_outlook_need: int    # 0-4
    customer_impact: int             # 0-4
    assumptions: tuple[str, ...] = ()
    missing_evidence: tuple[str, ...] = ()


# --------------------------------------------------------------------------- #
# Authored findings - every one grounded in claims present in the store
# --------------------------------------------------------------------------- #

FINDINGS: tuple[FindingSpec, ...] = (
    # ---- infotainment ---------------------------------------------------- #
    FindingSpec(
        "INF-TOUCH-FRICTION", "infotainment", "bmw_weakness",
        "Touch-first controls for frequent functions pull the driver's eyes off the road",
        "Independent testers report that controls around the iDrive controller sit flush in "
        "piano-black trim and cannot be found by touch, that airflow sliders below the display "
        "are unlit, and that drivers must therefore look away from the road to operate them. "
        "This is a usability and attention cost on exactly the functions used most often while "
        "driving.",
        Selector(("physical_controls", "climate_control_interaction", "touchscreen"),
                 any_keywords=("flush", "touch", "button", "slider", "unlit", "gaze", "piano",
                               "taste", "knopf", "blick"),
                 limit=14),
        contradicts=("INF-DISPLAY-STRENGTH",),
    ),
    FindingSpec(
        "INF-SHORTCUTS-LOST", "infotainment", "bmw_weakness",
        "Freely assignable favourite buttons were removed and are missed",
        "Independent review notes the previously practical, freely assignable favourite buttons "
        "have been removed in favour of programmable on-screen equivalents. Shortcut access to "
        "frequently used functions is a regression against the outgoing generation.",
        Selector(("physical_controls", "menu_complexity", "display_usability"),
                 any_keywords=("favorite", "favourite", "assignable", "shortcut", "missing",
                               "removed", "favoriten"),
                 limit=8),
    ),
    FindingSpec(
        "INF-DISPLAY-STRENGTH", "infotainment", "bmw_strength",
        "The curved display and interaction surfaces read as premium and modern",
        "The curved display pairing a 12.3-inch cluster with a 14.9-inch control screen, the "
        "Interaction Bar and ambient treatments are described as visually striking and "
        "immersive. The screen hardware itself is an asset; the friction sits in the control "
        "layer around it.",
        Selector(("display_usability", "perceived_interior_quality"),
                 any_keywords=("curved", "display", "inch", "zoll", "interaction bar",
                               "immersive", "screen"),
                 limit=10),
        contradicts=("INF-TOUCH-FRICTION",),
    ),
    FindingSpec(
        "INF-OTA-COMPETITORS", "infotainment", "competitor_strength",
        "Competitors position infotainment compute and over-the-air upgradeability as a feature",
        "Porsche markets a PCM generation with several times the previous computing power and "
        "fully over-the-air infotainment updates; Tesla sells an explicit infotainment compute "
        "upgrade to older cars. Both frame the head unit as something that improves after "
        "delivery, which sets an expectation the 5 Series successor will be measured against.",
        Selector(("software_reliability", "connected_services"),
                 any_keywords=("ota", "over-the-air", "upgrade", "computing power", "pcm",
                               "software version", "updates"),
                 limit=10),
    ),
    FindingSpec(
        "INF-SERVICE-PAYWALLS", "infotainment", "customer_friction",
        "Connected services lapse into paid tiers and some conveniences are cost options",
        "Connected Drive services are included for an initial period and charged for afterwards, "
        "and wireless smartphone charging is available only as a paid option. Digital "
        "convenience that arrives time-limited or priced separately is a recurring source of "
        "owner irritation.",
        Selector(("connected_services", "smartphone_integration"),
                 any_keywords=("charged", "afterward", "extra", "option", "costs", "bookable",
                               "included for"),
                 limit=10),
    ),

    # ---- charging -------------------------------------------------------- #
    FindingSpec(
        "CHG-PEAK-COMPETITIVE", "charging", "bmw_strength",
        "Peak DC charging power of roughly 207-208 kW is measured and competitive",
        "Independent testing measured a maximum charging power of 207 kW and 208.4 kW at a CCS "
        "fast charger. Peak capability is not the weakness in this car.",
        Selector(("charging_speed",), any_keywords=("maximum", "peak", "kw"),
                 require_numeric=True, limit=10),
        contradicts=("CHG-TAPER",),
    ),
    FindingSpec(
        "CHG-TAPER", "charging", "bmw_weakness",
        "Charging power tapers early, so the session average is far below the peak",
        "Independent testers record that the high charging power falls quickly, that power is "
        "down to about 42 kW by 80 percent state of charge, that the session average was "
        "135.7 kW, and that the optimum charging window is roughly 1-46 percent. The headline "
        "peak overstates what a long-distance stop actually delivers.",
        Selector(("charging_curve", "charging_speed"),
                 any_keywords=("falls", "fallen", "taper", "average", "optimum", "c-rate",
                               "80 percent", "faellt"),
                 limit=12),
        contradicts=("CHG-PEAK-COMPETITIVE",),
    ),
    FindingSpec(
        "CHG-TRIP-CADENCE", "charging", "bmw_strength",
        "A 10-80 percent stop of about 30 minutes adds roughly 184 km in 20 minutes",
        "Independent measurement puts 10-80 percent at about half an hour, with 184 km of range "
        "recovered in a 20-minute stop. Expressed as range-per-stop rather than kilowatts, the "
        "long-distance cadence is usable.",
        Selector(("charging_time",),
                 any_keywords=("10 to 80", "10-80", "half an hour", "20 minutes", "184", "minutes"),
                 limit=10),
    ),
    FindingSpec(
        "CHG-LOSSES", "charging", "bmw_weakness",
        "Independent testers judge charging losses to be improvable",
        "ADAC engineers call the drivetrain efficient but say charging losses could be lower, and "
        "note that measured consumption includes DC charging losses. Energy that never reaches "
        "the battery is cost and time the customer pays for twice.",
        Selector(("charging_reliability", "energy_consumption"),
                 any_keywords=("loss", "losses", "verluste", "ladeverluste", "efficient"),
                 limit=8),
    ),
    FindingSpec(
        "CHG-NETWORK-INTEGRATION", "charging", "bmw_strength",
        "Network breadth and single-app access are an explicit positioning strength",
        "BMW states the My BMW App integrates all BMW Charging network providers into one of the "
        "largest public charging networks, with access to more than 180,000 points and "
        "preferential pricing at IONNA. Note this finding rests mainly on manufacturer sources, "
        "so its independence is lower than the measured charging findings.",
        Selector(("charging_network", "route_planning", "charging_infrastructure",
                  "public_charging", "infrastructure_growth"),
                 any_keywords=("network", "app", "charging points", "providers", "ionna",
                               "preferential", "supercharg"),
                 limit=10),
        notes="Manufacturer-weighted; treat as positioning claim rather than verified performance.",
    ),

    # ---- range ----------------------------------------------------------- #
    FindingSpec(
        "RNG-REAL-VS-CATALOGUE", "range", "customer_friction",
        "Measured consumption runs far above catalogue figures",
        "On the independent test route the 530e consumed 27.1 kWh/100 km in pure electric mode "
        "against a combined catalogue figure of 14.7 kWh/100 km. A gap of that size between "
        "brochure and road is the mechanism behind range disappointment.",
        Selector(("energy_consumption", "real_world_range", "wltp_range"),
                 any_keywords=("kwh", "consumption", "verbrauch", "range", "reichweite"),
                 require_numeric=True, limit=12),
    ),
    FindingSpec(
        "RNG-TOURING-PENALTY", "range", "market_trend",
        "The Touring body carries a small measurable efficiency penalty",
        "An owner report puts the G61 Touring about 3.2 percent higher in consumption than the "
        "G60 saloon. Single-source and self-reported, so treated as a weak signal worth "
        "confirming rather than a settled figure.",
        Selector(("wltp_range", "energy_consumption", "real_world_range"),
                 any_keywords=("touring", "g61", "higher consumption", "3,2", "3.2"),
                 limit=5),
        notes="Low confidence by design: owner-reported, single independence group.",
    ),

    # ---- comfort --------------------------------------------------------- #
    FindingSpec(
        "CMF-SPACE-STRENGTH", "comfort", "bmw_strength",
        "Interior space is a measured, durable strength",
        "Independent measurement records 5.06 m overall length, about 10 cm longer than the "
        "predecessor, legroom sufficient for nearly 2 m occupants, headroom for nearly 2.10 m, "
        "and a 465-litre boot. Space and comfort have been a recognised strength across "
        "generations.",
        Selector(("interior_space", "rear_seat_space", "rear_seat_comfort"),
                 any_keywords=("legroom", "headroom", "meter", "litre", "liter", "boot",
                               "space", "length", "beinfreiheit"),
                 limit=12),
    ),
    FindingSpec(
        "CMF-SUSPENSION-OPTION", "comfort", "customer_friction",
        "Comfortable ride depends on an expensive adaptive suspension option",
        "Independent review finds the Sport-package car's suspension very firm and unsuited to "
        "comfortable family use, and that ride only smooths out noticeably with the costly "
        "Adaptive Suspension Professional option, which is standard only higher in the range. "
        "Baseline comfort is therefore configuration-dependent.",
        Selector(("suspension_comfort", "ride_comfort"),
                 any_keywords=("firm", "adaptive", "expensive", "option", "standard",
                               "smooths", "hart", "komfort"),
                 limit=12),
    ),
    FindingSpec(
        "CMF-QUIET-CABIN", "comfort", "bmw_strength",
        "Cabin noise is measured at roughly 64.7-65.0 dB(A) at 130 km/h",
        "Independent measurement puts interior noise at 130 km/h between 64.7 and 65.0 dB(A) "
        "across variants, with professional reviews describing the cabin as very quiet to about "
        "160 km/h. Refinement at autobahn speed is an evidenced strength.",
        Selector(("cabin_noise",), any_keywords=("db", "noise", "quiet", "geräusch", "gerausch"),
                 limit=10),
    ),
    FindingSpec(
        "CMF-DETAIL-QUALITY", "comfort", "bmw_weakness",
        "Specific interior details undermine the premium impression",
        "Independent review states that a set of interior details feel not very premium-like and "
        "tarnish the perception of quality, with piano-black surfaces and cheap-feeling touch "
        "buttons in the door called out. This sits alongside a generally good workmanship score, "
        "and both observations are preserved.",
        Selector(("perceived_interior_quality", "material_quality"),
                 any_keywords=("premium", "tarnish", "cheap", "fingerprint", "piano",
                               "workmanship", "billig", "wertig"),
                 limit=12),
        contradicts=("CMF-SPACE-STRENGTH",),
    ),

    # ---- driving experience ---------------------------------------------- #
    FindingSpec(
        "DRV-STEERING-VAGUE", "driving_experience", "bmw_weakness",
        "Base steering is judged vague; rear-axle steering is effectively required",
        "Independent review describes the steering as surprisingly vague and credits rear-axle "
        "steering with giving it the necessary bite, while professional review notes the non-M "
        "i5 lacks razor-sharp responses. Owner reports add tramlining and straight-line "
        "wandering, with large wheels implicated. The expected BMW steering feel appears to "
        "depend on options.",
        Selector(("steering_response", "handling"),
                 any_keywords=("steering", "vague", "rear-axle", "sharp", "rut", "serpentine",
                               "wheel", "lenkung", "dynamics"),
                 limit=12),
        contradicts=("DRV-COMPOSURE",),
    ),
    FindingSpec(
        "DRV-COMPOSURE", "driving_experience", "bmw_strength",
        "High-speed composure and refinement hold up despite EV mass",
        "The car passes the independent evasive-manoeuvre test easily and safely, is described "
        "as hard to unsettle in fast corners and incredibly refined in use, and its weight is "
        "noted as helping out-of-town behaviour. Stability is a strength even where steering "
        "feel is criticised.",
        Selector(("handling", "ride_comfort", "braking_feel"),
                 any_keywords=("evasive", "unsettle", "refined", "stable", "composure",
                               "weight", "confidently", "regenerative"),
                 limit=10),
        contradicts=("DRV-STEERING-VAGUE",),
    ),

    # ---- market trend ---------------------------------------------------- #
    FindingSpec(
        "MKT-SIZE-RACE", "market_trend", "market_trend",
        "The 5 Series now outsizes the E-Class, making space a live competitive axis",
        "Independent comparison puts the current 5 Series about 11 cm longer than the Mercedes "
        "E-Class, alongside a broad power and variant spread. Segment positioning is being "
        "contested on interior space and variant breadth.",
        Selector(("competitive_benchmark",),
                 any_keywords=("e-class", "e‑class", "exceeds", "centimeter", "longer",
                               "mercedes", "ps", "euro"),
                 limit=12),
    ),
    FindingSpec(
        "MKT-ELECTRIC-ESTATE-GAP", "market_trend", "market_trend",
        "Electric estates remain rare while the Touring body is popular in Germany",
        "Independent commentary notes the 5 Series Touring is popular in Germany while electric "
        "station wagons are still rare. An electric Touring addresses a demand pocket that few "
        "competitors serve.",
        Selector(("adoption_trend", "customer_expectation", "competitive_benchmark"),
                 any_keywords=("touring", "station wagon", "estate", "rare", "popular",
                               "germany", "kombi"),
                 limit=10),
    ),
)


# --------------------------------------------------------------------------- #
# Authored customer needs - customer language, not implementation
# --------------------------------------------------------------------------- #

NEEDS: tuple[NeedSpec, ...] = (
    NeedSpec("EYES-ON-ROAD", "infotainment",
             "I want to operate the controls I use most often without taking my eyes off the road.",
             "Independent testing finds flush, unlit and touch-only controls force the driver to "
             "look away to adjust common functions.",
             ("INF-TOUCH-FRICTION", "INF-SHORTCUTS-LOST"), "high",
             "Daily driving, adjusting climate and media while moving."),
    NeedSpec("KEEP-SCREEN-FIX-CONTROLS", "infotainment",
             "I want to keep the big, clear screen and still have the everyday controls be easy "
             "to use while driving.",
             "The curved display and interaction surfaces are received as premium and modern, "
             "while the control layer around them is what testers criticise. The screen is not "
             "the problem and should not be sacrificed to fix the controls.",
             ("INF-DISPLAY-STRENGTH", "INF-TOUCH-FRICTION"), "high",
             "Daily driving; also the showroom impression that sells the car."),
    NeedSpec("MY-OWN-SHORTCUTS", "infotainment",
             "I want to put the functions I personally use most within one deliberate reach.",
             "Assignable favourite buttons were removed and are missed; shortcut access reduces "
             "menu hunting for individual habits.",
             ("INF-SHORTCUTS-LOST", "INF-TOUCH-FRICTION"), "medium",
             "Repeat journeys where the same few functions are used every time."),
    NeedSpec("STAYS-CURRENT", "infotainment",
             "I want the car's digital experience to get better while I own it, not fall behind.",
             "Competitors sell infotainment compute upgrades and full over-the-air updates, "
             "setting an expectation of post-purchase improvement.",
             ("INF-OTA-COMPETITORS", "INF-SERVICE-PAYWALLS"), "high",
             "Multi-year ownership, comparing against newer cars."),
    NeedSpec("NO-SURPRISE-PAYWALLS", "infotainment",
             "I want to know up front which digital features stay free and which I will be asked "
             "to pay for later.",
             "Connected services lapse into paid tiers and some conveniences are cost options.",
             ("INF-SERVICE-PAYWALLS",), "medium",
             "End of the included service period."),
    NeedSpec("PREDICTABLE-STOP", "charging",
             "I want a long-distance charging stop to take about as long as I was told it would.",
             "Peak power is competitive but tapers early, so session averages and real stop "
             "times fall well short of the headline figure.",
             ("CHG-TAPER", "CHG-PEAK-COMPETITIVE", "CHG-TRIP-CADENCE"), "high",
             "Autobahn trips with one or two planned charging stops."),
    NeedSpec("RANGE-PER-STOP", "charging",
             "I want to know how much usable range a stop will actually give me, in kilometres.",
             "Range recovered per stop is the figure customers plan around; 184 km in 20 minutes "
             "is more meaningful to them than a kilowatt peak.",
             ("CHG-TRIP-CADENCE", "CHG-TAPER"), "high",
             "Trip planning before and during a journey."),
    NeedSpec("ENERGY-NOT-WASTED", "charging",
             "I do not want to pay for energy that never reaches my battery.",
             "Independent testers judge charging losses improvable and include them in measured "
             "consumption.",
             ("CHG-LOSSES", "RNG-REAL-VS-CATALOGUE"), "medium",
             "Every charging session, especially on public DC pricing."),
    NeedSpec("ONE-WAY-TO-CHARGE", "charging",
             "I want one simple way to find, use and pay for charging wherever I am.",
             "Single-app access across a broad provider network is positioned as a strength and "
             "matches how customers want to charge.",
             ("CHG-NETWORK-INTEGRATION",), "medium",
             "Charging away from home on mixed networks."),
    NeedSpec("HONEST-RANGE", "range",
             "I want the range the car promises to be the range I get.",
             "Measured consumption of 27.1 kWh/100 km against a 14.7 kWh/100 km catalogue figure "
             "is the mechanism behind range disappointment.",
             ("RNG-REAL-VS-CATALOGUE",), "high",
             "Winter, autobahn and fully loaded driving."),
    NeedSpec("COMFORT-WITHOUT-UPGRADE", "comfort",
             "I want a comfortable ride without having to find the right expensive option box.",
             "The Sport-package suspension is judged too firm for comfortable family use, with "
             "ride only improving noticeably on a costly adaptive option.",
             ("CMF-SUSPENSION-OPTION", "CMF-QUIET-CABIN"), "high",
             "Family and long-distance use on imperfect German roads."),
    NeedSpec("PREMIUM-WHERE-I-TOUCH", "comfort",
             "I want the surfaces I touch every day to feel as premium as the car's price implies.",
             "Independent review calls specific details not very premium-like, naming piano-black "
             "surfaces and cheap-feeling door touch buttons.",
             ("CMF-DETAIL-QUALITY", "INF-TOUCH-FRICTION"), "high",
             "Every entry and exit; daily contact points."),
    NeedSpec("ROOM-FOR-REAL-LIFE", "comfort",
             "I want space for four adults and their luggage without compromise.",
             "Measured legroom, headroom and boot volume are a recognised multi-generation "
             "strength, and the segment is competing on exactly this.",
             ("CMF-SPACE-STRENGTH", "MKT-SIZE-RACE"), "medium",
             "Family trips and business travel with passengers."),
    NeedSpec("CONFIDENT-STEERING", "driving_experience",
             "I want the car to go exactly where I point it, including at speed on a rutted road.",
             "Base steering is judged vague with rear-axle steering credited for the necessary "
             "bite, and owners report tramlining on large wheels.",
             ("DRV-STEERING-VAGUE", "DRV-COMPOSURE"), "high",
             "Autobahn cruising and winding secondary roads."),
    NeedSpec("ELECTRIC-ESTATE", "market_trend",
             "I want an electric car that still carries what my estate carries today.",
             "The Touring body is popular in Germany while electric estates remain rare, so the "
             "demand pocket is underserved.",
             ("MKT-ELECTRIC-ESTATE-GAP", "CMF-SPACE-STRENGTH", "RNG-TOURING-PENALTY"), "medium",
             "German buyers replacing a combustion estate."),
)


# --------------------------------------------------------------------------- #
# Authored requirements - customer-facing and testable
# --------------------------------------------------------------------------- #

REQUIREMENTS: tuple[RequirementSpec, ...] = (
    RequirementSpec(
        "CTRL-EYES-ON-ROAD", "infotainment",
        "Frequent functions operable without looking away",
        "The vehicle shall allow a seated driver to adjust cabin temperature, fan, audio volume "
        "and media track without looking away from the road, using controls that can be located "
        "and actuated by touch alone.",
        ("EYES-ON-ROAD", "MY-OWN-SHORTCUTS", "KEEP-SCREEN-FIX-CONTROLS"),
        "Removes a measured attention cost on the functions used most while driving.",
        "Directly answers the most frequently evidenced criticism of the current generation.",
        "medium", "medium",
        "Seated-driver task test: eyes-off-road time per adjustment measured against a declared "
        "ceiling, plus blind-location success rate on first attempt.",
        strategic_contribution=3, competitive_outlook_need=3, customer_impact=4,
        assumptions=("A tactile control layer can coexist with the current display architecture.",),
        missing_evidence=("No internal eyes-off-road measurement for the current car.",),
    ),
    RequirementSpec(
        "CTRL-PERSONAL-SHORTCUTS", "infotainment",
        "Driver-assignable shortcuts for personal frequent functions",
        "The vehicle shall let a driver assign their own frequently used functions to shortcuts "
        "that are reachable in a single deliberate action and are identifiable without reading "
        "the screen.",
        ("MY-OWN-SHORTCUTS", "EYES-ON-ROAD"),
        "Restores a capability owners explicitly miss from the previous generation.",
        "Re-establishes parity with the outgoing car rather than beating rivals.",
        "low", "low",
        "Task test: assign and then invoke a personal function without screen reading; owner "
        "panel confirmation that the removed capability is restored.",
        strategic_contribution=2, competitive_outlook_need=2, customer_impact=3,
    ),
    RequirementSpec(
        "DIGITAL-IMPROVES-OVER-TIME", "infotainment",
        "Digital experience measurably improves during ownership",
        "The vehicle shall receive over-the-air improvements to its infotainment and assistance "
        "experience throughout the ownership period, with each release stating in customer "
        "language what changed.",
        ("STAYS-CURRENT",),
        "Protects perceived value against rivals that visibly improve after delivery.",
        "Competitors already market this; absence becomes a visible gap by 2030.",
        "high", "high",
        "Release audit over a defined period: count of customer-visible improvements delivered "
        "over the air, and owner-perceived-currency survey.",
        strategic_contribution=4, competitive_outlook_need=4, customer_impact=3,
        missing_evidence=("No evidence yet on which update cadence customers consider sufficient.",),
    ),
    RequirementSpec(
        "DIGITAL-COST-TRANSPARENCY", "infotainment",
        "Up-front clarity on which digital features remain free",
        "The vehicle and its purchase journey shall state, before order, which digital features "
        "are included for the life of the vehicle and which require later payment, with no "
        "function that was demonstrated as included becoming chargeable without notice.",
        ("NO-SURPRISE-PAYWALLS", "STAYS-CURRENT"),
        "Removes a recurring trust irritant at the end of the included service period.",
        "Trust positioning rather than feature differentiation.",
        "low", "low",
        "Documentation audit against the delivered feature set, plus complaint-rate tracking at "
        "the end of included periods.",
        strategic_contribution=2, competitive_outlook_need=2, customer_impact=2,
    ),
    RequirementSpec(
        "CHG-SUSTAINED-POWER", "charging",
        "Sustained fast-charging power across the useful state-of-charge window",
        "The vehicle shall sustain high DC charging power across the state-of-charge range "
        "customers actually use on long trips, such that a 10-80 percent stop completes within a "
        "declared time at a compliant high-power charger and the session average remains close "
        "to the advertised peak.",
        ("PREDICTABLE-STOP", "RANGE-PER-STOP"),
        "Attacks the gap between headline peak and delivered stop time, which is the "
        "best-evidenced charging weakness.",
        "Peak power is already competitive; sustained power is where the car is beaten.",
        "high", "high",
        "Repeated 10-80 percent charge curves at a compliant charger, reporting session average "
        "and time, at declared ambient and preconditioning states.",
        strategic_contribution=4, competitive_outlook_need=4, customer_impact=4,
        assumptions=("Thermal and cell-chemistry headroom exists to hold power for longer.",),
        missing_evidence=("No competitor charge curves measured under identical conditions.",),
    ),
    RequirementSpec(
        "CHG-RANGE-PER-STOP", "charging",
        "Charging communicated as usable range per stop",
        "The vehicle shall present charging progress and planning in usable range gained for the "
        "stop, under current conditions, rather than only as power or percentage.",
        ("RANGE-PER-STOP", "PREDICTABLE-STOP"),
        "Matches the unit customers plan journeys in and makes a tapering curve honest.",
        "Low-cost credibility move that reframes a weakness as transparency.",
        "low", "low",
        "Compare predicted range-gained against measured range-gained across stops; accuracy "
        "band reported.",
        strategic_contribution=3, competitive_outlook_need=2, customer_impact=3,
    ),
    RequirementSpec(
        "CHG-LOSS-REDUCTION", "charging",
        "Reduced energy lost between charger and battery",
        "The vehicle shall reduce the share of energy drawn from the charger that does not reach "
        "the usable battery, measured over a standard charging cycle, and shall make the measured "
        "figure available to the customer.",
        ("ENERGY-NOT-WASTED", "HONEST-RANGE"),
        "Customers pay for charging losses twice, in money and in time.",
        "Independent testers already flag this, so improvement is externally verifiable.",
        "medium", "medium",
        "Metered input energy versus delivered battery energy over a standard cycle at declared "
        "temperature.",
        strategic_contribution=3, competitive_outlook_need=3, customer_impact=3,
    ),
    RequirementSpec(
        "CHG-ONE-JOURNEY", "charging",
        "One account and one app across the charging journey",
        "A driver shall be able to find, start, and pay for charging across the supported public "
        "network from the vehicle and its app without a second account or payment method.",
        ("ONE-WAY-TO-CHARGE",),
        "Keeps the strongest part of the current charging story intact.",
        "Already a positioning strength; the requirement is to protect it.",
        "medium", "medium",
        "Journey test across a sample of network operators, counting sessions completed without "
        "a secondary account.",
        strategic_contribution=3, competitive_outlook_need=2, customer_impact=3,
        missing_evidence=("Network-breadth claims are manufacturer-sourced and unverified here.",),
    ),
    RequirementSpec(
        "RNG-REALISTIC-PROMISE", "range",
        "Range promise that holds in real conditions",
        "The range the vehicle presents to the customer shall reflect current load, speed, "
        "temperature and route, and shall be stated so that the achieved range on a representative "
        "German long-distance route falls within a declared band of the promise.",
        ("HONEST-RANGE", "PREDICTABLE-STOP"),
        "Closes the brochure-versus-road gap that drives range disappointment.",
        "Credibility differentiator in a segment where everyone overstates.",
        "medium", "medium",
        "Independent-style route test comparing presented range against achieved range, winter "
        "and summer, reported as a band.",
        strategic_contribution=4, competitive_outlook_need=3, customer_impact=4,
    ),
    RequirementSpec(
        "CMF-BASELINE-RIDE", "comfort",
        "Comfortable ride in the standard configuration",
        "The vehicle shall deliver ride comfort suitable for family and long-distance use in its "
        "standard suspension configuration, without requiring a chargeable adaptive suspension "
        "option, including on the wheel sizes most customers order.",
        ("COMFORT-WITHOUT-UPGRADE", "ROOM-FOR-REAL-LIFE"),
        "Makes the car's recognised comfort strength available without option hunting.",
        "Rivals increasingly make adaptive damping standard in this class.",
        "high", "high",
        "Ride-comfort assessment on standard suspension across the most-ordered wheel sizes, on "
        "a representative poor-surface route.",
        strategic_contribution=3, competitive_outlook_need=3, customer_impact=4,
        assumptions=("Most-ordered wheel sizes can be determined from internal order data.",),
        missing_evidence=("No internal take-rate data for the adaptive suspension option here.",),
    ),
    RequirementSpec(
        "CMF-TOUCHPOINT-QUALITY", "comfort",
        "Daily touchpoints that feel premium and stay that way",
        "Surfaces and controls the driver contacts daily shall retain a premium appearance and "
        "feel over the ownership period, without visible fingerprint retention or hollow-feeling "
        "actuation on frequently used controls.",
        ("PREMIUM-WHERE-I-TOUCH",),
        "Addresses named details that independent review says tarnish quality perception.",
        "Perceived quality is a core premium promise; the criticism is specific and fixable.",
        "medium", "medium",
        "Tactile and appearance assessment of named touchpoints after a simulated ownership "
        "wear cycle, plus fingerprint-visibility test.",
        strategic_contribution=3, competitive_outlook_need=3, customer_impact=3,
    ),
    RequirementSpec(
        "CMF-QUIET-RETAINED", "comfort",
        "Autobahn quietness retained or improved",
        "Interior noise at 130 km/h shall be no higher than the current generation's measured "
        "level, on the wheel and tyre combinations most customers order.",
        ("COMFORT-WITHOUT-UPGRADE", "ROOM-FOR-REAL-LIFE"),
        "Protects a measured strength that is easy to lose with larger wheels.",
        "Defensive: a regression here would be independently measured and published.",
        "low", "medium",
        "Interior sound-level measurement at 130 km/h against the recorded 64.7-65.0 dB(A) "
        "baseline, same method.",
        strategic_contribution=2, competitive_outlook_need=2, customer_impact=3,
    ),
    RequirementSpec(
        "DRV-STEERING-CONFIDENCE", "driving_experience",
        "Confident steering feel without optional hardware",
        "The vehicle shall provide precise on-centre steering response and straight-line "
        "stability on rutted surfaces in its standard steering configuration, without requiring "
        "optional rear-axle steering, on the wheel sizes most customers order.",
        ("CONFIDENT-STEERING",),
        "Protects the brand's defining attribute where review and owner evidence agree it is "
        "currently option-dependent.",
        "Steering feel is the attribute customers most associate with the brand.",
        "high", "high",
        "On-centre response and tramlining assessment on standard steering across the "
        "most-ordered wheel sizes, with owner-panel confirmation.",
        strategic_contribution=4, competitive_outlook_need=3, customer_impact=4,
        missing_evidence=("Owner tramlining reports are forum-sourced and not independently "
                          "reproduced.",),
    ),
    RequirementSpec(
        "VAR-ELECTRIC-TOURING", "market_trend",
        "Electric estate variant with uncompromised load space",
        "The successor range shall include a fully electric estate variant whose load space and "
        "passenger room are competitive with the combustion estate it replaces.",
        ("ELECTRIC-ESTATE", "ROOM-FOR-REAL-LIFE"),
        "Serves a German demand pocket that few competitors currently address.",
        "Electric estates are explicitly noted as still rare.",
        "high", "high",
        "Load-volume and passenger-room comparison against the outgoing combustion estate and "
        "available electric rivals.",
        strategic_contribution=4, competitive_outlook_need=4, customer_impact=3,
        assumptions=("Electric estate demand persists to 2030.",),
        missing_evidence=("No sales or survey data here on electric estate demand size.",),
    ),
)


# --------------------------------------------------------------------------- #
# Derivation - everything below is computed, never authored
# --------------------------------------------------------------------------- #


def load_canonical() -> list[dict]:
    """Load canonical evidence. Never writes; never reads the replay file."""
    path = config.PROCESSED_EVIDENCE_PATH
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        raise SystemExit(f"no evidence in {path}")
    return rows


def confidence_for(independent: int, avg_quality: float, rows: int) -> str:
    """Confidence band from source independence and source quality.

    Independence dominates: a single source cannot produce high confidence
    however authoritative it is, which is the rule the brief asks for.
    """
    if independent <= 1:
        return "low_single_source"
    if independent >= 4 and avg_quality >= 80 and rows >= 6:
        return "high"
    if independent >= 2 and avg_quality >= 70:
        return "medium"
    return "low"


def stance_summary(rows: list[dict]) -> dict:
    """Counts by source family and a crude polarity split, for transparency."""
    families: dict[str, int] = {}
    for row in rows:
        families[row["source_family"]] = families.get(row["source_family"], 0) + 1
    return {
        "rows": len(rows),
        "by_source_family": dict(sorted(families.items(), key=lambda kv: (-kv[1], kv[0]))),
        "numeric_rows": sum(1 for r in rows if r.get("numeric_value") is not None),
    }


def build_findings(evidence: list[dict]) -> tuple[list[dict], dict[str, str]]:
    """Resolve every authored finding against the store."""
    live = [r for r in evidence if not r.get("duplicate_of")]
    findings, key_to_id, skipped = [], {}, []

    for index, spec in enumerate(FINDINGS, start=1):
        rows = spec.selector.select(live)
        if not rows:
            skipped.append(spec.key)
            continue
        ids = sorted(r["evidence_id"] for r in rows)
        groups = {r["independence_group"] for r in rows}
        avg_quality = round(sum(r["source_quality"] for r in rows) / len(rows), 1)
        finding_id = f"FND-{index:03d}-{spec.key}"
        key_to_id[spec.key] = finding_id
        findings.append({
            "finding_id": finding_id,
            "schema_version": "1",
            "topic": spec.topic,
            "finding_kind": spec.kind,
            "title": spec.title,
            "summary": spec.summary,
            "evidence_ids": ids,
            "source_count": len(ids),
            "independent_source_count": len(groups),
            "average_source_quality": avg_quality,
            "confidence": confidence_for(len(groups), avg_quality, len(rows)),
            "stance_summary": stance_summary(rows),
            "brands_covered": sorted({str(r.get("brand", "")) for r in rows if r.get("brand")}),
            "vehicles_covered": sorted({str(r.get("vehicle", "")) for r in rows if r.get("vehicle")}),
            "markets_covered": sorted({str(r.get("market", "")) for r in rows if r.get("market")}),
            "contradicts": list(spec.contradicts),
            "notes": spec.notes,
            "created_at": CREATED_AT,
        })

    # Resolve contradiction keys to ids now that all ids exist.
    for finding in findings:
        finding["contradicts"] = [key_to_id[k] for k in finding["contradicts"] if k in key_to_id]
    return findings, key_to_id


def build_needs(findings: list[dict], key_to_id: dict[str, str]) -> tuple[list[dict], dict[str, str]]:
    """Resolve needs, inheriting evidence ids from their findings."""
    by_id = {f["finding_id"]: f for f in findings}
    needs, key_to_need = [], {}

    for index, spec in enumerate(NEEDS, start=1):
        finding_ids = [key_to_id[k] for k in spec.finding_keys if k in key_to_id]
        if not finding_ids:
            continue
        evidence_ids = sorted({eid for fid in finding_ids for eid in by_id[fid]["evidence_ids"]})
        groups = max(by_id[fid]["independent_source_count"] for fid in finding_ids)
        qualities = [by_id[fid]["average_source_quality"] for fid in finding_ids]
        need_id = f"NEED-{index:03d}-{spec.key}"
        key_to_need[spec.key] = need_id
        needs.append({
            "need_id": need_id,
            "schema_version": "1",
            "topic": spec.topic,
            "statement": spec.statement,
            "rationale": spec.rationale,
            "finding_ids": finding_ids,
            "evidence_ids": evidence_ids,
            "importance": spec.importance,
            "confidence": confidence_for(groups, sum(qualities) / len(qualities), len(evidence_ids)),
            "customer_context": spec.customer_context,
            "target_market": "DE",
            "created_at": CREATED_AT,
        })
    return needs, key_to_need


def score_requirement(spec: RequirementSpec, independent: int, max_independent: int) -> dict:
    """Transparent 0-4 scoring on the reused policy axes.

    ``evidence_backed_reach`` is the declared deviation: it scales independent
    public sources against the widest-supported requirement in this batch,
    because the approved internal definition needs a feedback-record
    denominator that web evidence cannot supply.
    """
    reach_raw = (independent / max_independent) if max_independent else 0.0
    reach = round(reach_raw * 4, 2)
    components = {
        "customer_impact": float(spec.customer_impact),
        "evidence_backed_reach": reach,
        "strategic_contribution": float(spec.strategic_contribution),
        "competitive_outlook_need": float(spec.competitive_outlook_need),
    }
    total = round(sum(components[k] * w for k, w in POLICY["criteria"].items()), 3)
    return {
        "policy_id": POLICY["policy_id"],
        "derived_from": POLICY["derived_from"],
        "approved": POLICY["approved"],
        "deviation": POLICY["deviation"],
        "weights": POLICY["criteria"],
        "components_0_to_4": components,
        "reach_basis": {
            "independent_sources": independent,
            "max_independent_sources_in_batch": max_independent,
            "formula": "independent_sources / max_independent_sources_in_batch * 4",
        },
        "weighted_score_0_to_4": total,
    }


def build_requirements(needs: list[dict], key_to_need: dict[str, str],
                       findings: list[dict]) -> tuple[list[dict], list[dict]]:
    """Resolve requirements and score them."""
    need_by_id = {n["need_id"]: n for n in needs}
    finding_by_id = {f["finding_id"]: f for f in findings}

    resolved = []
    for spec in REQUIREMENTS:
        need_ids = [key_to_need[k] for k in spec.need_keys if k in key_to_need]
        if not need_ids:
            continue
        finding_ids = sorted({fid for nid in need_ids for fid in need_by_id[nid]["finding_ids"]})
        evidence_ids = sorted({eid for nid in need_ids for eid in need_by_id[nid]["evidence_ids"]})
        # Widest independent support among the findings behind this requirement.
        independent = max(
            finding_by_id[fid]["independent_source_count"] for fid in finding_ids
        )
        resolved.append((spec, need_ids, finding_ids, evidence_ids, independent))

    max_independent = max((r[4] for r in resolved), default=1)
    requirements, scores = [], []
    for index, (spec, need_ids, finding_ids, evidence_ids, independent) in enumerate(resolved, 1):
        requirement_id = f"REQ-{index:03d}-{spec.key}"
        confidences = [need_by_id[nid]["confidence"] for nid in need_ids]
        confidence = ("low_single_source" if all(c == "low_single_source" for c in confidences)
                      else "high" if "high" in confidences
                      else "medium" if "medium" in confidences else "low")
        requirements.append({
            "requirement_id": requirement_id,
            "schema_version": "1",
            "topic": spec.topic,
            "title": spec.title,
            "requirement": spec.requirement,
            "need_ids": need_ids,
            "finding_ids": finding_ids,
            "evidence_ids": evidence_ids,
            "customer_value": spec.customer_value,
            "differentiation": spec.differentiation,
            "confidence": confidence,
            "independent_source_count": independent,
            "rough_effort": spec.rough_effort,
            "rough_cost": spec.rough_cost,
            "validation_method": spec.validation_method,
            "assumptions": list(spec.assumptions),
            "missing_evidence": list(spec.missing_evidence),
            "status": "draft_unapproved",
            "created_at": CREATED_AT,
        })
        scores.append({
            "requirement_id": requirement_id,
            "schema_version": "1",
            **score_requirement(spec, independent, max_independent),
            "created_at": CREATED_AT,
        })
    return requirements, scores


def write_jsonl(path, rows) -> None:
    """Write rows as JSONL, one object per line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report without writing")
    args = parser.parse_args(argv)

    evidence = load_canonical()
    known_ids = {r["evidence_id"] for r in evidence}

    findings, key_to_id = build_findings(evidence)
    needs, key_to_need = build_needs(findings, key_to_id)
    requirements, scores = build_requirements(needs, key_to_need, findings)

    # Fail loudly rather than emit an unsupported id.
    for finding in findings:
        unknown = [e for e in finding["evidence_ids"] if e not in known_ids]
        if unknown:
            raise SystemExit(f"{finding['finding_id']} references unknown evidence: {unknown[:3]}")

    print(f"  canonical evidence rows   {len(evidence)}")
    print(f"  findings                  {len(findings)} / {len(FINDINGS)} authored")
    print(f"  customer needs            {len(needs)} / {len(NEEDS)} authored")
    print(f"  requirements              {len(requirements)} / {len(REQUIREMENTS)} authored")
    print(f"  requirement scores        {len(scores)}")
    missing = [s.key for s in FINDINGS if s.key not in key_to_id]
    if missing:
        print(f"  findings with no matching evidence: {missing}")

    if args.dry_run:
        print("  dry run - nothing written")
        return 0

    write_jsonl(FINDINGS_PATH, findings)
    write_jsonl(NEEDS_PATH, needs)
    write_jsonl(REQUIREMENTS_PATH, requirements)
    write_jsonl(SCORES_PATH, scores)
    for path in (FINDINGS_PATH, NEEDS_PATH, REQUIREMENTS_PATH, SCORES_PATH):
        print(f"  wrote {path.relative_to(config.BASE_DIR)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
