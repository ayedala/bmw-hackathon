"""Deterministic source-family classification and quality scoring.

Two decisions live here and nowhere else:

1. **Which family a URL belongs to** - derived from its registrable domain, not
   from the extraction model. A model that could choose its own family could
   also choose its own score.
2. **What that family is worth** - a fixed table.

The extraction model may supply a ``source_family_hint`` as context, but it is
never used for classification or scoring. Unknown domains deterministically
fall back to ``other``.
"""

from __future__ import annotations

from models import SOURCE_FAMILIES
from utils import domain_of, registrable_domain

#: Fixed quality score per source family, 0-100.
SOURCE_QUALITY: dict[str, int] = {
    "government_statistics": 95,
    "independent_test_org": 95,
    "official_manufacturer": 90,
    "professional_review": 80,
    "market_report": 80,
    "youtube_review": 70,
    "customer_forum": 60,
    "reddit": 50,
    "app_review": 50,
    "dealer": 45,
    "other": 40,
}

#: Score applied when a family is somehow absent from the table above.
FALLBACK_QUALITY: int = SOURCE_QUALITY["other"]

#: Registrable domain -> source family. Ordered by family for readability.
DOMAIN_FAMILY: dict[str, str] = {
    # Government and official statistics
    "bundesnetzagentur.de": "government_statistics",
    "kba.de": "government_statistics",
    "destatis.de": "government_statistics",
    "bmwk.de": "government_statistics",
    "bmdv.bund.de": "government_statistics",
    "umweltbundesamt.de": "government_statistics",
    "europa.eu": "government_statistics",
    "eafo.eu": "government_statistics",
    "acea.auto": "government_statistics",
    "bund.de": "government_statistics",
    # Independent test and assessment organisations
    "adac.de": "independent_test_org",
    "euroncap.com": "independent_test_org",
    "tuev-sued.de": "independent_test_org",
    "tuvsud.com": "independent_test_org",
    "dekra.de": "independent_test_org",
    "test.de": "independent_test_org",
    "greenncap.com": "independent_test_org",
    # Official manufacturer
    "bmw.de": "official_manufacturer",
    "bmw.com": "official_manufacturer",
    "bmwgroup.com": "official_manufacturer",
    "press.bmwgroup.com": "official_manufacturer",
    "bmwusa.com": "official_manufacturer",
    "mercedes-benz.com": "official_manufacturer",
    "mercedes-benz.de": "official_manufacturer",
    "mbusa.com": "official_manufacturer",
    "audi.de": "official_manufacturer",
    "audi.com": "official_manufacturer",
    "audi-mediacenter.com": "official_manufacturer",
    "porsche.com": "official_manufacturer",
    "porsche.de": "official_manufacturer",
    "tesla.com": "official_manufacturer",
    "vw.de": "official_manufacturer",
    # Professional automotive press
    "auto-motor-und-sport.de": "professional_review",
    "autobild.de": "professional_review",
    "automobilwoche.de": "professional_review",
    "handelsblatt.com": "professional_review",
    "spiegel.de": "professional_review",
    "heise.de": "professional_review",
    "golem.de": "professional_review",
    "electrive.net": "professional_review",
    "electrive.com": "professional_review",
    "efahrer.chip.de": "professional_review",
    "chip.de": "professional_review",
    "edison.media": "professional_review",
    "motor1.com": "professional_review",
    "motortrend.com": "professional_review",
    "whatcar.com": "professional_review",
    "autoexpress.co.uk": "professional_review",
    "evkx.net": "professional_review",
    "motor1.de": "professional_review",
    "insideevs.de": "professional_review",
    "insideevs.com": "professional_review",
    "autocar.co.uk": "professional_review",
    "topgear.com": "professional_review",
    "caranddriver.com": "professional_review",
    "edmunds.com": "professional_review",
    "carwow.de": "professional_review",
    "carwow.co.uk": "professional_review",
    "fastestlaps.com": "professional_review",
    "nextmove.de": "professional_review",
    "bimmertoday.de": "professional_review",
    "bmwblog.com": "professional_review",
    # Market reports and analysis
    "iea.org": "market_report",
    "statista.com": "market_report",
    "statista.de": "market_report",
    "mckinsey.com": "market_report",
    "bcg.com": "market_report",
    "deloitte.com": "market_report",
    "pwc.de": "market_report",
    "jdpower.com": "market_report",
    "bloomberg.com": "market_report",
    "transportenvironment.org": "market_report",
    # Video reviews
    "youtube.com": "youtube_review",
    "youtu.be": "youtube_review",
    # Owner forums
    "motor-talk.de": "customer_forum",
    "goingelectric.de": "customer_forum",
    "bimmerpost.com": "customer_forum",
    "bimmerfest.com": "customer_forum",
    "bimmerforums.com": "customer_forum",
    "g60.bimmerpost.com": "customer_forum",
    "5post.com": "customer_forum",
    "bmw-treff.de": "customer_forum",
    "elektroauto-news.net": "customer_forum",
    "spritmonitor.de": "customer_forum",
    "teslafahrer.de": "customer_forum",
    "gutefrage.net": "customer_forum",
    # Reddit
    "reddit.com": "reddit",
    "redd.it": "reddit",
    # App stores
    "apps.apple.com": "app_review",
    "play.google.com": "app_review",
    "trustpilot.com": "app_review",
}

