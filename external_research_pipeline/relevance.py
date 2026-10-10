"""Deterministic, post-scrape relevance gate.

A page can clear the pre-scrape URL filter on its title and snippet and still
turn out to be a cookie wall, a JS shell, or an article about something else
entirely. Once the page has been scraped the credit is already spent, but an
extraction request is not - so this gate reads the actual text and decides
whether a model call is worth making.

No LLM is involved. The vocabulary is shared with the pre-scrape filter
(:data:`search.TOPIC_KEYWORDS`) so the two gates cannot drift apart.

The gate is deliberately **conservative**: it is far cheaper to extract from a
marginal page than to silently discard a strong one, so a page is rejected only
when it shows almost no topical and no vehicle signal.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Mapping

import config
from search import TOPIC_KEYWORDS

#: Vehicle and model vocabulary. Competitor models are included on purpose:
#: competitor benchmark queries are part of the catalogue, so a thorough Audi
#: A6 e-tron charging test is on-target evidence, not an off-topic page.
VEHICLE_TERMS: tuple[str, ...] = (
    # Target vehicle
    "bmw i5",
    "i5 ",
    "i5,",
    "i5.",
    "g60",
    "g61",
    "edrive40",
    "xdrive40",
    "m60",
    "5 series",
    "5er",
    "5-series",
    "fünfer",
    # Competitors we deliberately benchmark against
    "a6 e-tron",
    "a6 etron",
    "a6 sportback e-tron",
    "eqe",
    "taycan",
    "model s",
    "model 3",
    "i4",
    "i7",
    "ix",
)

#: Terms that mark a page as a dead shell rather than content. Their presence
#: does not reject a page on its own, but they are reported so a thin page's
#: log line says *why* it was thin.
DEAD_PAGE_MARKERS: tuple[str, ...] = (
    "enable javascript",
    "javascript is required",
    "aktiviere javascript",
    "sorry to interrupt",
    "loading",
    "access denied",
    "are you a robot",
    "captcha",
    "cookie settings",
    "cookie-einstellungen",
    "page not found",
    "seite nicht gefunden",
    "404",
)


def _compile(terms: Iterable[str]) -> tuple[re.Pattern[str], ...]:
    """Compile *terms* into prefix-anchored patterns.

    Each term is anchored with ``\\b`` at the start but **not** at the end, which
    gives German compounds for free: ``lade`` matches ``Ladeleistung`` and
    ``Ladekurve`` while a word boundary still stops it matching ``Schokolade``.
    """
    patterns = []
    for term in terms:
        body = re.escape(term.strip().lower())
        prefix = r"\b" if term[:1].isalnum() else ""
        patterns.append(re.compile(prefix + body))
    return tuple(patterns)


_VEHICLE_PATTERNS = _compile(VEHICLE_TERMS)
_TOPIC_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    topic: _compile(terms) for topic, terms in TOPIC_KEYWORDS.items()
}


@dataclass(frozen=True)
class RelevanceVerdict:
    """Outcome of the gate for one page."""

    relevant: bool
    reason: str
    vehicle_hits: int = 0
    topic_hits: int = 0
    #: Topic -> hit count, for every topic with at least one hit. A charging
    #: page that also discusses comfort shows both, which is what makes
    #: cross-topic evidence worth keeping.
    hits_by_topic: Mapping[str, int] = field(default_factory=dict)
    dead_markers: tuple[str, ...] = ()

    @property
    def matched_topics(self) -> tuple[str, ...]:
        """Topics with at least one vocabulary hit, strongest first."""
        return tuple(topic for topic, _ in sorted(self.hits_by_topic.items(), key=lambda kv: (-kv[1], kv[0])))


def count_hits(text: str, patterns: Iterable[re.Pattern[str]]) -> int:
    """Number of *distinct* patterns in *patterns* that occur in *text*.

    Distinct patterns rather than total occurrences, so one word repeated by a
    navigation block cannot fake a relevant page.
    """
    return sum(1 for pattern in patterns if pattern.search(text))


def find_dead_markers(text: str) -> tuple[str, ...]:
    """Dead-page markers present in *text*."""
    lowered = text.lower()
    return tuple(marker for marker in DEAD_PAGE_MARKERS if marker in lowered)


def assess(
    text: str,
    *,
    topic: str | None = None,
    min_topic_hits: int = config.DEFAULT_MIN_TOPIC_HITS,
    min_vehicle_hits: int = config.DEFAULT_MIN_VEHICLE_HITS,
) -> RelevanceVerdict:
    """Decide whether *text* is worth an extraction request.

    The rule, in order:

    1. Count distinct vehicle-vocabulary hits, and topic-vocabulary hits for
       **every** topic - not only *topic*. A charging page that also covers
       comfort should pass on its combined signal, because the page is already
       paid for and its comfort claims are wanted too.
    2. Pass when topic hits reach *min_topic_hits*.
    3. Otherwise pass when vehicle hits reach *min_vehicle_hits* - a page
       clearly about the target car earns a look even if it words its topic
       unusually.
    4. Otherwise reject, naming the counts.

    *topic* is used only to make the log line specific; it never narrows which
    vocabularies are counted.

    Returns:
        A :class:`RelevanceVerdict`. ``relevant`` is the decision; the counts
        are kept for the run log.
    """
    lowered = (text or "").lower()
    if not lowered.strip():
        return RelevanceVerdict(False, "page text is empty")

    vehicle_hits = count_hits(lowered, _VEHICLE_PATTERNS)
    hits_by_topic = {
        name: count_hits(lowered, patterns)
        for name, patterns in _TOPIC_PATTERNS.items()
    }
    hits_by_topic = {name: count for name, count in hits_by_topic.items() if count}
    topic_hits = sum(hits_by_topic.values())
    dead = find_dead_markers(lowered)

    verdict = lambda ok, reason: RelevanceVerdict(  # noqa: E731 - local shorthand
        ok, reason, vehicle_hits, topic_hits, hits_by_topic, dead
    )

    if topic_hits >= min_topic_hits:
        detail = ", ".join(f"{name}={count}" for name, count in sorted(hits_by_topic.items()))
        return verdict(True, f"{topic_hits} topic term(s) ({detail}); vehicle terms={vehicle_hits}")

    if vehicle_hits >= min_vehicle_hits:
        return verdict(
            True,
            f"only {topic_hits} topic term(s) but {vehicle_hits} vehicle term(s) - "
            "treating as on-target",
        )

    wanted = f"{topic} " if topic else ""
    return verdict(
        False,
        f"too few {wanted}signals: {topic_hits} topic term(s) "
        f"(need {min_topic_hits}) and {vehicle_hits} vehicle term(s) (need {min_vehicle_hits})"
        + (f"; looks like a dead page ({', '.join(dead[:3])})" if dead else ""),
    )
