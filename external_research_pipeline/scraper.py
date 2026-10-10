"""Scrape layer: the Firecrawl Scrape adapter and the credit-guarding coordinator.

The coordinator is the only component that may spend a scrape credit, and it
refuses to do so until three cheap local checks have passed:

1. the URL is canonicalized,
2. the visited-URL ledger does not already record a successful scrape,
3. the local cache in ``data/cache/`` holds no payload for it.

``--force`` bypasses checks 2 and 3 and nothing else.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

import config
from models import RawPage, SearchHit
from storage import PageCache, VisitedUrlStore
from utils import (
    RateLimiter,
    call_with_rate_limit_retry,
    canonicalize_url,
    first_present,
    get_logger,
    registrable_domain,
    redact_sensitive_text,
    utc_now_iso,
)


class ScrapeOutcome(str, Enum):
    """How a single URL was resolved."""

    SCRAPED = "scraped"
    CACHED = "cached"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass(slots=True)
class ScrapeResult:
    """One URL's resolution: the page when there is one, plus the outcome."""

    outcome: ScrapeOutcome
    page: RawPage | None = None
    detail: str = ""

    @property
    def ok(self) -> bool:
        """Whether usable page content was obtained."""
        return self.page is not None


class ScrapeError(RuntimeError):
    """Raised when the scrape provider is unavailable or returned no content."""


# --------------------------------------------------------------------------- #
# Firecrawl Scrape adapter
# --------------------------------------------------------------------------- #


