"""Deterministic normalization applied after extraction, before storage.

The extraction model is good at finding claims and poor at three specific
things: it drifts on topic/subtopic for numeric facts, it writes claims in
whichever language the page used, and it collapses a two-value table row into
one record with no numbers at all. All three are fixable without asking a model
anything, which is what this module does.

Four passes, in order:

1. :func:`split_multi_value` - a row stating two labelled facts becomes two
   atomic records.
2. :func:`reclassify` - high-confidence rules correct topic/subtopic from the
   evidence text and its unit.
3. :func:`canonicalize_subtopic` - earlier subtopic spellings are rewritten to
   their canonical name.
4. :func:`looks_non_english` - claims still not in English are counted, so the
   prompt contract is measurable rather than assumed.

Nothing here touches ``evidence_text``, ``source_start_char`` or
``source_end_char``. The quote stays verbatim in its original language and the
offsets keep addressing it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Sequence

from models import SUBTOPIC_ALIASES, SUBTOPICS, RawEvidence

# --------------------------------------------------------------------------- #
# Number parsing
# --------------------------------------------------------------------------- #

_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def parse_number(text: str) -> float | None:
    """Parse a German- or English-formatted number, or ``None``.

    ``25,6`` is 25.6 and ``1.234,5`` is 1234.5: when both separators appear the
    dot is the thousands separator, which is the German convention these pages
    use.
    """
    raw = (text or "").strip()
    if not raw:
        return None
    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif "," in raw:
        raw = raw.replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# Signals
# --------------------------------------------------------------------------- #

#: Consumption expressed per 100 km, with or without a space before ``km``.
#: Unambiguous: nothing but energy consumption is quoted in these units.
RE_CONSUMPTION_UNIT = re.compile(r"k\s?wh\s*/\s*100\s*km", re.I)

#: A distance figure in kilometres, e.g. ``602 km`` or ``627 - 720 km``.
RE_KM_FIGURE = re.compile(r"\d+(?:[.,]\d+)?\s*(?:-|–|bis)?\s*(?:\d+(?:[.,]\d+)?)?\s*(?:km|kilometer)\b", re.I)

#: A power figure in kW, e.g. ``270 kW``.
RE_KW_FIGURE = re.compile(r"\d+(?:[.,]\d+)?\s*kw\b", re.I)

#: A duration in minutes, e.g. ``21 Min.`` or ``30 minutes``.
RE_MINUTES = re.compile(r"\d+(?:[.,]\d+)?\s*(?:min\b|minuten|minutes)", re.I)

#: 10-80 % state-of-charge window, the standard fast-charge benchmark.
RE_SOC_WINDOW = re.compile(r"\b10\s*(?:-|–|bis|auf|to)\s*80\s*%?", re.I)

RE_WLTP = re.compile(r"\bwltp\b", re.I)
RE_RANGE_WORD = re.compile(r"\breichweite|\brange\b", re.I)
RE_TEST_WORD = re.compile(r"\btest|\bpraxis|real[\s-]?world|\bgemessen\b", re.I)
RE_WINTER_WORD = re.compile(r"\bwinter|\bkälte|\bkalte|\bcold\b", re.I)
RE_AC = re.compile(r"(?<![a-z])ac(?![a-z])", re.I)
RE_DC = re.compile(r"(?<![a-z])dc(?![a-z])", re.I)
RE_CHARGE_POWER_WORD = re.compile(r"ladeleistung|charging power|lade\s?leistung", re.I)
RE_CHARGE_TIME_WORD = re.compile(r"ladedauer|ladezeit|charging time|charge time", re.I)
RE_CURVE_WORD = re.compile(r"ladekurve|charging curve", re.I)
RE_TAPER = re.compile(r"f[äa]llt\s+(?:\w+\s+)?ab|tapers?|drops? off", re.I)
RE_PRECONDITION = re.compile(r"vorkonditionier|precondition", re.I)

#: How the car steers. ``Lenkrad`` - the steering *wheel* - is excluded: the
#: real page says "Auch im Lenkrad finden sich Touchtasten", which is
#: infotainment, not steering behaviour.
RE_STEERING = re.compile(r"lenkung|lenkverhalten|\bsteering\b|lenkpräzision|lenkgefühl", re.I)
RE_STEERING_WHEEL = re.compile(r"lenkrad|steering wheel", re.I)

RE_BRAKING = re.compile(r"\bbremse|\bbremsen|bremsgef[üu]hl|bremspedal|\bbraking\b|brake pedal", re.I)

#: A physical charging port or flap, and where it sits on the car.
RE_CHARGE_PORT = re.compile(
    r"ladeanschl|ladeklappe|ladedose|ladebuchse|charging port|charge port|charging flap",
    re.I,
)

#: "Nachgeladene Reichweite in 20 Minuten | 184 km" states range *gained by
#: charging*. It is a charging metric that happens to be denominated in
#: kilometres, so the range rules must not claim it.
RE_RECHARGED = re.compile(r"nachgelad|nachlad|recharged|zugelad", re.I)


@dataclass(frozen=True)
class ClassificationRule:
    """One high-confidence topic/subtopic correction.

    ``matches`` receives the lowercased evidence text, the lowercased unit and
    a page-context string (title plus a winter marker). A rule fires only on a
    *combination* of signals - a unit plus a keyword, or a keyword plus a
    figure - so a passing mention of a word cannot retopic a record.
    """

    name: str
    topic: str
    subtopic: str
    matches: Callable[[str, str, str], bool]
    why: str


def _consumption(text: str, unit: str, ctx: str) -> bool:
    return bool(RE_CONSUMPTION_UNIT.search(text) or RE_CONSUMPTION_UNIT.search(unit))


def _wltp_range(text: str, unit: str, ctx: str) -> bool:
    # WLTP plus a distance, and explicitly not a consumption figure.
    if RE_CONSUMPTION_UNIT.search(text) or RE_CONSUMPTION_UNIT.search(unit):
        return False
    return bool(RE_WLTP.search(text) and (RE_KM_FIGURE.search(text) or RE_RANGE_WORD.search(text)))


def _measured_range(text: str, unit: str, ctx: str) -> bool:
    """A range figure from a test rather than from the WLTP label."""
    if RE_CONSUMPTION_UNIT.search(text) or RE_CONSUMPTION_UNIT.search(unit):
        return False
    if RE_WLTP.search(text):
        return False
    if RE_RECHARGED.search(text):
        # Range added by charging, not range achieved on a drive.
        return False
    if not RE_RANGE_WORD.search(text):
        return False
    # Needs a measurement signal: a test word in the quote, or a km figure on a
    # page that is itself a test. A bare mention of "Reichweite" is not enough.
    return bool(RE_TEST_WORD.search(text) or (RE_KM_FIGURE.search(text) and RE_TEST_WORD.search(ctx)))


def _winter_range(text: str, unit: str, ctx: str) -> bool:
    return _measured_range(text, unit, ctx) and bool(
        RE_WINTER_WORD.search(text) or RE_WINTER_WORD.search(ctx)
    )


def _charging_time(text: str, unit: str, ctx: str) -> bool:
    if RE_CHARGE_TIME_WORD.search(text):
        return True
    return bool(RE_SOC_WINDOW.search(text) and (RE_MINUTES.search(text) or "min" in unit))


def _charging_curve(text: str, unit: str, ctx: str) -> bool:
    if RE_CURVE_WORD.search(text):
        return True
    return bool(RE_CHARGE_POWER_WORD.search(text) and RE_TAPER.search(text))


def _preconditioning(text: str, unit: str, ctx: str) -> bool:
    return bool(RE_PRECONDITION.search(text))


def _steering(text: str, unit: str, ctx: str) -> bool:
    if RE_STEERING_WHEEL.search(text):
        return False
    return bool(RE_STEERING.search(text))


def _braking(text: str, unit: str, ctx: str) -> bool:
    return bool(RE_BRAKING.search(text))


def _charge_port(text: str, unit: str, ctx: str) -> bool:
    return bool(RE_CHARGE_PORT.search(text))


def _charging_speed(text: str, unit: str, ctx: str) -> bool:
    # A power figure plus something naming charging. "270 kW" alone could be a
    # motor output, so the charging word is required.
    has_power = bool(RE_KW_FIGURE.search(text) or "kw" in unit)
    if not has_power:
        return False
    return bool(
        RE_CHARGE_POWER_WORD.search(text) or RE_AC.search(text) or RE_DC.search(text)
    )


#: Ordered most specific first. The first rule that fires wins.
RULES: tuple[ClassificationRule, ...] = (
    ClassificationRule("consumption_unit", "range", "energy_consumption", _consumption,
                       "quoted in kWh/100 km"),
    ClassificationRule("wltp_range", "range", "wltp_range", _wltp_range,
                       "WLTP label with a distance figure"),
    ClassificationRule("winter_range", "range", "winter_range", _winter_range,
                       "measured range in a winter context"),
    ClassificationRule("measured_range", "range", "real_world_range", _measured_range,
                       "measured range outside the WLTP label"),
    ClassificationRule("preconditioning", "charging", "battery_preconditioning", _preconditioning,
                       "names battery preconditioning"),
    ClassificationRule("charge_port", "charging", "charging_port_access", _charge_port,
                       "names a physical charging port or flap"),
    ClassificationRule("steering", "driving_experience", "steering_response", _steering,
                       "names steering behaviour, not the steering wheel"),
    ClassificationRule("braking", "driving_experience", "braking_feel", _braking,
                       "names braking"),
    ClassificationRule("charging_time", "charging", "charging_time", _charging_time,
                       "charge duration or a 10-80 % window with minutes"),
    ClassificationRule("charging_curve", "charging", "charging_curve", _charging_curve,
                       "charging curve or a tapering charge power"),
    ClassificationRule("charging_speed", "charging", "charging_speed", _charging_speed,
                       "charge power figure in kW"),
)


def page_context(*, title: str = "", extra: str = "") -> str:
    """Lowercased context string for the rules, from page-level text.

    A range figure means something different on a winter test page than on a
    launch review, and that distinction lives in the page, not the quote.
    """
    return f"{title} {extra}".lower()


def reclassify(record: RawEvidence, *, context: str = "") -> tuple[RawEvidence, str | None]:
    """Apply the correction rules to one record.

    Returns ``(record, rule_name)``; *rule_name* is ``None`` when no rule fired
    or when the rule agreed with the model, in which case the record is handed
    back unchanged and the model's classification stands.
    """
    text = (record.evidence_text or "").lower()
    unit = (record.numeric_unit or "").lower()

    for rule in RULES:
        if not rule.matches(text, unit, context):
            continue
        if record.topic == rule.topic and record.subtopic == rule.subtopic:
            return record, None
        return record.model_copy(update={"topic": rule.topic, "subtopic": rule.subtopic}), rule.name
    return record, None


def canonicalize_subtopic(record: RawEvidence) -> tuple[RawEvidence, bool]:
    """Rewrite a deprecated subtopic spelling to its canonical name."""
    canonical = SUBTOPIC_ALIASES.get(record.subtopic)
    if canonical is None or canonical == record.subtopic:
        return record, False
    if canonical not in SUBTOPICS.get(record.topic, ()):
        return record, False
    return record.model_copy(update={"subtopic": canonical}), True


# --------------------------------------------------------------------------- #
# Multi-value facts
# --------------------------------------------------------------------------- #

#: ``Ladeleistung AC/DC | 11 kW / 270 kW`` and its variants. The labels are
#: captured so an ``AC/DC`` row and a ``DC/AC`` row both map correctly.
RE_AC_DC_PAIR = re.compile(
    r"(?P<first>ac|dc)\s*/\s*(?P<second>ac|dc)\b.{0,40}?"
    r"(?P<v1>\d+(?:[.,]\d+)?)\s*kw\s*/\s*(?P<v2>\d+(?:[.,]\d+)?)\s*kw",
    re.I | re.S,
)

#: Separately labelled values in one quote. Both orders occur in prose:
#: ``AC 11 kW`` (label first) and ``11 kW am AC-Lader`` (value first).
RE_AC_LABELLED = re.compile(
    r"(?:(?<![a-z])ac(?![a-z])\D{0,20}?(?P<after>\d+(?:[.,]\d+)?)\s*kw"
    r"|(?P<before>\d+(?:[.,]\d+)?)\s*kw\b[^.;]{0,24}?(?<![a-z])ac(?![a-z]))",
    re.I,
)
RE_DC_LABELLED = re.compile(
    r"(?:(?<![a-z])dc(?![a-z])\D{0,20}?(?P<after>\d+(?:[.,]\d+)?)\s*kw"
    r"|(?P<before>\d+(?:[.,]\d+)?)\s*kw\b[^.;]{0,24}?(?<![a-z])dc(?![a-z]))",
    re.I,
)


def split_multi_value(record: RawEvidence) -> list[RawEvidence]:
    """Split a record stating two labelled facts into atomic records.

    Returns the replacement records, or ``[]`` when the record states one fact
    and should be kept as it is.

    Both halves keep the original ``evidence_text`` and offsets, because both
    facts genuinely come from that one span. They differ in
    ``numeric_value``, which is what stops the span-overlap deduplication in
    :mod:`extractor` from treating them as the same proposition.

    A *range* of one value - ``14,8 - 17,0 kWh/100 km``, ``627 - 720 km`` - is
    one fact with an interval, not two facts, and is deliberately left alone
    rather than invented into a structure the schema cannot hold.
    """
    text = record.evidence_text or ""
    pair = RE_AC_DC_PAIR.search(text)
    if pair:
        first, second = pair.group("first").upper(), pair.group("second").upper()
        v1, v2 = parse_number(pair.group("v1")), parse_number(pair.group("v2"))
        if first != second and v1 is not None and v2 is not None:
            values = {first: v1, second: v2}
            return [
                _charge_power_record(record, "AC", values["AC"]),
                _charge_power_record(record, "DC", values["DC"]),
            ]

    ac, dc = RE_AC_LABELLED.search(text), RE_DC_LABELLED.search(text)
    if ac and dc:
        ac_value = parse_number(ac.group("after") or ac.group("before") or "")
        dc_value = parse_number(dc.group("after") or dc.group("before") or "")
        if ac_value is not None and dc_value is not None and ac_value != dc_value:
            return [
                _charge_power_record(record, "AC", ac_value),
                _charge_power_record(record, "DC", dc_value),
            ]
    return []


def _charge_power_record(record: RawEvidence, current: str, value: float) -> RawEvidence:
    """One atomic AC or DC charge-power record derived from *record*."""
    pretty = f"{value:g}"
    return record.model_copy(
        update={
            "topic": "charging",
            "subtopic": "charging_speed",
            "claim": f"{current} charging power is {pretty} kW.",
            "numeric_value": value,
            "numeric_unit": "kW",
        }
    )


# --------------------------------------------------------------------------- #
# Claim language
# --------------------------------------------------------------------------- #

#: German function words. Individually weak - "die" appears in English text as
#: a verb - so a decision needs several, or a German-only character.
_GERMAN_MARKERS: frozenset[str] = frozenset(
    {
        "der", "die", "das", "des", "dem", "den", "und", "ist", "sind", "nicht",
        "mit", "für", "von", "bei", "ein", "eine", "einen", "einem", "einer",
        "im", "auf", "sich", "wird", "werden", "sehr", "aber", "auch", "kein",
        "keinen", "keine", "macht", "wie", "noch", "beim", "zum", "zur", "als",
        "dass", "oder", "nach", "über", "unter", "schon", "hat", "haben",
    }
)

_GERMAN_CHARS = re.compile(r"[äöüß]", re.I)
_WORD = re.compile(r"[a-zäöüß]+", re.I)

#: Quoted spans. A product, option or package name is quoted and stays in its
#: original language by design - "Virtuelle Außenspiegel" is what Audi calls the
#: option - so the umlauts inside it say nothing about the language of the claim
#: around it.
#:
#: The single-quote branch carries lookarounds because ``'`` is also the English
#: apostrophe: without them, "it's the car's best feature" would be read as a
#: quoted span and mangled.
_QUOTED_SPAN = re.compile(
    r'"[^"]{1,100}"'
    r"|\u201c[^\u201d]{1,100}\u201d"
    r"|\u201e[^\u201c\u201d]{1,100}[\u201c\u201d]"
    r"|\u00ab[^\u00bb]{1,100}\u00bb"
    r"|\u2018[^\u2019]{1,100}\u2019"
    r"|(?<![^\W\d_])'[^']{1,100}'(?![^\W\d_])"
)

#: German nominalisation and adjective endings. These carry the signal that
#: short, ASCII-spelled German sentences lack: "Ladeleistung" and
#: "Vorkonditionierung" are unmistakable even without an umlaut. Required
#: alongside a function word, so the English "among" or "young" cannot trip it.
_GERMAN_SUFFIXES: tuple[str, ...] = ("ung", "ungen", "keit", "heit", "schaft", "lich", "isch")


def looks_non_english(text: str, *, min_markers: int = 2) -> bool:
    """Heuristic: does *text* look like it is not English?

    Quoted spans are removed before judging, because a product, option or
    package name is quoted and is meant to stay in its source language:

        The option 'Virtuelle Außenspiegel' (Code PAF) costs 1,450 EUR.

    is an English claim, and the umlauts belong to Audi's name for the option,
    not to the sentence. Judging the raw text flagged it as German.

    After that, true on any of:

    * a German-only character (``ä``, ``ö``, ``ü``, ``ß``);
    * *min_markers* distinct German function words;
    * one function word plus a word carrying a German nominalisation ending,
      which is what catches a short ASCII-spelled sentence such as
      "Die Ladeleistung faellt ab 60 Prozent ab."

    Tuned to stay quiet on English: an English claim mentioning a German model
    name has no function word, so it never reaches the second or third test.

    This is a *detector*, not a translator. Producing an English claim is the
    extraction prompt's job - no deterministic rule can translate prose - and
    this function measures whether that contract was honoured.
    """
    body = (text or "").strip()
    if not body:
        return False

    # Judge the sentence around the quoted names, not the names themselves.
    # If stripping leaves almost nothing the claim *is* the quote, so fall back
    # to the original - a claim that is only a German sentence in quotes is
    # still not an English claim.
    outside = _QUOTED_SPAN.sub(" ", body)
    body = outside if len(outside.split()) >= 3 else body

    if _GERMAN_CHARS.search(body):
        return True

    words = {match.group(0).lower() for match in _WORD.finditer(body)}
    markers = len(words & _GERMAN_MARKERS)
    if markers >= min_markers:
        return True
    if markers >= 1 and any(
        word.endswith(_GERMAN_SUFFIXES) and len(word) > 6 for word in words
    ):
        return True
    return False


# --------------------------------------------------------------------------- #
# Canonical numeric units
# --------------------------------------------------------------------------- #

#: The unit vocabulary downstream aggregation may rely on. Anything a model
#: writes is mapped onto one of these, or left alone when unrecognised.
CANONICAL_UNITS: tuple[str, ...] = (
    "kW", "kWh", "kWh/100 km", "V", "A", "km", "km/h", "minutes", "hours",
    "percent", "EUR", "kg", "litres", "dB",
)

#: Surface form (lowercased, stripped) -> canonical unit. Covers the German and
#: English spellings these pages actually use.
_UNIT_MAP: dict[str, str] = {
    # time
    "min": "minutes", "min.": "minutes", "mins": "minutes", "minute": "minutes",
    "minuten": "minutes", "minutes": "minutes", "m": "minutes",
    "h": "hours", "hr": "hours", "hrs": "hours", "hour": "hours",
    "hours": "hours", "stunde": "hours", "stunden": "hours",
    # power / energy / electrical
    "kw": "kW", "kilowatt": "kW", "kilowatts": "kW",
    "kwh": "kWh", "kilowattstunde": "kWh", "kilowattstunden": "kWh",
    "kwh/100km": "kWh/100 km", "kwh/100 km": "kWh/100 km",
    "kwh / 100 km": "kWh/100 km", "kwh per 100 km": "kWh/100 km",
    "kwh/100 kilometer": "kWh/100 km", "kwh auf 100 km": "kWh/100 km",
    "v": "V", "volt": "V", "volts": "V", "a": "A", "ampere": "A", "amps": "A",
    # distance / speed
    "km": "km", "kilometer": "km", "kilometers": "km", "kilometre": "km",
    "kilometres": "km", "kms": "km",
    "km/h": "km/h", "kmh": "km/h", "kph": "km/h", "km per hour": "km/h",
    "stundenkilometer": "km/h",
    # proportion
    "%": "percent", "percent": "percent", "per cent": "percent",
    "prozent": "percent", "pct": "percent",
    # money and misc
    "eur": "EUR", "euro": "EUR", "euros": "EUR", "€": "EUR",
    "kg": "kg", "kilogram": "kg", "kilograms": "kg", "kilo": "kg",
    "l": "litres", "liter": "litres", "litre": "litres", "litres": "litres",
    "liters": "litres", "db": "dB", "db(a)": "dB",
}

#: A bare ``kWh`` figure is consumption only when the quote says so. These are
#: the phrasings the cached pages use: "Verbrauch", "unser Schnitt auf der
#: Langstrecke", "bei konstantem Tempo 100".
RE_CONSUMPTION_CONTEXT = re.compile(
    r"verbrauch|consumption|schnitt|durchschnitt|average|langstrecke"
    r"|long[\s-]?distance|konstant|at constant|tempo\s*\d|/\s*100\s*km"
    r"|auf\s*100\s*(?:km|kilometer)|per\s*100\s*km|effizienz|efficiency",
    re.I,
)

#: ...and it is battery capacity when the quote names the battery. Capacity
#: wins, so "| Akku netto | 94,9 kWh |" is never rewritten.
RE_CAPACITY_CONTEXT = re.compile(
    r"akku|batterie|battery|kapazit|capacity|netto|brutto|nutzbar|usable"
    r"|gross|speicher|zellen",
    re.I,
)


#: Highest plausible consumption figure in kWh/100 km. Anything above this is a
#: battery capacity: production EV consumption sits around 10-35, while usable
#: pack sizes start near 50. Used only to break a tie the words leave open.
CONSUMPTION_MAX_KWH: float = 40.0


def normalize_unit(
    unit: str | None,
    evidence_text: str = "",
    *,
    value: float | None = None,
    context: str = "",
) -> str | None:
    """Map *unit* onto :data:`CANONICAL_UNITS`.

    ``Min.``, ``Minuten`` and ``min`` all become ``minutes``; ``%`` becomes
    ``percent``; ``Euro`` becomes ``EUR``.

    ``kWh`` is the one ambiguous case, and it is resolved from the quote rather
    than guessed: a consumption phrasing promotes it to ``kWh/100 km``, while
    anything naming the battery keeps it as ``kWh``. Capacity wins when both
    appear, because mislabelling a 94,9 kWh battery as consumption would be far
    worse than leaving a consumption figure unpromoted.

    When the quote itself says neither, two weaker signals decide together: the
    page has to be talking about consumption, *and* the figure has to be small
    enough to be one (see :data:`CONSUMPTION_MAX_KWH`). That is what resolves a
    terse reviewer quote such as "wir erreichten 16,3 kWh" without ever
    touching a "94,9 kWh" pack figure.

    An unrecognised unit is returned unchanged - inventing a canonical form for
    something unknown would lose information.
    """
    if unit is None:
        return None
    raw = unit.strip()
    if not raw:
        return None

    key = re.sub(r"\s+", " ", raw.lower()).strip()
    canonical = _UNIT_MAP.get(key, _UNIT_MAP.get(key.rstrip("."), raw))

    if canonical == "kWh":
        text = evidence_text or ""
        # Capacity wins outright: mislabelling a pack size as consumption is
        # far worse than leaving a consumption figure unpromoted.
        if RE_CAPACITY_CONTEXT.search(text):
            return "kWh"
        if RE_CONSUMPTION_CONTEXT.search(text):
            return "kWh/100 km"
        plausible = value is not None and 0 < value <= CONSUMPTION_MAX_KWH
        if plausible and RE_CONSUMPTION_CONTEXT.search(context or ""):
            return "kWh/100 km"
    return canonical


# --------------------------------------------------------------------------- #
# Scope filter
# --------------------------------------------------------------------------- #

#: Subjects that are not customer-facing product evidence. Deliberately
#: specific: "Dienstwagenbesteuerung" is out of scope, "Preis" alone is not,
#: because a price-value complaint is exactly the kind of evidence to keep.
RE_OUT_OF_SCOPE = re.compile(
    r"dienstwagen|firmenwagen|company[\s-]?car|geschäftswagen"
    r"|versteuerung|besteuerung|steuersatz|\bsteuer\w*|taxation|\btax\b|taxes"
    r"|leasing|leasingrate|finanzierung|financing|\bkredit|monatsrate"
    r"|versicherung|insurance|kaskoeinstufung"
    r"|kaufprämie|umweltbonus|förderung|subvention|subsid|incentive"
    r"|homologation|typgenehmigung|zulassungsvorschrift|type approval"
    r"|regulatory compliance|flottengrenzwert|co2[\s-]?flotten"
    r"|händlerangebot|dealer offer|gebrauchtwagenpreis|restwert|residual value"
    r"|listenpreis|list price|business case|total cost of ownership|\btco\b",
    re.I,
)

#: Customer-facing product subjects. One of these present means the record is
#: about the product after all, so the scope filter stands down. This is what
#: keeps "for this price the material quality disappoints" - a value-perception
#: complaint - out of the filter's reach.
#: Note the deliberate mix of anchored and unanchored alternatives. German
#: compounds carry the meaningful stem in the *middle* of a word
#: ("Materialqualität", "Rücksitz", "Ladeleistung"), so those stems must stay
#: unanchored. Short English words must be anchored, or they fire on unrelated
#: text - an unanchored ``app`` matches "applies", which stood the filter down
#: on "company car taxation now applies up to 100,000 Euro" and let an
#: out-of-scope record through.
RE_PRODUCT_SCOPE = re.compile(
    r"qualit|quality|material|verarbeit|anmutung|wertig"
    r"|komfort|comfort|(?<!be)sitz|\bseat|platz|\bspace|innenraum|beinfreiheit|legroom"
    r"|lade|laden|charg|reichweite|\brange\b|verbrauch|consumption"
    r"|bedien|usability|touchscreen|display|software|update|navigation|\bapps?\b"
    r"|lenk|steering|fahrwerk|handling|brems|\bbrak"
    r"|geräusch|gerausch|\bnoise|akustik|design|optik"
    r"|erwart|expect|wunsch|kunden|customer|nutzer|\buser"
    r"|preis-?leistung|value for money|worth it",
    re.I,
)


def is_out_of_scope(record: RawEvidence) -> tuple[bool, str]:
    """Whether *record* is outside customer-facing product evidence.

    Rejects a record whose quote is *primarily* about taxation, financing,
    incentives, insurance, homologation or a pure business case - and only when
    the quote names no customer-facing product subject. That ordering is what
    separates the two cases the brief calls out:

    * "the 0.25-percent company car taxation now applies up to 100,000 Euro"
      names taxation and no product subject, so it goes;
    * "for this price the material quality disappoints" names a price *and*
      material quality, so it stays.

    Returns ``(rejected, reason)``.
    """
    text = f"{record.evidence_text} {record.claim}"
    out = RE_OUT_OF_SCOPE.search(text)
    if not out:
        return False, ""
    product = RE_PRODUCT_SCOPE.search(text)
    if product:
        return False, ""
    return True, f"out of scope: {out.group(0).lower()!r} with no customer-facing subject"


# --------------------------------------------------------------------------- #
# Claim text cleanup
# --------------------------------------------------------------------------- #

#: Word pairs that models sometimes emit glued together. Both halves must be
#: listed, which is what stops "notable" being split into "not able".
_GLUE_FIRST: tuple[str, ...] = (
    "only", "very", "also", "not", "too", "more", "less", "much", "quite",
    "really", "still", "even", "both", "never", "always",
)
_GLUE_SECOND: tuple[str, ...] = (
    "for", "the", "and", "with", "when", "quiet", "loud", "comfortable",
    "good", "bad", "high", "low", "fast", "slow", "long", "short", "well",
    "soft", "firm", "narrow", "wide", "small", "large", "expensive", "cheap",
    "briefly", "available", "usable", "visible", "strong", "weak",
)
_GLUED = re.compile(
    r"\b(" + "|".join(_GLUE_FIRST) + r")(" + "|".join(_GLUE_SECOND) + r")\b", re.I
)

#: ``A6e-tron`` -> ``A6 e-tron``: a model code run into the following token.
_MODEL_GLUE = re.compile(r"\b([A-Za-z]{1,2}\d{1,2})(e-tron|etron|Touring|Avant|Sportback)\b")

_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.;:!?%])")
_MULTI_SPACE = re.compile(r"[ \t]{2,}")


def clean_claim_text(claim: str) -> tuple[str, bool]:
    """Repair obvious formatting artifacts in a generated claim.

    Only the ``claim`` is touched. ``evidence_text`` is a verbatim quote and
    must stay byte-for-byte identical, so it is never passed here.

    Repairs are bounded on purpose: a glued pair is split only when *both*
    halves appear in a curated list, so ``notable`` and ``online`` survive while
    ``onlyfor`` and ``veryquiet`` are fixed.

    Returns ``(claim, changed)``.
    """
    original = claim or ""
    text = _MODEL_GLUE.sub(r"\1 \2", original)
    text = _GLUED.sub(r"\1 \2", text)
    text = _SPACE_BEFORE_PUNCT.sub(r"\1", text)
    text = _MULTI_SPACE.sub(" ", text).strip()
    return text, text != original


# --------------------------------------------------------------------------- #
# Semantic role
# --------------------------------------------------------------------------- #

#: A manufacturer figure or rated capability.
RE_ROLE_CAPABILITY = re.compile(
    r"werksangabe|laut hersteller|herstellerangabe|datenblatt|spezifikation"
    r"|specification|rated|nominal|maximal|\bmax\b|bis zu|up to|laut audi"
    r"|laut bmw|offiziell|official",
    re.I,
)

#: Something the reviewer or owner actually observed.
RE_ROLE_OBSERVED = re.compile(
    r"im test|wir erreichten|wir haben|unser|gemessen|measured|in practice"
    r"|in der praxis|nur kurz|kurzzeitig|only briefly|briefly|erreichten"
    r"|beobachtet|observed|real[\s-]?world|tatsächlich|actually|erlebt",
    re.I,
)


def semantic_role(record: RawEvidence) -> str:
    """Classify a record as ``capability``, ``observed`` or ``unspecified``.

    Used only to decide whether two same-page records about one number are the
    same proposition. A rated 270 kW peak and a reviewer noting 270 kW is
    reached "only briefly" are different evidence about the same number, and
    collapsing them would delete the nuance that matters most to a product
    manager.

    An observation marker **wins** when both kinds appear. The two records
    typically share one quote, and a rated phrasing in that shared quote - "bis
    zu 270 kW" - would otherwise cancel the observation that only one of the two
    claims actually makes. "Rated at up to 270 kW, but in the test only
    briefly" is an observation about a rated figure, and the observation is the
    more specific signal.

    The role is computed when needed and never stored, so the evidence schema
    is unchanged.
    """
    text = f"{record.evidence_text} {record.claim}"
    if RE_ROLE_OBSERVED.search(text):
        return "observed"
    if RE_ROLE_CAPABILITY.search(text):
        return "capability"
    return "unspecified"


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class NormalizationReport:
    """What the normalization pass changed, for the run log."""

    split_records: int = 0
    reclassified: int = 0
    canonicalized: int = 0
    units_normalized: int = 0
    claims_cleaned: int = 0
    filtered_out_of_scope: int = 0
    non_english_claims: int = 0
    rules_fired: dict[str, int] = field(default_factory=dict)
    scope_reasons: list[str] = field(default_factory=list)

    def note_rule(self, name: str) -> None:
        self.rules_fired[name] = self.rules_fired.get(name, 0) + 1

    @property
    def changed(self) -> int:
        """Total records altered or dropped by the pass."""
        return (
            self.split_records + self.reclassified + self.canonicalized
            + self.units_normalized + self.claims_cleaned + self.filtered_out_of_scope
        )


def normalize_records(
    records: Sequence[RawEvidence], *, context: str = ""
) -> tuple[list[RawEvidence], NormalizationReport]:
    """Run every normalization pass over *records*.

    Order matters:

    1. **Scope filter** first, so nothing is spent normalizing a record that is
       about to be discarded.
    2. **Split**, so each half of a two-value row is classified on its own.
    3. **Normalize the unit**, using the quote to settle the kWh question.
    4. **Reclassify** topic/subtopic. This runs *after* the unit pass on
       purpose: promoting ``kWh`` to ``kWh/100 km`` is exactly the signal the
       consumption rule keys on, so reclassifying first would miss every
       consumption figure that was not already written per 100 km.
    5. **Canonicalize** deprecated subtopic names.
    6. **Clean the claim text** - the claim only, never the quote.
    7. **Measure claim language.**
    """
    report = NormalizationReport()
    out: list[RawEvidence] = []

    for record in records:
        rejected, reason = is_out_of_scope(record)
        if rejected:
            report.filtered_out_of_scope += 1
            report.scope_reasons.append(reason)
            continue

        parts = split_multi_value(record)
        if parts:
            report.split_records += 1
        for part in parts or [record]:
            unit = normalize_unit(
                part.numeric_unit, part.evidence_text,
                value=part.numeric_value, context=context,
            )
            if unit != part.numeric_unit:
                report.units_normalized += 1
                part = part.model_copy(update={"numeric_unit": unit})

            part, rule = reclassify(part, context=context)
            if rule:
                report.reclassified += 1
                report.note_rule(rule)
            part, renamed = canonicalize_subtopic(part)
            if renamed:
                report.canonicalized += 1

            claim, cleaned = clean_claim_text(part.claim)
            if cleaned:
                report.claims_cleaned += 1
                part = part.model_copy(update={"claim": claim})

            if looks_non_english(part.claim):
                report.non_english_claims += 1
            out.append(part)
    return out, report
