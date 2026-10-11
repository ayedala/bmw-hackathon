"""Search layer: the Firecrawl Search adapter and the pre-scrape URL filter.

Two responsibilities, deliberately separated:

* :class:`FirecrawlSearchClient` - the only place that knows the Firecrawl
  Search SDK. Swapping in another provider means writing one more class with the
  same ``search`` signature.
* :class:`SearchResultFilter` - deterministic, provider-independent rules that
  decide what is worth spending a scrape credit on.

Nothing here scrapes or scores evidence.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Sequence
from urllib.parse import urlsplit

import config
from models import SearchHit
from queries import SearchQuery
from source_scoring import is_preferred_domain, priority_of_url
from utils import (
    RateLimiter,
    call_with_rate_limit_retry,
    canonicalize_url,
    domain_of,
    first_present,
    get_logger,
    is_rate_limit_error,
    registrable_domain,
    redact_sensitive_text,
    url_safety_rejection_reason,
)

# --------------------------------------------------------------------------- #
# Filter policy
# --------------------------------------------------------------------------- #

#: Hosts that aggregate, mirror or spin other sites' content, plus link farms.
#: Scraping these spends a credit on a copy of something we can get first-hand.
DENY_HOSTS: frozenset[str] = frozenset(
    {
        "pinterest.com",
        "pinterest.de",
        "facebook.com",
        "instagram.com",
        "x.com",
        "twitter.com",
        "tiktok.com",
        "linkedin.com",
        "quora.com",
        "slideshare.net",
        "scribd.com",
        "coursehero.com",
        "studocu.com",
        "alibaba.com",
        "aliexpress.com",
        "amazon.de",
        "amazon.com",
        "ebay.de",
        "ebay.com",
        "temu.com",
        "wish.com",
        "newsbreak.com",
        "medium.com",
        "blogspot.com",
        "wordpress.com",
        "webcache.googleusercontent.com",
        "translate.google.com",
        "news.google.com",
        "bing.com",
        "duckduckgo.com",
        "yandex.com",
        "baidu.com",
        "msn.com",
        "yahoo.com",
        "topcarnews.net",
        "carnewschina.com",
        "autoevolution.com",
        "zigwheels.com",
        "cardekho.com",
        "carwale.com",
        "gaadiwaadi.com",
        "rushlane.com",
    }
)

#: URL shorteners: the destination is unknown before a redirect, so never scrape.
SHORTENER_HOSTS: frozenset[str] = frozenset(
    {"bit.ly", "t.co", "tinyurl.com", "ow.ly", "buff.ly", "lnkd.in", "goo.gl", "is.gd"}
)

#: Path markers for search, tag, pagination and author index pages. These are
#: listings rather than documents and carry no extractable claim.
LISTING_PATH_MARKERS: tuple[str, ...] = (
    "/search",
    "/suche",
    "/suchergebnis",
    "/tag/",
    "/tags/",
    "/thema/",
    "/themen/",
    "/category/",
    "/categories/",
    "/kategorie/",
    "/kategorien/",
    "/author/",
    "/autor/",
    "/archive/",
    "/archiv/",
    "/sitemap",
    "/feed",
    "/rss",
    "/login",
    "/anmelden",
    "/register",
    "/registrieren",
    "/cart",
    "/warenkorb",
    "/newsletter",
    "/impressum",
    "/datenschutz",
    "/privacy",
    "/cookie",
    "/agb",
    "/terms",
)

#: Query keys that mark a result as a search-results page.
LISTING_QUERY_KEYS: frozenset[str] = frozenset({"q", "query", "s", "search", "suche", "keyword"})

#: Binary and media extensions Firecrawl cannot turn into useful markdown.
BLOCKED_EXTENSIONS: tuple[str, ...] = (
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".svg",
    ".ico",
    ".mp4",
    ".mov",
    ".avi",
    ".mkv",
    ".mp3",
    ".wav",
    ".zip",
    ".rar",
    ".7z",
    ".gz",
    ".tar",
    ".exe",
    ".dmg",
    ".apk",
    ".xls",
    ".xlsx",
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
)

#: Per-topic relevance vocabulary (German and English). A result must match its
#: topic or be on the preferred-source allowlist to be worth a scrape.
TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "infotainment": (
        "infotainment",
        "idrive",
        "touchscreen",
        "display",
        "bedienung",
        "bedienkonzept",
        "menu",
        "menü",
        "software",
        "update",
        "navigation",
        "navi",
        "sprachassistent",
        "voice",
        "apple carplay",
        "carplay",
        "android auto",
        "connecteddrive",
        "connected",
        "klimabedienung",
        "klimasteuerung",
        "usability",
        "hmi",
        "interface",
        "app",
        "taste",
        "knopf",
        "control",
    ),
    "charging": (
        "lade",
        "laden",
        "ladezeit",
        "ladeleistung",
        "ladekurve",
        "ladegeschwindigkeit",
        "schnelllad",
        "hpc",
        "charging",
        "charger",
        "charge",
        "kwh",
        "kw",
        "akku",
        "batterie",
        "battery",
        "vorkonditionier",
        "precondition",
        "reichweite",
        "range",
        "langstrecke",
        "road trip",
        "routenplan",
        "route planner",
        "ionity",
        "plug",
        "ccs",
        "soc",
        "10-80",
        "winter",
    ),
    "comfort": (
        "komfort",
        "comfort",
        "sitz",
        "seat",
        "fahrkomfort",
        "federung",
        "suspension",
        "dämpfer",
        "geräusch",
        "gerausch",
        "noise",
        "windgeräusch",
        "abrollgeräusch",
        "akustik",
        "innenraum",
        "interior",
        "material",
        "qualität",
        "quality",
        "platz",
        "space",
        "rücksitz",
        "rear seat",
        "beinfreiheit",
        "legroom",
        "ride",
        "refinement",
        "klima",
    ),
    "range": (
        "reichweite",
        "range",
        "verbrauch",
        "consumption",
        "kwh/100",
        "kwh / 100",
        "wltp",
        "testverbrauch",
        "stromverbrauch",
        "efficiency",
        "effizienz",
        "autobahn",
        "langstrecke",
        "akku",
        "batterie",
        "kapazit",
        "km",
    ),
    "driving_experience": (
        "lenkung",
        "lenkverhalten",
        "steering",
        "handling",
        "fahrwerk",
        "fahrverhalten",
        "kurven",
        "agil",
        "bremse",
        "bremsen",
        "braking",
        "brake",
        "wankt",
        "kurvenlage",
        "gewichtsverteilung",
        "fahrdynamik",
        "dynamik",
    ),
    "market_trend": (
        "ladeinfrastruktur",
        "ladepunkt",
        "ladesäule",
        "charging infrastructure",
        "charging point",
        "charging network",
        "schnelllad",
        "hpc",
        "elektroauto",
        "elektromobilität",
        "electric vehicle",
        " ev ",
        "bev",
        "zulassung",
        "registration",
        "marktanteil",
        "market share",
        "studie",
        "study",
        "survey",
        "umfrage",
        "statistik",
        "statistic",
        "prognose",
        "forecast",
        "outlook",
        "2030",
        "2026",
        "bundesnetzagentur",
        "kba",
        "eafo",
        "zuverlässigkeit",
        "reliability",
        "erwartung",
        "expectation",
        "kunden",
        "customer",
    ),
}


@dataclass(slots=True)
class FilterOutcome:
    """Result of applying :class:`SearchResultFilter` to one batch of hits."""

    kept: list[SearchHit] = field(default_factory=list)
    skipped_duplicate: int = 0
    skipped_filtered: int = 0
    reasons: dict[str, str] = field(default_factory=dict)


class SearchResultFilter:
    """Decides which search results are worth a scrape credit.

    Stateful across calls within one run: a canonical URL seen once is reported
    as a duplicate on every later appearance, whichever query surfaced it.
    """

    def __init__(self, *, require_topic_match: bool = True) -> None:
        self.require_topic_match = require_topic_match
        self._seen_canonical: set[str] = set()

    def reset(self) -> None:
        """Forget previously seen URLs."""
        self._seen_canonical.clear()

    def apply(self, hits: Iterable[SearchHit]) -> FilterOutcome:
        """Partition *hits* into kept, duplicate and filtered."""
        outcome = FilterOutcome()
        for hit in hits:
            if not hit.canonical_url:
                outcome.skipped_filtered += 1
                outcome.reasons[hit.url] = "unparsable url"
                continue
            if hit.canonical_url in self._seen_canonical:
                outcome.skipped_duplicate += 1
                outcome.reasons[hit.url] = "duplicate url"
                continue
            reason = self.rejection_reason(hit)
            if reason is not None:
                self._seen_canonical.add(hit.canonical_url)
                outcome.skipped_filtered += 1
                outcome.reasons[hit.url] = reason
                continue
            self._seen_canonical.add(hit.canonical_url)
            outcome.kept.append(hit)
        return outcome

    def rejection_reason(self, hit: SearchHit) -> str | None:
        """Return why *hit* should not be scraped, or ``None`` to keep it."""
        unsafe_reason = url_safety_rejection_reason(hit.url)
        if unsafe_reason is not None:
            return unsafe_reason
        parts = urlsplit(hit.canonical_url)
        host = domain_of(hit.canonical_url)
        path = (parts.path or "").lower()

        if not host:
            return "no host"
        if host in SHORTENER_HOSTS:
            return "url shortener"
        if host in DENY_HOSTS or any(host.endswith("." + bad) for bad in DENY_HOSTS):
            return "aggregator or low-value host"
        if path.endswith(BLOCKED_EXTENSIONS):
            return "non-text file"
        if any(marker in path for marker in LISTING_PATH_MARKERS):
            return "listing or boilerplate page"
        if any(key in LISTING_QUERY_KEYS for key, _ in _query_pairs(parts.query)):
            return "search-results page"
        if path in ("", "/") and not is_preferred_domain(hit.canonical_url):
            return "site root, no specific document"

        if self.require_topic_match and not is_preferred_domain(hit.canonical_url):
            if not self._matches_topic(hit):
                return f"no {hit.topic} keyword in title/snippet/url"
        return None

    @staticmethod
    def _matches_topic(hit: SearchHit) -> bool:
        """Whether the hit's text mentions anything from its topic vocabulary."""
        keywords = TOPIC_KEYWORDS.get(hit.topic, ())
        if not keywords:
            return True
        haystack = " ".join((hit.title, hit.description, hit.canonical_url)).lower()
        return any(keyword in haystack for keyword in keywords)