class FirecrawlScraperClient:
    """Adapter over the Firecrawl Scrape API.

    Verified against ``firecrawl-py`` 4.50.0 (October 2026)::

        from firecrawl import Firecrawl
        firecrawl = Firecrawl(api_key="fc-...")
        doc = firecrawl.scrape(url, formats=["markdown"], only_main_content=True)
        doc.markdown, doc.metadata.title, doc.metadata.source_url

    The SDK converts response field names from camelCase to snake_case, so
    ``sourceURL`` arrives as ``source_url``; every metadata read below accepts
    both spellings anyway.

    ``max_age`` enables Firecrawl's own 2-day server cache, which improves
    latency but **still costs 1 credit** - only the local cache avoids spend.
    """

    def __init__(
        self,
        api_key: str,
        *,
        delay_seconds: float = config.DEFAULT_SEARCH_DELAY_SECONDS,
        max_retries: int = config.DEFAULT_FIRECRAWL_MAX_RETRIES,
        max_sleep: float = config.MAX_RATE_LIMIT_SLEEP_SECONDS,
        limiter: RateLimiter | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._api_key = api_key
        self._client: Any | None = None
        self.call_count = 0
        self._log = get_logger()
        self._max_retries = max(1, int(max_retries))
        self._max_sleep = max_sleep
        self._sleeper = sleeper
        #: Scrapes obey the same per-minute budget as searches. Pass the search
        #: client's limiter to share one budget across both endpoints.
        self.limiter = limiter if limiter is not None else RateLimiter(delay_seconds, sleeper=sleeper)

    @property
    def client(self) -> Any:
        """Lazily construct the Firecrawl client."""
        if self._client is None:
            try:
                from firecrawl import Firecrawl
            except ImportError as exc:  # pragma: no cover - environment dependent
                raise ScrapeError(
                    "firecrawl-py is not installed. Run "
                    "`pip install -r requirements.txt` inside external_research_pipeline/."
                ) from exc
            self._client = Firecrawl(api_key=self._api_key)
        return self._client

    def fetch(self, url: str) -> dict[str, Any]:
        """Scrape *url* under the throttle, with rate-limit-aware retries.

        The URL is requested exactly as the search provider returned it; the
        canonical form is only ever an identity key. A 429 waits for the
        provider's ``Retry-After`` when one is supplied, otherwise exponential
        backoff.

        Raises:
            ScrapeError: when the response carries no usable markdown.
        """
        return call_with_rate_limit_retry(
            lambda: self._fetch_once(url),
            attempts=self._max_retries,
            base_delay=max(self.limiter.min_interval, 1.0),
            max_sleep=self._max_sleep,
            label=f"firecrawl.scrape({url})",
            limiter=self.limiter,
            sleeper=self._sleeper,
            logger=self._log,
        )

    def _fetch_once(self, url: str) -> dict[str, Any]:
        """One unretried Firecrawl scrape request."""
        self.call_count += 1
        self._log.debug("firecrawl.scrape(%s)", url)
        document = self.client.scrape(
            url,
            formats=["markdown"],
            only_main_content=True,
            max_age=config.SCRAPE_MAX_AGE_MS,
            timeout=config.SCRAPE_TIMEOUT_MS,
        )
        payload = self._normalize(document, url)
        if not payload.get("markdown"):
            raise ScrapeError(f"no markdown returned for {url}")
        return payload

    @staticmethod
    def _normalize(document: Any, requested_url: str) -> dict[str, Any]:
        """Flatten a Firecrawl document into the fields this pipeline stores."""
        markdown = first_present(document, ("markdown", "content")) or ""
        metadata = first_present(document, ("metadata", "meta")) or {}

        title = first_present(metadata, ("title", "og_title", "ogTitle")) or ""
        site_name = first_present(metadata, ("site_name", "og_site_name", "ogSiteName"))
        source_url = first_present(metadata, ("source_url", "sourceURL", "url")) or requested_url
        published = first_present(
            metadata,
            (
                "published_time",
                "publishedTime",
                "article_published_time",
                "article:published_time",
                "og_published_time",
                "date",
                "datePublished",
                "modified_time",
                "modifiedTime",
            ),
        )
        status_code = first_present(metadata, ("status_code", "statusCode"))

        return {
            "markdown": str(markdown),
            "title": str(title),
            "source_name": str(site_name) if site_name else registrable_domain(requested_url),
            "source_url": str(source_url),
            "published_at": str(published) if published else None,
            "status_code": int(status_code) if isinstance(status_code, int) else None,
            "language": first_present(metadata, ("language", "lang")),
        }


# --------------------------------------------------------------------------- #
# Credit-guarding coordinator
# --------------------------------------------------------------------------- #


class ScrapeCoordinator:
    """Resolves URLs to pages through cache, ledger and - last - Firecrawl.

    Args:
        client: The scrape adapter, or ``None`` for planning-only use.
        cache: Local page cache.
        visited: Visited-URL ledger.
        force: Re-scrape even when cached or already visited.
    """

    def __init__(
        self,
        *,
        client: FirecrawlScraperClient | None,
        cache: PageCache,
        visited: VisitedUrlStore,
        force: bool = False,
    ) -> None:
        self._client = client
        self._cache = cache
        self._visited = visited
        self._force = force
        self._log = get_logger()
        self.cache_hits = 0
        self.scrapes = 0
        self.failures = 0

    # -- planning (no network, no credits) --------------------------------- #

    def plan(self, hit: SearchHit) -> ScrapeOutcome:
        """Predict how *hit* would be resolved, without contacting any provider.

        This is what ``--dry-run`` reports, and it uses the same branches as
        :meth:`resolve`, so the preview cannot drift from the real behaviour.
        """
        if self._force:
            return ScrapeOutcome.SCRAPED
        if self._cache.has(hit.canonical_url):
            return ScrapeOutcome.CACHED
        if self._visited.was_scraped(hit.canonical_url):
            return ScrapeOutcome.SKIPPED
        return ScrapeOutcome.SCRAPED

    # -- execution --------------------------------------------------------- #

    def resolve(self, hit: SearchHit) -> ScrapeResult:
        """Return page content for *hit*, spending a credit only if unavoidable."""
        canonical = hit.canonical_url or canonicalize_url(hit.url)

        if not self._force:
            cached = self._cache.get(canonical)
            if cached is not None:
                self.cache_hits += 1
                self._log.info("cache hit  %s", canonical)
                self._visited.mark(
                    canonical, status="cached", title=str(cached.get("title", "")), topic=hit.topic, query=hit.query
                )
                return ScrapeResult(ScrapeOutcome.CACHED, self._to_page(cached, hit, canonical))

            if self._visited.was_scraped(canonical):
                self._log.info("skip visited  %s (use --force to re-scrape)", canonical)
                return ScrapeResult(ScrapeOutcome.SKIPPED, None, "already visited")

        if self._client is None:
            return ScrapeResult(ScrapeOutcome.SKIPPED, None, "no scrape client configured")

        try:
            payload = self._client.fetch(hit.url)
        except Exception as exc:  # noqa: BLE001 - one bad page must not stop the run
            self.failures += 1
            safe_detail = redact_sensitive_text(exc, limit=300)
            self._log.error("scrape failed  %s: %s", hit.url, safe_detail)
            self._visited.mark(canonical, status="failed", topic=hit.topic, query=hit.query, detail=safe_detail)
            return ScrapeResult(ScrapeOutcome.FAILED, None, safe_detail)

        self.scrapes += 1
        self._cache.put(canonical, payload)
        self._visited.mark(
            canonical, status="scraped", title=payload.get("title", ""), topic=hit.topic, query=hit.query
        )
        self._log.info("scraped    %s (%d chars)", canonical, len(payload.get("markdown", "")))
        return ScrapeResult(ScrapeOutcome.SCRAPED, self._to_page(payload, hit, canonical))

    @staticmethod
    def _to_page(payload: dict[str, Any], hit: SearchHit, canonical: str) -> RawPage:
        """Build the stored :class:`RawPage` from a payload and its search hit."""
        return RawPage(
            url=hit.url,
            resolved_url=str(payload.get("source_url") or hit.url),
            canonical_url=canonical,
            title=str(payload.get("title") or hit.title or ""),
            source_name=str(payload.get("source_name") or registrable_domain(hit.url)),
            published_at=payload.get("published_at"),
            query=hit.query,
            topic=hit.topic,
            retrieved_at=str(payload.get("cached_at") or utc_now_iso()),
            markdown=str(payload.get("markdown") or ""),
        )
