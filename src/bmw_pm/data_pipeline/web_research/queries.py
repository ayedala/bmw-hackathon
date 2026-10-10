"""The search-query catalogue, grouped by category and tagged with a topic.

Each query carries the ``topic`` its results will be filed under. Competitor
and benchmark queries are tagged with the topic they actually probe (an Audi
charging test is charging evidence), so ``--topic charging`` picks up the BMW
and the competitor charging queries together. Use ``--category`` to run one
category on its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from models import TOPICS

CATEGORIES: tuple[str, ...] = (
    "infotainment",
    "charging",
    "comfort",
    "competitor_benchmark",
    "market",
)


@dataclass(frozen=True, slots=True)
class SearchQuery:
    """One search query plus the topic and category it belongs to."""

    text: str
    topic: str
    category: str


def _group(category: str, topic: str, texts: Iterable[str]) -> tuple[SearchQuery, ...]:
    """Build a query group where every query shares one topic."""
    return tuple(SearchQuery(text=text, topic=topic, category=category) for text in texts)


INFOTAINMENT_QUERIES: tuple[SearchQuery, ...] = _group(
    "infotainment",
    "infotainment",
    (
        "BMW i5 Infotainment Erfahrungen",
        "BMW G60 Bedienung Kritik",
        "BMW i5 Touchscreen Erfahrungen",
        "BMW i5 Software Probleme Forum",
        "BMW i5 ConnectedDrive Probleme",
        "BMW i5 physical controls",
        "BMW G60 infotainment review",
        "BMW i5 iDrive usability",
        "BMW G60 Klimabedienung Touchscreen",
        "BMW i5 Android Auto Probleme",
    ),
)

CHARGING_QUERIES: tuple[SearchQuery, ...] = _group(
    "charging",
    "charging",
    (
        "BMW i5 Ladeprobleme Erfahrungen",
        "BMW i5 Ladegeschwindigkeit Test",
        "BMW i5 Batterie Vorkonditionierung Erfahrungen",
        "BMW i5 Langstrecke Forum",
        "BMW i5 charging curve",
        "BMW i5 10-80 charging",
        "BMW i5 route planner charging",
        "BMW i5 Schnellladen Erfahrungen",
        "BMW i5 HPC Laden Forum",
        "BMW i5 Winter Laden Erfahrungen",
    ),
)

COMFORT_QUERIES: tuple[SearchQuery, ...] = _group(
    "comfort",
    "comfort",
    (
        "BMW i5 Sitzkomfort Erfahrungen",
        "BMW G60 Fahrkomfort Erfahrungen",
        "BMW G60 Windgeräusche",
        "BMW G60 Innenraum Qualität",
        "BMW i5 rear seat comfort",
        "BMW i5 Langstrecke Komfort",
        "BMW i5 Abrollgeräusche",
        "BMW G60 Materialqualität Innenraum",
        "BMW i5 Rücksitz Komfort",
        "BMW G60 Federung Komfort",
    ),
)

#: Competitor and benchmark queries. Each is tagged with the topic it probes so
#: that a topic-scoped run includes the matching competitor comparison.
COMPETITOR_QUERIES: tuple[SearchQuery, ...] = (
    SearchQuery("Audi A6 e-tron Laden Erfahrungen", "charging", "competitor_benchmark"),
    SearchQuery("Audi A6 e-tron infotainment review", "infotainment", "competitor_benchmark"),
    SearchQuery("Audi A6 e-tron charging test", "charging", "competitor_benchmark"),
    SearchQuery("Mercedes EQE Ladeprobleme Erfahrungen", "charging", "competitor_benchmark"),
    SearchQuery("Mercedes EQE infotainment usability", "infotainment", "competitor_benchmark"),
    SearchQuery("Mercedes EQE charging test", "charging", "competitor_benchmark"),
    SearchQuery("Porsche Taycan charging test", "charging", "competitor_benchmark"),
    SearchQuery("Porsche Taycan infotainment usability", "infotainment", "competitor_benchmark"),
    SearchQuery("Tesla Model S infotainment usability", "infotainment", "competitor_benchmark"),
    SearchQuery("Tesla Model S charging test", "charging", "competitor_benchmark"),
)

MARKET_QUERIES: tuple[SearchQuery, ...] = _group(
    "market",
    "market_trend",
    (
        "Deutschland Schnellladeinfrastruktur 2026",
        "EV charging customer survey Germany",
        "Elektroauto Ladezuverlässigkeit Deutschland Studie",
        "Schnellladen Deutschland 2030",
        "Germany EV charging infrastructure",
        "Deutschland HPC Ladepunkte",
        "Bundesnetzagentur Ladeinfrastruktur Elektroauto",
        "EAFO Germany charging infrastructure",
        "EV charging reliability Germany",
        "premium EV customer expectations Germany",
    ),
)

ALL_QUERIES: tuple[SearchQuery, ...] = (
    INFOTAINMENT_QUERIES
    + CHARGING_QUERIES
    + COMFORT_QUERIES
    + COMPETITOR_QUERIES
    + MARKET_QUERIES
)


def select_queries(
    *, topic: str | None = None, category: str | None = None
) -> tuple[SearchQuery, ...]:
    """Return the queries matching *topic* and/or *category*.

    Raises:
        ValueError: if *topic* or *category* is not a known value.
    """
    if topic is not None and topic not in TOPICS:
        raise ValueError(f"unknown topic {topic!r}; expected one of {', '.join(TOPICS)}")
    if category is not None and category not in CATEGORIES:
        raise ValueError(
            f"unknown category {category!r}; expected one of {', '.join(CATEGORIES)}"
        )

    selected = ALL_QUERIES
    if topic is not None:
        selected = tuple(q for q in selected if q.topic == topic)
    if category is not None:
        selected = tuple(q for q in selected if q.category == category)
    return selected


def queries_by_topic() -> dict[str, int]:
    """Count of catalogued queries per topic (used by ``--list-queries``)."""
    counts: dict[str, int] = {topic: 0 for topic in TOPICS}
    for query in ALL_QUERIES:
        counts[query.topic] += 1
    return counts
