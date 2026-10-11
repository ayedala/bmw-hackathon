"""Report the metrics of one completed run per topic, scoped accurately.

Read-only. Reads the run ledger, the visited-URL ledger and the evidence store;
makes no Firecrawl call, no LLM call and no change to any pipeline state.

Usage, from inside this folder::

    python report_run.py infotainment comfort
    python report_run.py --mode reprocess-cache infotainment

Scoping evidence to a single run
--------------------------------
A run record carries counters, not a URL list, so the rows a run wrote are
identified two independent ways and intersected when both are available:

1. **Ledger-derived URLs.** ``visited_urls.json`` records ``last_seen_at`` per
   URL, so the URLs touched inside a run's window are known. Evidence is
   matched on the *canonicalized* ``source_url``, because the ledger is keyed
   on canonical URLs (``adac.de/x``) while evidence stores the resolved one
   (``https://www.adac.de/x/``).
2. **Bounded timestamp window**, ``started_at <= retrieved_at <= finished_at``.
   Every row a run writes shares one ``retrieved_at`` - the finalize step
   stamps them together - so a *bounded* window reproduces a run exactly.

The window must be bounded at both ends. An open-ended ``>= started_at`` filter
attributes every later run's rows to the earlier one: on this project's own
data it credited a run that created 0 records with all 107 rows in the store.

Evidence is **never** filtered by evidence topic. The pipeline deliberately
keeps cross-topic evidence from a page it has already paid for, so the comfort
and range records a charging page yields belong to that charging run and are
counted in it. Topic is reported as a distribution, never as a filter.
"""

from __future__ import annotations

import argparse
import json
import pathlib
from collections import Counter
from typing import Any

import config
from utils import canonicalize_url

#: Counters printed for every run, in a deliberate reading order: cost first,
#: then acquisition, then per-page outcomes, then yield.
FIELDS: tuple[tuple[str, str], ...] = (
    ("firecrawl search calls", "firecrawl_search_calls"),
    ("firecrawl scrape calls", "firecrawl_scrape_calls"),
    ("llm calls", "llm_calls"),
    ("queries attempted", "queries_attempted"),
    ("search results found", "search_results_found"),
    ("urls skipped (duplicate)", "urls_skipped_duplicate"),
    ("urls skipped (filtered)", "urls_skipped_filtered"),
    ("pages scraped", "pages_scraped"),
    ("pages from cache", "pages_loaded_from_cache"),
    ("scrape failures", "pages_failed"),
    ("thin pages", "pages_skipped_thin"),
    ("off-topic pages", "pages_skipped_irrelevant"),
    ("extraction failures", "pages_extraction_failed"),
    ("zero-evidence pages", "pages_zero_evidence"),
    ("pages with evidence", "pages_with_evidence"),
    ("chunks processed", "chunks_processed"),
    ("chunks failed", "chunks_failed"),
    ("evidence created", "evidence_records_created"),
    ("duplicates detected", "evidence_duplicates_found"),
    ("evidence per good page", "evidence_per_extracted_page"),
    ("out-of-scope filtered", "records_filtered_out_of_scope"),
)


def read_jsonl(path: pathlib.Path) -> list[dict[str, Any]]:
    """Read a JSONL file, skipping blank and unparsable lines."""
    if not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def read_json(path: pathlib.Path) -> dict[str, Any]:
    """Read a JSON object, returning ``{}`` when missing or unparsable."""
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def latest_run(runs: list[dict[str, Any]], topic: str, mode: str) -> dict[str, Any] | None:
    """The most recent finished run for *topic* in *mode*."""
    matches = [
        run for run in runs
        if run.get("topic") == topic
        and run.get("mode", "search") == mode
        and run.get("finished_at")
    ]
    return matches[-1] if matches else None


def scope_evidence(
    run: dict[str, Any],
    evidence: list[dict[str, Any]],
    visited: dict[str, Any],
) -> tuple[list[dict[str, Any]], str, str | None]:
    """Return ``(rows, method, warning)`` for the evidence *run* wrote.

    Intersects the two independent scopes when both are populated, so a URL a
    later run re-touched cannot drag its rows into this report, and a row
    written in this window cannot be attributed elsewhere.
    """
    started = run["started_at"]
    finished = run.get("finished_at") or "9999-12-31T23:59:59Z"

    by_window = [
        row for row in evidence
        if started <= str(row.get("retrieved_at", "")) <= finished
    ]

    run_urls = {
        key for key, entry in visited.items()
        if isinstance(entry, dict) and started <= str(entry.get("last_seen_at", "")) <= finished
    }
    by_ledger = (
        [row for row in evidence if canonicalize_url(str(row.get("source_url", ""))) in run_urls]
        if run_urls else []
    )

    if by_ledger and by_window:
        window_ids = {row.get("evidence_id") for row in by_window}
        agreed = [row for row in by_ledger if row.get("evidence_id") in window_ids]
        warning = None
        if len(agreed) != len(by_window) or len(agreed) != len(by_ledger):
            warning = (
                f"scopes disagree: ledger matched {len(by_ledger)} row(s), "
                f"timestamp window matched {len(by_window)}, intersection {len(agreed)}. "
                "A URL re-touched by a later run, or a cache-served page from an "
                "earlier one, explains the gap; the intersection is used."
            )
        if agreed:
            return agreed, "ledger URLs intersected with the bounded timestamp window", warning
        return (
            by_window,
            "bounded timestamp window (ledger intersection was empty)",
            warning or "ledger and timestamp scopes shared no rows; using timestamps",
        )
    if by_ledger:
        return by_ledger, "ledger-derived URLs (no timestamp match)", None
    if by_window:
        return by_window, "bounded timestamp window (no ledger match)", None
    return [], "no evidence matched this run", None