def _query_pairs(query: str) -> list[tuple[str, str]]:
    """Parse a query string into lowercased key/value pairs."""
    from urllib.parse import parse_qsl

    return [(key.lower(), value) for key, value in parse_qsl(query, keep_blank_values=True)]


def classify_hits(hits: Iterable[SearchHit]) -> list[SearchHit]:
    """Attach ``source_family`` and ``priority`` to each hit, deterministically.

    Classification is domain-driven (see :mod:`source_scoring`); no LLM is
    involved. Returns new objects rather than mutating the inputs.
    """
    classified: list[SearchHit] = []
    for hit in hits:
        family, priority = priority_of_url(hit.canonical_url or hit.url)
        classified.append(hit.model_copy(update={"source_family": family, "priority": priority}))
    return classified


def rank_hits(hits: Sequence[SearchHit]) -> list[SearchHit]:
    """Order hits strongest-source-first, fully deterministically.

    Within a capped run the page budget is spent top-down, so this ordering
    decides which evidence actually gets collected. The sort key is, in order:

    1. ``priority`` descending - the source-family tier (government statistics
       first, dealer/other last).
    2. preferred-domain allowlist - breaks ties inside a tier toward the
       sources this project trusts most.
    3. the provider's own ``position`` ascending.
    4. ``canonical_url`` ascending - a final tie-break so that identical inputs
       always produce byte-identical ordering.

    Hits that have not been classified yet are classified here, so callers can
    pass raw hits.
    """
    classified = [hit if hit.source_family else classify_hits([hit])[0] for hit in hits]
    return sorted(
        classified,
        key=lambda hit: (
            -hit.priority,
            0 if is_preferred_domain(hit.canonical_url) else 1,
            hit.position,
            hit.canonical_url,
        ),
    )


