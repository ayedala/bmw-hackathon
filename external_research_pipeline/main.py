"""CLI entry point for the external research pipeline.

Usage examples::

    python main.py                                        # every topic
    python main.py --topic charging
    python main.py --topic comfort --dry-run
    python main.py --topic charging --max-pages 10 --search-limit 5
    python main.py --topic infotainment --force

The orchestration order is fixed: search, filter, plan, scrape, extract,
normalize, score, group, deduplicate, write. Scoring, grouping and
deduplication are deterministic and happen after the model has had its say.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from dataclasses import dataclass

import config
import dedup
import storage
from config import ConfigError, Settings
from dedup import independence_group_for, mark_duplicates
from extractor import EvidenceExtractor
from llm_provider import get_provider
from models import ProcessedEvidence, RawEvidence, RawPage, ResearchRun, SearchHit, TOPICS
from queries import CATEGORIES, ALL_QUERIES, SearchQuery, queries_by_topic, select_queries
from scraper import FirecrawlScraperClient, ScrapeCoordinator, ScrapeOutcome
from search import (
    FirecrawlSearchClient,
    SearchResultFilter,
    classify_hits,
    rank_hits,
    select_diverse,
    summarize_selection,
)
from source_scoring import get_source_quality
from storage import PageCache, VisitedUrlStore
from utils import evidence_id, get_logger, registrable_domain, setup_logging, utc_now_iso


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def build_parser() -> argparse.ArgumentParser:
    """Define the command-line interface."""
    parser = argparse.ArgumentParser(
        prog="python main.py",
        description=(
            "Collect external public-web evidence about the BMW 5 Series / i5 (G60) "
            "for product research. Collects and structures evidence only - it never "
            "generates product requirements or priorities."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "credit safety:\n"
            "  Search costs ~2 Firecrawl credits per 10 results; each uncached page\n"
            "  scrape costs 1. Cached pages and already-visited URLs cost nothing.\n"
            "  Always try --dry-run first, and --dry-run --no-search to plan with\n"
            "  zero API calls.\n"
        ),
    )
    parser.add_argument("--topic", choices=TOPICS, help="restrict to one research topic")
    parser.add_argument(
        "--category",
        choices=CATEGORIES,
        help="restrict to one query category (e.g. competitor_benchmark)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        metavar="N",
        help=f"cap pages handled this run (default {config.DEFAULT_MAX_PAGES_PER_RUN})",
    )
    parser.add_argument(
        "--search-limit",
        type=int,
        metavar="N",
        help=f"results requested per query (default {config.DEFAULT_SEARCH_LIMIT})",
    )
    parser.add_argument(
        "--search-delay",
        type=float,
        metavar="SECONDS",
        help=(
            "seconds between Firecrawl requests "
            f"(default {config.DEFAULT_SEARCH_DELAY_SECONDS}, env FIRECRAWL_SEARCH_DELAY_SECONDS)"
        ),
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        metavar="N",
        help=(
            "attempts per Firecrawl request "
            f"(default {config.DEFAULT_FIRECRAWL_MAX_RETRIES}, env FIRECRAWL_MAX_RETRIES)"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="plan only: no page scrapes, no LLM calls",
    )
    parser.add_argument(
        "--no-search",
        action="store_true",
        help="with --dry-run, skip search too so the run makes zero API calls",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="re-scrape URLs even when cached or already visited (spends credits)",
    )
    parser.add_argument("--verbose", action="store_true", help="debug-level logging")
    parser.add_argument(
        "--list-queries",
        action="store_true",
        help="print the query catalogue and exit without calling anything",
    )
    return parser


@dataclass(slots=True)
class RunPlan:
    """The scrape plan for one run, produced before any credit is spent."""

    candidates: list[SearchHit]
    to_scrape: list[SearchHit]
    cached: list[SearchHit]
    skipped: list[SearchHit]
    deferred: list[SearchHit]


# --------------------------------------------------------------------------- #
# Phases
# --------------------------------------------------------------------------- #


def run_search(
    client: FirecrawlSearchClient,
    queries: tuple[SearchQuery, ...],
    *,
    limit: int,
    run: ResearchRun,
) -> list[SearchHit]:
    """Execute every selected query and return all hits, pre-filter."""
    log = get_logger()
    hits: list[SearchHit] = []
    for query in queries:
        run.queries_attempted += 1
        found = client.search(query, limit=limit)
        run.search_results_found += len(found)
        hits.extend(found)
    run.firecrawl_search_calls = client.call_count
    log.info("search complete: %d result(s) from %d query/queries", len(hits), run.queries_attempted)
    return hits


def plan_run(
    hits: list[SearchHit],
    coordinator: ScrapeCoordinator,
    *,
    max_pages: int,
    run: ResearchRun,
) -> RunPlan:
    """Filter, rank and cap *hits*, then predict each URL's resolution."""
    log = get_logger()
    result_filter = SearchResultFilter()
    outcome = result_filter.apply(hits)
    run.urls_skipped_duplicate += outcome.skipped_duplicate
    run.urls_skipped_filtered += outcome.skipped_filtered

    for url, reason in outcome.reasons.items():
        log.debug("skip %s (%s)", url, reason)

    ranked = rank_hits(classify_hits(outcome.kept))
    candidates, deferred = select_diverse(ranked, max_pages)
    if deferred:
        log.info(
            "page budget %d reached; %d candidate(s) deferred to a later run",
            max_pages,
            len(deferred),
        )
    families, domains = summarize_selection(candidates)
    log.info("selected %d page(s) across %d domain(s): %s", len(candidates), len(domains), families)

    plan = RunPlan(candidates=candidates, to_scrape=[], cached=[], skipped=[], deferred=deferred)
    for hit in candidates:
        predicted = coordinator.plan(hit)
        if predicted is ScrapeOutcome.CACHED:
            plan.cached.append(hit)
        elif predicted is ScrapeOutcome.SKIPPED:
            plan.skipped.append(hit)
        else:
            plan.to_scrape.append(hit)
    return plan