#: Domains worth scraping even when the snippet does not match a topic keyword.
PREFERRED_DOMAINS: frozenset[str] = frozenset(
    {
        "adac.de",
        "bundesnetzagentur.de",
        "kba.de",
        "destatis.de",
        "eafo.eu",
        "europa.eu",
        "euroncap.com",
        "iea.org",
        "umweltbundesamt.de",
        "press.bmwgroup.com",
        "bmwgroup.com",
        "bmw.de",
        "auto-motor-und-sport.de",
        "autobild.de",
        "electrive.net",
        "efahrer.chip.de",
        "insideevs.de",
        "motor-talk.de",
        "goingelectric.de",
        "bimmerpost.com",
        "nextmove.de",
        "test.de",
        "statista.com",
    }
)

#: Substrings in a host that indicate a dealership or classified listing.
_DEALER_HINTS: tuple[str, ...] = (
    "autohaus",
    "autohandel",
    "dealer",
    "haendler",
    "mobile.de",
    "autoscout24",
    "carvago",
    "leasingmarkt",
)


def get_source_quality(source_family: str) -> int:
    """Return the fixed quality score, 0-100, for *source_family*.

    Unknown families score as ``other`` rather than raising, so a future family
    added upstream degrades gracefully instead of killing a run.
    """
    return SOURCE_QUALITY.get(source_family, FALLBACK_QUALITY)


def classify_source_family(url: str, *, hint: str | None = None) -> str:
    """Classify *url* into one of :data:`models.SOURCE_FAMILIES`.

    The *hint* parameter remains for call compatibility but is ignored. Unknown
    domains use deterministic host heuristics, then ``other``.
    """
    host = domain_of(url)
    if not host:
        return "other"

    # Exact host first (press.bmwgroup.com differs from bmwgroup.com), then the
    # registrable domain so subdomains inherit their parent's family.
    if host in DOMAIN_FAMILY:
        return DOMAIN_FAMILY[host]
    registrable = registrable_domain(url)
    if registrable in DOMAIN_FAMILY:
        return DOMAIN_FAMILY[registrable]

    if any(marker in host for marker in _DEALER_HINTS):
        return "dealer"
    if host.endswith(".gov") or ".bund.de" in host or host.endswith(".gov.uk"):
        return "government_statistics"
    if "forum" in host or "community" in host:
        return "customer_forum"

    # Model supplied hints are descriptive at most. They cannot change the
    # deterministic source-quality score for an unclassified domain.
    return "other"


# --------------------------------------------------------------------------- #
# Scrape-ordering priority
# --------------------------------------------------------------------------- #

#: Priority used to decide *which candidate URLs are worth scraping first*.
#:
#: This is deliberately a separate scale from :data:`SOURCE_QUALITY`. Quality
#: scores the *evidence* once collected and is part of the stored schema;
#: priority only orders the scrape queue and is never written to disk. The two
#: orderings genuinely differ: a YouTube review scores 70 as evidence but ranks
#: below a customer forum for scraping, because forum threads yield far more
#: extractable owner claims per page than a video transcript.
#:
#: Tier order (highest first):
#:   1 government / public statistics   5 customer forum
#:   2 independent test organisation    6 reddit
#:   3 official manufacturer            7 youtube
#:   4 professional review              8 dealer / other
SOURCE_PRIORITY: dict[str, int] = {
    "government_statistics": 100,
    "independent_test_org": 95,
    "official_manufacturer": 85,
    "professional_review": 75,
    "market_report": 70,
    "customer_forum": 60,
    "reddit": 50,
    "youtube_review": 40,
    "app_review": 30,
    "dealer": 20,
    "other": 10,
}

#: Priority for a family missing from the table above.
FALLBACK_PRIORITY: int = SOURCE_PRIORITY["other"]


def get_source_priority(source_family: str) -> int:
    """Return the scrape-ordering priority, 0-100, for *source_family*.

    Higher means scrape sooner. Unknown families fall back to ``other``.
    """
    return SOURCE_PRIORITY.get(source_family, FALLBACK_PRIORITY)


def priority_of_url(url: str, *, hint: str | None = None) -> tuple[str, int]:
    """Classify *url* and return ``(source_family, priority)``.

    Deterministic and LLM-free: the family comes from the domain table and host
    heuristics in :func:`classify_source_family`.
    """
    family = classify_source_family(url, hint=hint)
    return family, get_source_priority(family)


def is_preferred_domain(url: str) -> bool:
    """Whether *url* is on the preferred-source allowlist."""
    return domain_of(url) in PREFERRED_DOMAINS or registrable_domain(url) in PREFERRED_DOMAINS


def score_url(url: str, *, hint: str | None = None) -> tuple[str, int]:
    """Convenience wrapper returning ``(source_family, source_quality)``."""
    family = classify_source_family(url, hint=hint)
    return family, get_source_quality(family)