def select_diverse(ranked: Sequence[SearchHit], max_pages: int) -> tuple[list[SearchHit], list[SearchHit]]:
    """Pick up to *max_pages* hits, spreading the early slots across sources.

    Ranking alone would spend a small budget on whichever domain happened to
    return the most results, so a five-page run could become five Motor-Talk
    threads. Selection therefore runs in three deterministic passes over the
    already-ranked list:

    1. **New family and new domain** - the strongest unseen source family from
       an unseen domain. This fills the early slots with genuinely different
       kinds of evidence.
    2. **New domain** - the next strongest hit from a domain not yet used, even
       if its family has appeared. Adds breadth once every family is covered.
    3. **Global ranking** - whatever is left, in rank order, which is where a
       second page from an already-used domain is allowed in.

    Because every pass walks *ranked* in order and the passes are ordered, the
    result is a pure function of the input.

    Returns:
        ``(selected, deferred)`` - deferred keeps its rank order and is what a
        later run picks up.
    """
    if max_pages <= 0:
        return [], list(ranked)

    chosen_ids: set[int] = set()
    selected: list[SearchHit] = []
    seen_families: set[str] = set()
    seen_domains: set[str] = set()

    def take(hit: SearchHit) -> None:
        chosen_ids.add(id(hit))
        selected.append(hit)
        seen_families.add(hit.source_family)
        seen_domains.add(registrable_domain(hit.canonical_url))

    # Pass 1: an unseen family from an unseen domain.
    for hit in ranked:
        if len(selected) >= max_pages:
            break
        domain = registrable_domain(hit.canonical_url)
        if hit.source_family not in seen_families and domain not in seen_domains:
            take(hit)

    # Pass 2: an unseen domain, family may repeat.
    for hit in ranked:
        if len(selected) >= max_pages:
            break
        if id(hit) in chosen_ids:
            continue
        if registrable_domain(hit.canonical_url) not in seen_domains:
            take(hit)

    # Pass 3: fill the remaining slots by global ranking.
    for hit in ranked:
        if len(selected) >= max_pages:
            break
        if id(hit) not in chosen_ids:
            take(hit)

    deferred = [hit for hit in ranked if id(hit) not in chosen_ids]
    return selected, deferred


