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
from pathlib import Path

import config
import dedup
import storage
from config import ConfigError, Settings
from dedup import independence_group_for, mark_duplicates
from extractor import EvidenceExtractor, ExtractionOutcome
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
from utils import (
    canonicalize_url,
    evidence_id,
    get_logger,
    registrable_domain,
    setup_logging,
    utc_now_iso,
)


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
        "--chunk-chars",
        type=int,
        metavar="N",
        help=(
            "characters of page text per extraction request "
            f"(default {config.DEFAULT_EXTRACTION_CHUNK_CHARS}, env EXTRACTION_CHUNK_CHARS)"
        ),
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
        "--reprocess-cache",
        action="store_true",
        help=(
            "replay already-cached pages through the current post-scrape pipeline. "
            "Makes zero Firecrawl calls of any kind and needs no Firecrawl key; "
            "writes to data/processed/cache_reprocess_evidence.jsonl"
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
    force: bool = False,
) -> RunPlan:
    """Filter, rank and cap *hits*, then predict each URL's resolution.

    URLs carrying a terminal outcome are removed before the page budget is
    spent, unless *force* is set.
    """
    log = get_logger()
    result_filter = SearchResultFilter()
    outcome = result_filter.apply(hits)
    run.urls_skipped_duplicate += outcome.skipped_duplicate
    run.urls_skipped_filtered += outcome.skipped_filtered

    for url, reason in outcome.reasons.items():
        log.debug("skip %s (%s)", url, reason)

    ranked = rank_hits(classify_hits(outcome.kept))

    # Drop URLs already judged deterministically unusable *before* selection,
    # so a thin or unsupported page cannot take a slot from a fresh candidate.
    # Only terminal verdicts qualify: an extraction failure, a zero-evidence
    # page or a temporary provider error may all succeed later.
    if not force:
        live = [hit for hit in ranked if not coordinator.is_terminal(hit.canonical_url)]
        terminal_count = len(ranked) - len(live)
        if terminal_count:
            run.urls_skipped_filtered += terminal_count
            log.info(
                "%d candidate(s) skipped: terminal outcome recorded earlier "
                "(thin or unsupported); their budget slots go to other URLs",
                terminal_count,
            )
        ranked = live

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
) -> list[ProcessedEvidence]:
    """Scrape each planned page and extract evidence from it.

    A failure on one page is recorded and the loop continues: one bad page must
    not end the research run.

    Everything a page produces is persisted **before the next page starts**:
    its raw markdown, its evidence, its visited-ledger entry, any terminal
    verdict, and a checkpoint of the run counters. At roughly 17 minutes per
    page, writing only at the end means one signal costs hours of extraction -
    which is what happened to the first infotainment run.

    Re-running is safe because every write is idempotent: ``evidence_id`` is a
    hash of canonical URL plus normalized claim, so the store skips rows it
    already holds, and the ledger is keyed by canonical URL.

    Returns the **already-finalized** records. The caller must not finalize
    them again.
    """
    log = get_logger()
    collected: list[RawEvidence] = []
    total = len(plan.candidates)

    for index, hit in enumerate(plan.candidates, start=1):
        log.info("[%d/%d] %s", index, len(plan.candidates), hit.canonical_url)
        result = coordinator.resolve(hit)

        if result.outcome is ScrapeOutcome.SCRAPED:
            run.pages_scraped += 1
        elif result.outcome is ScrapeOutcome.CACHED:
            run.pages_loaded_from_cache += 1
        elif result.outcome is ScrapeOutcome.FAILED:
            run.pages_failed += 1
            # The coordinator already recorded the outcome, including any
            # terminal "unsupported" verdict, so flush it before moving on.
            coordinator.save_ledger()
            storage.write_run_checkpoint(run, pages_done=index, pages_total=total)
            continue
        else:
            storage.write_run_checkpoint(run, pages_done=index, pages_total=total)
            continue

        if result.page is None:
            continue
        if result.outcome is ScrapeOutcome.SCRAPED:
            # Persist the markdown before extraction begins: the scrape is the
            # part that cost a Firecrawl credit.
            storage.append_raw_pages([result.page])

        try:
            extraction = extractor.extract_from_page(result.page)
        except Exception as exc:  # noqa: BLE001 - never let one page end the run
            run.pages_extraction_failed += 1
            log.exception("extraction crashed on %s: %s", hit.canonical_url, exc)
            storage.write_run_checkpoint(run, pages_done=index, pages_total=total)
            continue

        run.chunks_processed += extraction.chunks
        run.chunks_failed += extraction.chunks_failed
        if extraction.outcome is ExtractionOutcome.SKIPPED_THIN:
            run.pages_skipped_thin += 1
            # A page with almost no text will have almost no text next time:
            # record it so it stops competing for a page-budget slot. Off-topic,
            # extraction-failed and zero-evidence pages are *not* marked, since
            # any of those can change.
            coordinator.mark_terminal(
                hit.canonical_url, status="thin", detail=extraction.reason[:300],
                topic=hit.topic,
            )
        elif extraction.outcome is ExtractionOutcome.SKIPPED_IRRELEVANT:
            run.pages_skipped_irrelevant += 1
        elif extraction.outcome is ExtractionOutcome.EXTRACTION_FAILED:
            run.pages_extraction_failed += 1
        elif extraction.outcome is ExtractionOutcome.NO_EVIDENCE:
            run.pages_zero_evidence += 1
        else:
            run.pages_with_evidence += 1

        # Evidence first, then the ledger, then the checkpoint. A crash between
        # these writes can only lose *bookkeeping* for work already stored - it
        # can never lose the evidence itself.
        run.llm_calls = extractor.stats.llm_calls
        run.records_filtered_out_of_scope = extractor.stats.filtered_out_of_scope
        run.firecrawl_scrape_calls = coordinator.scrape_call_count
        if extraction.records:
            collected.extend(finalize_evidence(extraction.records, run=run))
        coordinator.save_ledger()
        storage.write_run_checkpoint(run, pages_done=index, pages_total=total)

    run.firecrawl_scrape_calls = coordinator.scrape_call_count
    run.llm_calls = extractor.stats.llm_calls
    run.records_filtered_out_of_scope = extractor.stats.filtered_out_of_scope
    log.info(
        "pages: %d with evidence, %d thin, %d off-topic, %d extraction-failed, %d zero-evidence",
        run.pages_with_evidence,
        run.pages_skipped_thin,
        run.pages_skipped_irrelevant,
        run.pages_extraction_failed,
        run.pages_zero_evidence,
    )
    return collected