def host_of(url: str) -> str:
    """Registrable-ish host of *url*, for the domain breakdown."""
    canonical = canonicalize_url(url)
    parts = canonical.split("/")
    return parts[2] if len(parts) > 2 else canonical or "unknown"


def report_topic(
    topic: str,
    mode: str,
    runs: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    visited: dict[str, Any],
) -> None:
    """Print the full report for one topic's latest run."""
    print("=" * 80)
    print(f"RUN METRICS - {topic}  (mode={mode})")
    print("=" * 80)

    run = latest_run(runs, topic, mode)
    if run is None:
        print(f"  no finished run found for topic={topic!r} mode={mode!r}\n")
        return

    print(f"  run_id                   {run['run_id']}")
    print(f"  window                   {run['started_at']} -> {run['finished_at']}")
    for label, key in FIELDS:
        if key in run:
            print(f"  {label:24} {run[key]}")

    scoped, method, warning = scope_evidence(run, evidence, visited)
    print(f"\n  evidence scoped by       {method}")
    if warning:
        print(f"  WARNING                  {warning}")
    print(f"  evidence rows in scope   {len(scoped)}")
    if not scoped:
        print()
        return

    live = [row for row in scoped if not row.get("duplicate_of")]
    groups = {row.get("independence_group") for row in live}
    print(f"  independent sources      {len(groups)}")
    print(f"  rows marked duplicate    {len(scoped) - len(live)}")

    print("\n  source families (records):")
    for family, count in Counter(row.get("source_family") for row in scoped).most_common():
        print(f"    {str(family):26} {count}")

    print("  domains (records):")
    for host, count in Counter(host_of(str(row.get("source_url", ""))) for row in scoped).most_common():
        print(f"    {host[:44]:46} {count}")

    print("  evidence topics (cross-topic kept on purpose):")
    for name, count in Counter(row.get("topic") for row in scoped).most_common():
        print(f"    {str(name):26} {count}")

    units = Counter(row.get("numeric_unit") for row in scoped if row.get("numeric_unit"))
    if units:
        print("  numeric units:")
        for unit, count in units.most_common():
            print(f"    {str(unit):26} {count}")
    print()


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    parser = argparse.ArgumentParser(
        prog="python report_run.py",
        description="Report metrics for the latest run of each topic, scoped to that run.",
    )
    parser.add_argument("topics", nargs="+", help="topics to report")
    parser.add_argument(
        "--mode", default="search", choices=["search", "reprocess-cache"],
        help="which run mode to report (default: search)",
    )
    args = parser.parse_args(argv)

    runs = read_jsonl(config.RESEARCH_RUNS_PATH)
    visited = read_json(config.VISITED_URLS_PATH)
    store = (
        config.CACHE_REPROCESS_EVIDENCE_PATH
        if args.mode == "reprocess-cache"
        else config.PROCESSED_EVIDENCE_PATH
    )
    evidence = read_jsonl(store)

    for topic in args.topics:
        report_topic(topic, args.mode, runs, evidence, visited)

    print("=" * 80)
    print("LEDGER / STORE")
    print("=" * 80)
    print(f"  evidence store           {store.name} ({len(evidence)} rows)")
    print(f"  visited entries          {len(visited)}")
    statuses = Counter(
        entry.get("status") for entry in visited.values() if isinstance(entry, dict)
    )
    print(f"  by status                {dict(statuses)}")
    terminal = [
        key for key, entry in visited.items()
        if isinstance(entry, dict) and (entry.get("terminal") or entry.get("status") in ("thin", "unsupported"))
    ]
    print(f"  terminal flagged         {len(terminal)}")
    for key in terminal:
        entry = visited[key]
        print(f"    [{entry.get('status')}] {key[:62]}")
    print(f"  cached pages on disk     {len(list(config.CACHE_DIR.glob('*.json')))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