def summarize_selection(hits: Sequence[SearchHit]) -> tuple[dict[str, int], list[str]]:
    """Return ``(count per source family, sorted unique domains)`` for *hits*."""
    families: dict[str, int] = {}
    for hit in hits:
        families[hit.source_family or "unclassified"] = families.get(hit.source_family or "unclassified", 0) + 1
    ordered = dict(sorted(families.items(), key=lambda kv: (-kv[1], kv[0])))
    domains = sorted({registrable_domain(hit.canonical_url) for hit in hits})
    return ordered, domains


# --------------------------------------------------------------------------- #
# Firecrawl Search adapter
# --------------------------------------------------------------------------- #


class SearchError(RuntimeError):
    """Raised when the search provider could not be reached or returned garbage."""


class FirecrawlSearchClient:
    """Adapter over the Firecrawl Search API.

    Verified against ``firecrawl-py`` 4.50.0 (October 2026)::

        from firecrawl import Firecrawl
        firecrawl = Firecrawl(api_key="fc-...")
        result = firecrawl.search("query", limit=5, location="Germany", sources=["web"])
        for item in result.web or []:
            item.url, item.title, item.description, item.position

    Search costs 2 credits per 10 results, rounded up. ``scrape_options`` is
    deliberately *not* used: combining search and scrape would fetch every
    result before the filter has had a chance to reject it.
    """

    def __init__(
        self,
        api_key: str,
        *,
        location: str = config.SEARCH_LOCATION,
        delay_seconds: float = config.DEFAULT_SEARCH_DELAY_SECONDS,
        max_retries: int = config.DEFAULT_FIRECRAWL_MAX_RETRIES,
        max_sleep: float = config.MAX_RATE_LIMIT_SLEEP_SECONDS,
        limiter: RateLimiter | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._api_key = api_key
        self._location = location
        self._client: Any | None = None
        self.call_count = 0
        self._log = get_logger()
        self._max_retries = max(1, int(max_retries))
        self._max_sleep = max_sleep
        self._sleeper = sleeper
        #: Shared throttle. One limiter per client means the pause is enforced
        #: across the whole query loop, not per query.
        self.limiter = limiter if limiter is not None else RateLimiter(delay_seconds, sleeper=sleeper)
        #: Queries abandoned because the retry budget ran out while rate limited.
        self.rate_limited_queries = 0

    @property
    def client(self) -> Any:
        """Lazily construct the Firecrawl client so imports stay cheap."""
        if self._client is None:
            try:
                from firecrawl import Firecrawl
            except ImportError as exc:  # pragma: no cover - environment dependent
                raise SearchError(
                    "firecrawl-py is not installed. Run "
                    "`pip install -r requirements.txt` inside src/bmw_pm/data_pipeline/web_research/."
                ) from exc
            self._client = Firecrawl(api_key=self._api_key)
        return self._client

    def search(self, query: SearchQuery, *, limit: int) -> list[SearchHit]:
        """Run one search and return parsed hits.

        A provider failure is logged and returns an empty list: one dead query
        must not end the run.
        """
        try:
            payload = self._call(query.text, limit)
        except Exception as exc:  # noqa: BLE001 - provider errors are varied
            if is_rate_limit_error(exc):
                self.rate_limited_queries += 1
                self._log.error(
                    "search for %r abandoned after %d rate-limited attempt(s); "
                    "continuing the run. Raise FIRECRAWL_SEARCH_DELAY_SECONDS or "
                    "FIRECRAWL_MAX_RETRIES if this repeats.",
                    query.text,
                    self._max_retries,
                )
            else:
                self._log.error("search failed for %r: %s", query.text, redact_sensitive_text(exc))
            return []

        hits = list(self._parse(payload, query))
        self._log.info("search %r -> %d result(s)", query.text, len(hits))
        return hits

    def _call(self, text: str, limit: int) -> Any:
        """Issue the SDK search call under the throttle, with retries.

        Every attempt passes through the shared :class:`RateLimiter`, so the
        configured delay is honoured between queries *and* between retries. A
        429 carrying ``Retry-After`` pauses the whole loop for that long rather
        than only the failing query.
        """
        return call_with_rate_limit_retry(
            lambda: self._search_once(text, limit),
            attempts=self._max_retries,
            base_delay=max(self.limiter.min_interval, 1.0),
            max_sleep=self._max_sleep,
            label=f"firecrawl.search({text!r})",
            limiter=self.limiter,
            sleeper=self._sleeper,
            logger=self._log,
        )

    def _search_once(self, text: str, limit: int) -> Any:
        """One unretried Firecrawl search request."""
        self.call_count += 1
        self._log.debug("firecrawl.search(%r, limit=%d)", text, limit)
        return self.client.search(
            text,
            limit=limit,
            sources=["web"],
            location=self._location,
            timeout=config.SEARCH_TIMEOUT_MS,
        )

    @staticmethod
    def _parse(payload: Any, query: SearchQuery) -> Iterable[SearchHit]:
        """Normalize a search response into :class:`SearchHit` objects.

        Accepts the documented ``result.web`` shape and tolerates a dict or a
        bare list, so a minor SDK response change does not break the run.
        """
        for index, item in enumerate(_iter_web_results(payload)):
            url = first_present(item, ("url", "link", "source_url", "sourceURL"))
            if not isinstance(url, str) or not url.strip():
                continue
            title = first_present(item, ("title", "name", "og_title")) or ""
            description = first_present(item, ("description", "snippet", "highlights")) or ""
            position = first_present(item, ("position", "rank"))
            yield SearchHit(
                url=url.strip(),
                canonical_url=canonicalize_url(url),
                title=str(title),
                description=str(description) if not isinstance(description, list) else " ".join(map(str, description)),
                position=int(position) if isinstance(position, int) else index + 1,
                query=query.text,
                topic=query.topic,
                category=query.category,
            )


def _iter_web_results(payload: Any) -> Iterable[Any]:
    """Yield the web-result items out of whatever shape the SDK returned."""
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    web = first_present(payload, ("web", "results", "data"))
    if isinstance(web, list):
        return web
    if isinstance(web, dict):
        nested = web.get("results")
        return nested if isinstance(nested, list) else []
    return []