def finalize_evidence(
    raw_records: list[RawEvidence],
    *,
    run: ResearchRun,
    store_path: Path | None = None,
    rebuild_source_urls: set[str] | None = None,
) -> list[ProcessedEvidence]:
    """Assign ids, quality, independence groups and duplicate links, then store.

    Every field added here is computed by deterministic code - never by the
    extraction model.

    Args:
        store_path: Evidence store to write. Defaults to the main store.
        rebuild_source_urls: When given, rows for these source URLs are
            replaced rather than appended, which is what makes a cache
            reprocess run idempotent. Cross-source duplicate marking also reads
            from *store_path* so a reprocess run compares against its own
            output, not the scrape store.
    """
    log = get_logger()
    target = store_path or config.PROCESSED_EVIDENCE_PATH
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
    previously_stored = storage.load_processed_in_groups(groups, path=target)
    if rebuild_source_urls:
        # Those rows are about to be replaced, so they must not act as keepers
        # that mark this run's fresh records as duplicates of themselves.
        previously_stored = [
            row for row in previously_stored if row.source_url not in rebuild_source_urls
        ]
    report = mark_duplicates(previously_stored + processed, threshold=config.DUPLICATE_SIMILARITY_THRESHOLD)

    # Accumulate: this is called once per page in the live flow, so assigning
    # would leave only the last page's figures.
    run.evidence_records_created += len(processed)
    run.evidence_duplicates_found += sum(1 for record in processed if record.duplicate_of)
    if run.pages_with_evidence:
        run.evidence_per_extracted_page = round(
            run.evidence_records_created / run.pages_with_evidence, 2
        )

    if rebuild_source_urls is not None:
        _, written = storage.rebuild_processed_evidence(
            processed, path=target, replace_source_urls=rebuild_source_urls
        )
    else:
        written = storage.append_processed_evidence(processed, path=target)
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
# Cache-only reprocessing
# --------------------------------------------------------------------------- #


def _ledger_index(visited: VisitedUrlStore) -> dict[str, dict[str, str]]:
    """Canonical URL -> recorded topic/query/title, read-only.

    The cache payload stores the page, not the search that found it, so topic
    and query come from the visited-URL ledger. The ledger is only ever read
    here; a reprocess run never writes it.
    """
    index: dict[str, dict[str, str]] = {}
    for key, entry in getattr(visited, "_entries", {}).items():
        if isinstance(entry, dict):
            index[key] = {
                "topic": str(entry.get("topic") or ""),
                "query": str(entry.get("query") or ""),
                "title": str(entry.get("title") or ""),
            }
    return index