def print_plan(plan: RunPlan, *, searched: bool, force: bool) -> None:
    """Print the dry-run report to stdout.

    Shows each candidate's source family, domain and priority, which action it
    would trigger, and a breakdown of the families and domains the budget was
    actually spent on.
    """
    print()
    print("=" * 78)
    print("DRY RUN - no page was scraped and no LLM call was made")
    print("=" * 78)
    if not searched:
        print("Search was skipped (--no-search): zero API calls were made.")
        print("Run without --no-search to see real candidate URLs.")
        print()
        return

    status_of: dict[str, str] = {}
    for hit in plan.to_scrape:
        status_of[hit.canonical_url] = "SCRAPE"
    for hit in plan.cached:
        status_of[hit.canonical_url] = "CACHED"
    for hit in plan.skipped:
        status_of[hit.canonical_url] = "SKIP"

    print(f"\nSELECTED ({len(plan.candidates)}) - in scrape order\n")
    for index, hit in enumerate(plan.candidates, start=1):
        status = status_of.get(hit.canonical_url, "SCRAPE")
        print(
            f"[{index}] {hit.source_family:22} | {registrable_domain(hit.canonical_url):24} "
            f"| priority={hit.priority:<4} | {status}"
        )
        print(f"    {hit.canonical_url}")
        if hit.title:
            print(f"    {hit.title[:72]}")

    if plan.deferred:
        print(f"\nDEFERRED ({len(plan.deferred)}) - over the page budget, a later run picks these up\n")
        for hit in plan.deferred[:15]:
            print(
                f"    {hit.source_family:22} | {registrable_domain(hit.canonical_url):24} "
                f"| priority={hit.priority:<4} | DEFERRED"
            )
            print(f"      {hit.canonical_url}")
        if len(plan.deferred) > 15:
            print(f"    ... and {len(plan.deferred) - 15} more")

    families, domains = summarize_selection(plan.candidates)
    print("\nselected source families:")
    for family, count in families.items():
        print(f"  - {family}: {count}")
    print("\nselected domains:")
    for domain in domains:
        print(f"  - {domain}")

    print()
    print("-" * 78)
    print(f"candidate pages          {len(plan.candidates)}")
    print(f"deferred candidates      {len(plan.deferred)}")
    print(f"would scrape             {len(plan.to_scrape)}")
    print(f"served from cache        {len(plan.cached)}")
    print(f"skipped (already seen)   {len(plan.skipped)}")
    print(f"planned page count       {len(plan.to_scrape) + len(plan.cached)}  (would reach the extractor)")
    print(f"estimated scrape credits {len(plan.candidates) if force else len(plan.to_scrape)}")
    print(f"estimated LLM calls      >= {len(plan.to_scrape) + len(plan.cached)}  (one per content chunk)")
    print("-" * 78)
    print()


def collect_evidence(
    plan: RunPlan,
    coordinator: ScrapeCoordinator,
    extractor: EvidenceExtractor,
    *,
    run: ResearchRun,
) -> list[RawEvidence]:
    """Scrape each planned page and extract evidence from it.

    A failure on one page is recorded and the loop continues: one bad page must
    not end the research run.
    """
    log = get_logger()
    pages: list[RawPage] = []
    collected: list[RawEvidence] = []

    for index, hit in enumerate(plan.candidates, start=1):
        log.info("[%d/%d] %s", index, len(plan.candidates), hit.canonical_url)
        result = coordinator.resolve(hit)

        if result.outcome is ScrapeOutcome.SCRAPED:
            run.pages_scraped += 1
        elif result.outcome is ScrapeOutcome.CACHED:
            run.pages_loaded_from_cache += 1
        elif result.outcome is ScrapeOutcome.FAILED:
            run.pages_failed += 1
            continue
        else:
            continue

        if result.page is None:
            continue
        if result.outcome is ScrapeOutcome.SCRAPED:
            pages.append(result.page)

        try:
            collected.extend(extractor.extract_from_page(result.page))
        except Exception as exc:  # noqa: BLE001 - never let one page end the run
            log.exception("extraction crashed on %s: %s", hit.canonical_url, exc)

    if pages:
        storage.append_raw_pages(pages)
        log.info("appended %d page(s) to %s", len(pages), config.RAW_PAGES_PATH.name)

    run.firecrawl_scrape_calls = getattr(coordinator, "_client").call_count if coordinator._client else 0
    run.llm_calls = extractor.stats.llm_calls
    return collected


def finalize_evidence(raw_records: list[RawEvidence], *, run: ResearchRun) -> list[ProcessedEvidence]:
    """Assign ids, quality, independence groups and duplicate links, then store.

    Every field added here is computed by deterministic code - never by the
    extraction model.
    """
    log = get_logger()
    retrieved_at = utc_now_iso()

    processed = [
        ProcessedEvidence.from_raw(
            record,
            evidence_id=evidence_id(record.source_url, record.claim),
            retrieved_at=retrieved_at,
            source_quality=get_source_quality(record.source_family),
            independence_group=independence_group_for(record.source_url),
        )
        for record in raw_records
    ]

    # Collapse records this run produced twice for the same URL and claim.
    unique: dict[str, ProcessedEvidence] = {}
    for record in processed:
        unique.setdefault(record.evidence_id, record)
    processed = list(unique.values())

    # Compare against stored records in the same origin documents so a repeated
    # run over one thread does not re-append near-duplicates.
    groups = {record.independence_group for record in processed}
    previously_stored = storage.load_processed_in_groups(groups)
    report = mark_duplicates(previously_stored + processed, threshold=config.DUPLICATE_SIMILARITY_THRESHOLD)

    run.evidence_records_created = len(processed)
    run.evidence_duplicates_found = sum(1 for record in processed if record.duplicate_of)

    written = storage.append_processed_evidence(processed)
    log.info(
        "evidence: %d record(s) from %d independent source(s), %d marked duplicate, %d written",
        len(processed),
        dedup.count_independent_sources(processed),
        run.evidence_duplicates_found,
        written,
    )
    if report.cross_source_matches:
        log.info("%d cross-source corroboration pair(s) retained", len(report.cross_source_matches))
    return processed


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #


def execute(args: argparse.Namespace, settings: Settings) -> int:
    """Run one pipeline execution. Returns a process exit code."""
    log = get_logger()
    run = ResearchRun(
        run_id=f"run-{utc_now_iso().replace(':', '').replace('-', '')}-{uuid.uuid4().hex[:6]}",
        started_at=utc_now_iso(),
        topic=args.topic or (f"category:{args.category}" if args.category else "all"),
    )

    queries = select_queries(topic=args.topic, category=args.category)
    if not queries:
        log.error("no queries match topic=%r category=%r", args.topic, args.category)
        return 2

    log.info(
        "run %s | %d query/queries | search_limit=%d | max_pages=%d | dry_run=%s | force=%s",
        run.run_id,
        len(queries),
        settings.search_limit,
        settings.max_pages_per_run,
        args.dry_run,
        args.force,
    )
    log.info(
        "throttle: %.1fs between Firecrawl requests, up to %d attempt(s) each",
        settings.search_delay_seconds,
        settings.firecrawl_max_retries,
    )

    cache = PageCache()
    visited = VisitedUrlStore()

    # -- search ------------------------------------------------------------- #
    hits: list[SearchHit] = []
    searched = False
    search_client: FirecrawlSearchClient | None = None
    if not (args.dry_run and args.no_search):
        search_client = FirecrawlSearchClient(
            settings.require_firecrawl_key(),
            delay_seconds=settings.search_delay_seconds,
            max_retries=settings.firecrawl_max_retries,
            max_sleep=settings.max_rate_limit_sleep,
        )
        hits = run_search(search_client, queries, limit=settings.search_limit, run=run)
        searched = True

    # -- plan --------------------------------------------------------------- #
    scrape_client = None
    if not args.dry_run:
        # Share the search client's limiter so searches and scrapes draw on one
        # per-minute budget instead of two independent ones.
        scrape_client = FirecrawlScraperClient(
            settings.require_firecrawl_key(),
            delay_seconds=settings.search_delay_seconds,
            max_retries=settings.firecrawl_max_retries,
            max_sleep=settings.max_rate_limit_sleep,
            limiter=search_client.limiter if search_client is not None else None,
        )
    coordinator = ScrapeCoordinator(client=scrape_client, cache=cache, visited=visited, force=args.force)
    plan = plan_run(hits, coordinator, max_pages=settings.max_pages_per_run, run=run)

    if args.dry_run:
        print_plan(plan, searched=searched, force=args.force)
        run.finished_at = utc_now_iso()
        storage.append_research_run(run)
        visited.save()
        return 0

    if not plan.candidates:
        log.warning("nothing to do: no candidate URL survived filtering")
        run.finished_at = utc_now_iso()
        storage.append_research_run(run)
        return 0

    # -- scrape and extract -------------------------------------------------- #
    extractor = EvidenceExtractor(get_provider(settings), settings)
    raw_records = collect_evidence(plan, coordinator, extractor, run=run)

    # -- normalize, score, group, deduplicate, store ------------------------- #
    if raw_records:
        finalize_evidence(raw_records, run=run)
    else:
        log.warning("no evidence extracted this run")

    visited.save()
    run.finished_at = utc_now_iso()
    storage.append_research_run(run)

    log.info("run finished")
    for line in run.summary_lines():
        log.info("  %s", line)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, configure logging and dispatch to :func:`execute`."""
    args = build_parser().parse_args(argv)

    config.ensure_directories()
    log = setup_logging(config.LOG_PATH, verbose=args.verbose)

    if args.list_queries:
        print(f"\n{len(ALL_QUERIES)} catalogued queries by topic: {queries_by_topic()}\n")
        for query in ALL_QUERIES:
            print(f"  [{query.topic:13}] [{query.category:21}] {query.text}")
        print()
        return 0

    for name, value in (
        ("--max-pages", args.max_pages),
        ("--search-limit", args.search_limit),
        ("--max-retries", args.max_retries),
    ):
        if value is not None and value <= 0:
            log.error("%s must be greater than zero", name)
            return 2
    if args.search_delay is not None and args.search_delay < 0:
        log.error("--search-delay cannot be negative")
        return 2
    if args.no_search and not args.dry_run:
        log.error("--no-search is only meaningful together with --dry-run")
        return 2

    try:
        settings = config.load_settings(
            search_limit=args.search_limit,
            max_pages=args.max_pages,
            search_delay=args.search_delay,
            max_retries=args.max_retries,
        )
        return execute(args, settings)
    except ConfigError as exc:
        log.error("configuration problem: %s", exc)
        return 2
    except KeyboardInterrupt:  # pragma: no cover
        log.warning("interrupted by user; partial results remain on disk")
        return 130


if __name__ == "__main__":
    sys.exit(main())