def load_cached_pages(
    *, topic: str | None, cache: PageCache, visited: VisitedUrlStore
) -> tuple[list[RawPage], int]:
    """Rebuild :class:`RawPage` objects from every payload in ``data/cache/``.

    Discovery is cache-first: every ``*.json`` in the cache directory is a
    page, whatever the ledger says. The ledger only supplies the topic and
    query, so a cache entry with no ledger record is still reprocessable when
    no ``--topic`` filter is in force.

    Page fields are reconstructed exactly as the scrape path builds them, so a
    reprocessed record lands on the same ``source_url`` - and therefore the same
    ``evidence_id`` - as the original run produced.

    Returns:
        ``(pages, skipped_by_topic_filter)``, pages ordered by cache filename
        so a reprocess run is deterministic.
    """
    log = get_logger()
    index = _ledger_index(visited)
    pages: list[RawPage] = []
    skipped = 0

    for path in sorted(cache.directory.glob("*.json")):
        payload = storage.load_json(path, default=None)
        if not isinstance(payload, dict) or not payload.get("markdown"):
            log.warning("cache file %s has no markdown; skipping", path.name)
            continue

        canonical = str(payload.get("canonical_url") or "")
        source_url = str(payload.get("source_url") or canonical)
        if not canonical:
            canonical = canonicalize_url(source_url)
        recorded = index.get(canonical, {})
        page_topic = recorded.get("topic", "")

        if topic is not None and page_topic != topic:
            skipped += 1
            log.debug(
                "cache %s skipped: recorded topic %r does not match --topic %r",
                path.name, page_topic or "unknown", topic,
            )
            continue

        pages.append(
            RawPage(
                url=source_url,
                resolved_url=source_url,
                canonical_url=canonical,
                title=str(payload.get("title") or recorded.get("title") or ""),
                source_name=str(payload.get("source_name") or registrable_domain(source_url)),
                published_at=payload.get("published_at"),
                query=recorded.get("query", ""),
                topic=page_topic or (topic or ""),
                retrieved_at=str(payload.get("cached_at") or utc_now_iso()),
                markdown=str(payload.get("markdown") or ""),
            )
        )
    return pages, skipped


def print_run_metrics(run: ResearchRun, *, header: str) -> None:
    """Print the run counters, with the zero-credit facts stated first."""
    print()
    print("=" * 78)
    print(header)
    print("=" * 78)
    print(f"  firecrawl search calls   {run.firecrawl_search_calls}")
    print(f"  firecrawl scrape calls   {run.firecrawl_scrape_calls}")
    print(f"  cached pages processed   {run.pages_loaded_from_cache}")
    print("  " + "-" * 40)
    print(f"  pages skipped thin       {run.pages_skipped_thin}")
    print(f"  pages skipped irrelevant {run.pages_skipped_irrelevant}")
    print(f"  extraction failures      {run.pages_extraction_failed}")
    print(f"  zero-evidence pages      {run.pages_zero_evidence}")
    print(f"  pages with evidence      {run.pages_with_evidence}")
    print("  " + "-" * 40)
    print(f"  chunks processed         {run.chunks_processed}")
    print(f"  chunks failed            {run.chunks_failed}")
    print(f"  out-of-scope filtered    {run.records_filtered_out_of_scope}")
    print(f"  evidence created         {run.evidence_records_created}")
    print(f"  evidence duplicates      {run.evidence_duplicates_found}")
    print(f"  evidence per good page   {run.evidence_per_extracted_page:.2f}")
    print(f"  llm calls                {run.llm_calls}")
    print("=" * 78)
    print()


def reprocess_cache(args: argparse.Namespace, settings: Settings, run: ResearchRun) -> int:
    """Replay cached pages through the current post-scrape pipeline.

    Spends no Firecrawl credits: neither provider adapter is constructed, so
    there is no client that could issue a request, and no Firecrawl key is
    required. Cache files and the visited ledger are read but never written.
    """
    log = get_logger()
    run.mode = "reprocess-cache"

    print()
    print("=" * 78)
    print("CACHE-ONLY REPROCESS - no Firecrawl search, no Firecrawl scrape, 0 credits")
    print("=" * 78)

    cache = PageCache()
    visited = VisitedUrlStore()
    pages, skipped_by_topic = load_cached_pages(topic=args.topic, cache=cache, visited=visited)

    if skipped_by_topic:
        log.info(
            "%d cached page(s) skipped: their recorded topic does not match --topic %r",
            skipped_by_topic, args.topic,
        )
    if not pages:
        log.warning(
            "no cached pages to reprocess in %s%s",
            config.CACHE_DIR,
            f" for topic {args.topic!r}" if args.topic else "",
        )
        run.finished_at = utc_now_iso()
        storage.append_research_run(run)
        print_run_metrics(run, header="CACHE-ONLY REPROCESS - nothing to do")
        return 0

    print(f"\nreprocessing {len(pages)} cached page(s) from {config.CACHE_DIR}:\n")
    for page in pages:
        print(f"  {len(page.markdown):>7} chars  {page.canonical_url}")
    print()

    extractor = EvidenceExtractor(get_provider(settings), settings)
    collected: list[RawEvidence] = []

    for index, page in enumerate(pages, start=1):
        log.info("[%d/%d] %s", index, len(pages), page.canonical_url)
        run.pages_loaded_from_cache += 1
        try:
            extraction = extractor.extract_from_page(page)
        except Exception as exc:  # noqa: BLE001 - one page must not end the run
            run.pages_extraction_failed += 1
            log.exception("extraction crashed on %s: %s", page.canonical_url, exc)
            continue

        collected.extend(extraction.records)
        run.chunks_processed += extraction.chunks
        run.chunks_failed += extraction.chunks_failed
        if extraction.outcome is ExtractionOutcome.SKIPPED_THIN:
            run.pages_skipped_thin += 1
        elif extraction.outcome is ExtractionOutcome.SKIPPED_IRRELEVANT:
            run.pages_skipped_irrelevant += 1
        elif extraction.outcome is ExtractionOutcome.EXTRACTION_FAILED:
            run.pages_extraction_failed += 1
        elif extraction.outcome is ExtractionOutcome.NO_EVIDENCE:
            run.pages_zero_evidence += 1
        else:
            run.pages_with_evidence += 1

    run.llm_calls = extractor.stats.llm_calls
    run.records_filtered_out_of_scope = extractor.stats.filtered_out_of_scope
    # Both stay zero: no Firecrawl client was ever built in this mode.
    run.firecrawl_search_calls = 0
    run.firecrawl_scrape_calls = 0

    if collected:
        finalize_evidence(
            collected,
            run=run,
            store_path=config.CACHE_REPROCESS_EVIDENCE_PATH,
            rebuild_source_urls={page.resolved_url or page.url for page in pages},
        )
    else:
        log.warning("no evidence extracted from the cached pages")
        # Still rebuild, so a previous run's rows for these pages do not linger.
        storage.rebuild_processed_evidence(
            [],
            path=config.CACHE_REPROCESS_EVIDENCE_PATH,
            replace_source_urls={page.resolved_url or page.url for page in pages},
        )

    run.finished_at = utc_now_iso()
    storage.append_research_run(run)
    print_run_metrics(run, header="CACHE-ONLY REPROCESS - run metrics")
    print(f"output: {config.CACHE_REPROCESS_EVIDENCE_PATH}")
    print("the main store (external_evidence.jsonl) was not touched.\n")
    return 0


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

    if args.reprocess_cache:
        return reprocess_cache(args, settings, run)

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
    log.info(
        "extraction: %d-char chunks, %d-char overlap, min %d chars, "
        "relevance needs %d topic or %d vehicle term(s)",
        settings.extraction_chunk_chars,
        settings.extraction_chunk_overlap_chars,
        settings.min_content_chars,
        settings.min_topic_hits,
        settings.min_vehicle_hits,
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
    plan = plan_run(
        hits, coordinator, max_pages=settings.max_pages_per_run, run=run, force=args.force
    )

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
    # collect_evidence finalizes and stores each page's evidence as it goes, so
    # the records coming back are already ProcessedEvidence. Finalizing again
    # would re-wrap them and raise - which is exactly what aborted the first
    # completed infotainment run before it could write its run record.
    stored = collect_evidence(plan, coordinator, extractor, run=run)
    if stored:
        log.info(
            "stored %d evidence record(s) from %d independent source(s)",
            len(stored), dedup.count_independent_sources(stored),
        )
    else:
        log.warning("no evidence extracted this run")

    visited.save()
    run.finished_at = utc_now_iso()
    storage.append_research_run(run)
    # The run record is durable now, so the in-progress checkpoint is obsolete.
    storage.clear_run_checkpoint()

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
        ("--chunk-chars", args.chunk_chars),
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
    if args.reprocess_cache and args.dry_run:
        log.error("--reprocess-cache and --dry-run are different modes; pick one")
        return 2
    if args.reprocess_cache and args.force:
        log.error("--force has no meaning with --reprocess-cache: nothing is scraped")
        return 2

    try:
        settings = config.load_settings(
            search_limit=args.search_limit,
            max_pages=args.max_pages,
            chunk_chars=args.chunk_chars,
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
