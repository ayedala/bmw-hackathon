# External Research Pipeline

Collects **external public-web evidence** about the BMW 5 Series / i5 (G60) for
product research, and stores it as traceable, deduplicated, source-scored
records.

| | |
|---|---|
| Target vehicle | BMW 5 Series / BMW i5, generation **G60** |
| Primary market | **Germany** (`DE`) |
| Time horizon | roughly **3–5 years** ahead |
| Topics | `infotainment`, `charging`, `comfort`, `market_trend` |

## 1. What this pipeline does

It runs a fixed sequence: search the web, filter the results, scrape the pages
that survive, extract atomic claims with an LLM, then normalize, score, group
and deduplicate those claims deterministically and append them to JSONL.

**What it explicitly does not do:**

- It **does not generate product requirements.** Not one.
- It does not assign requirement priorities or compute a priority score.
- It does not decide which evidence "wins", or resolve contradictions.
- It does not generalize a single owner comment into a statement about
  customers in general.

The output is an evidence layer. Combining it with internal BMW data and
deriving requirements from it is a separate, later step that a human owns.

A deliberate consequence: **supporting and contradicting evidence are both
kept.** A page that praises ride comfort and a page that complains about wind
noise both become records. Nothing here collapses them into a verdict.

## 2. Module boundary

This optional collector lives under `src/bmw_pm/data_pipeline/web_research/` alongside the workbook and YouTube ingestion code. It keeps its own dependencies, local `.env`, cache and JSONL storage. Run scripts from this directory; imports remain local to the collector. The core package and Docker image exclude this standalone tool, so collector credentials and caches are not bundled.

Collection does not establish an automatic integration with requirement cards. A canonical evidence importer and reviewed vehicle/market mappings are still needed. Raw customer material must remain out of Git; this collector acquires public web evidence only.

## 3. Architecture

```
queries.py          50 catalogued queries, each tagged with a topic
      |
      v
search.py           Firecrawl Search  ->  SearchHit records
      |
      v
search.py           filter                  <- no credits spent here
      |                (deny-lists, listing pages, topic relevance, dupes)
      v
source_scoring.py   classify domain -> source family -> priority
      |
      v
search.py           rank by priority, then select for source diversity
      |                (round 1 new family+domain, round 2 new domain,
      |                 round 3 global rank; the rest is deferred)
      v
scraper.py          canonicalize -> visited? -> cached? -> only then scrape
      |
      v
data/raw/           raw_pages.jsonl (markdown + provenance)
      |
      v
extractor.py        trim -> thin gate -> relevance gate   <- no LLM call yet
      |                (relevance.py, deterministic)
      v
extractor.py        chunk (7k) -> LLM per chunk -> merge + dedup
      |                (llm_provider.py: OpenAI or Anthropic;
      |                 a truncated chunk is retried as two halves)
      v
models.py           Pydantic validation against the controlled vocabulary
      |
      v
source_scoring.py   deterministic source_family + source_quality
      |
      v
dedup.py            independence groups, then duplicate_of within a group
      |
      v
data/processed/      external_evidence.jsonl
data/metadata/       research_runs.jsonl, visited_urls.json
```

### What the LLM is allowed to decide

The division of labour is the point of the design, so it is enforced in code
rather than in the prompt.

| Decision | Owner |
|---|---|
| Which claims a page contains | LLM |
| Topic / subtopic of a claim | LLM (validated against the vocabulary) |
| Numeric value and unit | LLM (copied, never computed) |
| `source_url`, `source_name`, `source_title` | **Code** — from page metadata |
| `published_at` | **Code** — the page's own metadata; the model's value is used only when the page has none |
| `source_family` | **Code** — domain table in `source_scoring.py` |
| `source_quality` | **Code** — fixed table |
| `evidence_id` | **Code** — hash of URL + claim |
| `independence_group` | **Code** — hash of origin document |
| `duplicate_of` | **Code** — similarity within one group |

The extraction JSON schema has no `source_url` field at all, so the model
cannot attribute a claim to a page that was never scraped. It may offer a
`source_family_hint` as extraction context, but the hint does not affect source
family or quality scoring; unknown domains deterministically remain `other`.

Scraped page text is treated as **untrusted data**. It is delimited and labelled
in the prompt, and the model is instructed to ignore any instruction found
inside it and report it as content.

### Swapping out Firecrawl

The integration sits behind two adapters, `FirecrawlSearchClient`
(`search.py`) and `FirecrawlScraperClient` (`scraper.py`). Another provider
means writing two classes with the same `search()` / `fetch()` signatures.
Nothing downstream imports `firecrawl`.

## 4. Installation

Python 3.11 or newer.

**macOS / Linux**

```bash
cd src/bmw_pm/data_pipeline/web_research
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Windows**

```bat
cd src/bmw_pm/data_pipeline/web_research
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

The venv goes inside this folder and is gitignored.

### Dependencies

| Package | Why |
|---|---|
| `firecrawl-py>=4.50.0` | Search + Scrape |
| `pydantic>=2.7` | Every record schema |
| `python-dotenv` | `.env` loading |
| `tenacity` | Retry with exponential backoff |
| `rapidfuzz` | Claim similarity for deduplication |
| `openai>=3.0` *or* `anthropic>=1.0` | Extraction — only the one you use |

Two notes on the dependency list:

- **`requests` is intentionally absent.** All HTTP goes through the Firecrawl and
  LLM SDKs, so adding it would be an unused dependency.
- `python-dotenv`, `tenacity` and `rapidfuzz` have **standard-library fallbacks**
  (`.env` parser, retry loop, `difflib`) so `--dry-run` works on a bare
  interpreter. Install them anyway: the `difflib` fallback is stricter than
  `rapidfuzz` and will miss near-duplicate claims.

## 5. Environment configuration

**Create `.env` inside this folder** — `src/bmw_pm/data_pipeline/web_research/.env`, right
next to `main.py`. Not at the repository root.

```bash
cd src/bmw_pm/data_pipeline/web_research
cp .env.example .env
```

Then edit it:

```ini
FIRECRAWL_API_KEY=fc-...            # required

LLM_PROVIDER=openai                 # or: anthropic

OPENAI_API_KEY=sk-...               # only if LLM_PROVIDER=openai
OPENAI_MODEL=gpt-5-mini

ANTHROPIC_API_KEY=                  # only if LLM_PROVIDER=anthropic
ANTHROPIC_MODEL=                    # blank -> claude-opus-5

FIRECRAWL_SEARCH_DELAY_SECONDS=2    # free-tier throttle, 0 disables it
FIRECRAWL_MAX_RETRIES=4             # attempts per request (3 retries)

SEARCH_LIMIT=5
MAX_PAGES_PER_RUN=20
MAX_CONTENT_CHARS=15000
```

Only the selected provider's key is required. Configuring OpenAI never obliges
you to hold an Anthropic key, or the reverse — the unused provider is never
imported and never validated.

`.env` is gitignored. Keys are not intentionally written to outputs, and common
credential forms are redacted from provider error text before logging or saving.
An exported shell variable takes precedence over the file.

Firecrawl keys: <https://www.firecrawl.dev/app/api-keys>

**Model choice.** `ANTHROPIC_MODEL` defaults to `claude-opus-5`. For bulk
extraction across many pages, `claude-haiku-4-5` is substantially cheaper and
usually sufficient for "pull the atomic claims out of this text".

## 6. How to run it

Run from inside this folder.

```bash
python main.py --topic charging --dry-run      # always start here
python main.py --topic charging --max-pages 10 # the real thing
```

| Command | Effect |
|---|---|
| `python main.py` | all 50 queries, all topics |
| `python main.py --topic charging` | one topic |
| `python main.py --topic comfort` | |
| `python main.py --topic infotainment` | |
| `python main.py --topic market_trend` | |
| `python main.py --max-pages 10` | cap pages this run |
| `python main.py --search-limit 5` | results requested per query |
| `python main.py --dry-run` | plan only — no scrape, no LLM |
| `python main.py --reprocess-cache` | replay cached pages, **zero** Firecrawl calls |
| `python main.py --force` | re-scrape cached / visited URLs |
| `python main.py --search-delay 5` | seconds between Firecrawl requests |
| `python main.py --max-retries 6` | attempts per Firecrawl request |

Flags combine freely:

```bash
python main.py --topic charging --max-pages 10 --search-limit 5
```

On a free Firecrawl key, a slower run finishes where a fast one gets throttled:

```bash
python main.py --topic charging --max-pages 10 --search-delay 5 --max-retries 6
```

Three extra conveniences:

| Flag | Effect |
|---|---|
| `--category competitor_benchmark` | run one query category on its own |
| `--dry-run --no-search` | plan with **zero** API calls of any kind |
| `--verbose` | debug logging, including every filter rejection |
| `--list-queries` | print the catalogue and exit, calls nothing |

### Topics vs. categories

The 50 queries are grouped into five categories — `infotainment`, `charging`,
`comfort`, `competitor_benchmark`, `market` — but filed under four *topics*.
Competitor queries carry the topic they actually probe, so
`--topic charging` includes "Porsche Taycan charging test" alongside the BMW
charging queries. That is deliberate: a competitor charging benchmark *is*
charging evidence. Use `--category competitor_benchmark` to run only the
competitor set.

Because a claim is filed under its own topic, a `--topic charging` run will
produce some comfort and infotainment records too — a charging review that also
criticises the touchscreen yields both. That is correct behaviour, not a bug.

### Logging

Logs go to `src/bmw_pm/data_pipeline/web_research/pipeline.log` and to the console.
Nothing is written outside this folder. The log records searches, URLs
selected, filter rejections, cache hits, scrape attempts, extraction attempts,
errors and the final counters.

## 7. Dry-run mode

`--dry-run` runs search and the full filter, then prints the plan and stops. It
**never** scrapes a page and **never** calls the LLM.

Each candidate shows its source family, domain, scrape priority and the action
it would trigger, followed by the families and domains the budget was spent on:

```
==============================================================================
DRY RUN - no page was scraped and no LLM call was made
==============================================================================

SELECTED (5) - in scrape order

[1] government_statistics  | bundesnetzagentur.de     | priority=100  | SCRAPE
    https://bundesnetzagentur.de/DE/Ladeinfrastruktur/start.html
    Ladeinfrastruktur in Betrieb
[2] independent_test_org   | adac.de                  | priority=95   | SCRAPE
    https://adac.de/rund-ums-fahrzeug/autokatalog/marken-modelle/bmw/bmw-i5
    BMW i5 im ADAC Test: Laden
[3] official_manufacturer  | bmw.de                   | priority=85   | SCRAPE
    https://bmw.de/de/neufahrzeuge/i5/limousine.html
[4] professional_review    | evkx.net                 | priority=75   | SCRAPE
    https://evkx.net/models/bmw/i5
[5] customer_forum         | motor-talk.de            | priority=60   | SCRAPE
    https://motor-talk.de/forum/i5-laden-t7123456.html

DEFERRED (7) - over the page budget, a later run picks these up

    professional_review    | insideevs.com            | priority=75   | DEFERRED
      https://insideevs.com/reviews/bmw-i5-charging
    customer_forum         | motor-talk.de            | priority=60   | DEFERRED
      https://motor-talk.de/forum/i5-winter-t7123999.html
    ...

selected source families:
  - customer_forum: 1
  - government_statistics: 1
  - independent_test_org: 1
  - official_manufacturer: 1
  - professional_review: 1

selected domains:
  - adac.de
  - bmw.de
  - bundesnetzagentur.de
  - evkx.net
  - motor-talk.de

------------------------------------------------------------------------------
candidate pages          5
deferred candidates      7
would scrape             5
served from cache        0
skipped (already seen)   0
planned page count       5  (would reach the extractor)
estimated scrape credits 5
estimated LLM calls      >= 5  (one per content chunk)
------------------------------------------------------------------------------
```

The `STATUS` column is `SCRAPE`, `CACHED` or `SKIP`, matching exactly what the
real run would do.

A dry run **does** call Firecrawl Search, which costs ~2 credits per 10
results. To plan with no API calls at all:

```bash
python main.py --topic charging --dry-run --no-search
```

The prediction uses the same code branches as the real run
(`ScrapeCoordinator.plan` and `.resolve` share their logic), so the preview
cannot drift from what actually happens.

## 8. Firecrawl credit-saving behaviour

Credits are the scarce resource, so spending them is gated in several places.

**Costs.** Search ≈ 2 credits per 10 results. Each page scrape = 1 credit.
A Firecrawl *server-side* cache hit (`max_age`) still costs 1 credit — it buys
latency, not credits. Only the **local** cache in `data/cache/` is free.

| Guard | Effect |
|---|---|
| `DEFAULT_SEARCH_LIMIT = 5` | 5 results per query, not 50 |
| `DEFAULT_MAX_PAGES_PER_RUN = 20` | hard cap per run |
| Filter before scrape | deny-listed hosts, listing/search pages, binaries, shorteners and off-topic results are rejected **before** any scrape |
| Priority ranking | the budget is spent on the strongest source families first (§11) |
| Source diversity | early slots go to different domains, so 5 credits buy 5 independent sources rather than 5 threads from one forum (§11) |
| Request throttle | `FIRECRAWL_SEARCH_DELAY_SECONDS` keeps a free-tier run inside the per-minute limit (§12) |
| Canonicalization | `http`/`https`, `www.`, tracking params and fragments collapse to one key, so one page is never paid for twice |
| Local cache | a cached page costs nothing |
| Visited ledger | an already-scraped URL is skipped |
| Search ≠ scrape | `scrape_options` on search is deliberately unused — it would fetch every result before the filter could reject it |
| `--dry-run` | see the bill before paying it |

Over-budget candidates are not discarded; they are deferred and picked up by a
later run.

Every run appends its actual counts to
`data/metadata/research_runs.jsonl`, so the spend is auditable after the fact.
Use `pages_scraped` for credits billed and `firecrawl_scrape_calls` for requests
issued — they differ when a page needed retries (see §11).

**`--force` spends credits.** It bypasses both the cache and the visited ledger
and re-scrapes everything in the plan. Use it when a page has genuinely changed.

## 9. Caching

```
data/cache/<sha256-of-canonical-url>.json
```

The filename is a hash of the canonical URL, so the same page maps to the same
file across runs and machines. On a cache hit the pipeline reuses the stored
markdown and makes no Firecrawl call.

`data/metadata/visited_urls.json` is the separate ledger of outcomes:

```json
{
  "https://adac.de/bmw-i5-ladetest": {
    "first_seen_at": "2026-10-10T09:14:02Z",
    "last_seen_at": "2026-10-10T09:31:44Z",
    "last_scraped_at": "2026-10-10T09:14:02Z",
    "status": "cached",
    "attempts": 2,
    "cache_file": "b20d3e...bac.json",
    "title": "ADAC: BMW i5 Ladetest",
    "topic": "charging"
  }
}
```

`status` is `scraped`, `cached`, `failed` or `filtered`. "Have we already paid
for this page?" is answered by `last_scraped_at`, not by `status` — so a later
cache hit cannot erase the record that the page was already bought. A `failed`
URL has no `last_scraped_at` and will be retried on the next run.

Both the cache and the ledger survive interruption: JSON is written to a temp
file and moved into place atomically, so a killed run cannot leave a truncated
ledger.

To reset: delete `data/cache/*.json` and `data/metadata/visited_urls.json`.
The next run will re-scrape and re-spend.

## 10. Cache-only reprocessing

Every scraped page is kept in `data/cache/`, so improving the post-scrape
pipeline does not require re-buying the pages. This mode replays them:

```bash
python main.py --topic charging --reprocess-cache
```

**It spends nothing.** Neither Firecrawl adapter is constructed, so there is no
client that could issue a request, and no `FIRECRAWL_API_KEY` is needed. It does
consume LLM tokens, since extraction is the point.

The run output is unmistakable:

```
==============================================================================
CACHE-ONLY REPROCESS - no Firecrawl search, no Firecrawl scrape, 0 credits
==============================================================================

reprocessing 3 cached page(s) from .../data/cache:

    15569 chars  https://insideevs.de/reviews/765911/audi-a6-etron-avant-test
     4700 chars  https://adac.de/.../bmw--i5-touring-edrive40-id-5115
      428 chars  https://faq.bmwusa.com/s/article/My-BMW-App-Map-Plan-route-...

==============================================================================
CACHE-ONLY REPROCESS - run metrics
==============================================================================
  firecrawl search calls   0
  firecrawl scrape calls   0
  cached pages processed   3
  ----------------------------------------
  pages skipped thin       1
  pages skipped irrelevant 0
  extraction failures      0
  zero-evidence pages      0
  pages with evidence      2
  ----------------------------------------
  chunks processed         4
  chunks failed            0
  evidence created         7
  evidence duplicates      0
  evidence per good page   3.50
  llm calls                4
==============================================================================
```

The run record is stamped `mode: "reprocess-cache"`, so a zero-credit run is
distinguishable in `research_runs.jsonl` afterwards.

### How cached pages are discovered

Cache-first: every `*.json` in `data/cache/` is a page, ordered by filename so
the run is deterministic. The payload supplies the URL, title, source name,
published date, content and capture time. The cache does not record *which
search found* the page, so the topic and query come from
`data/metadata/visited_urls.json` — **read only; a reprocess run never writes
the ledger, and never touches a cache file.**

`--topic` filters on that recorded topic. A cached page whose topic was never
recorded is reprocessed when no `--topic` is given, and skipped (with a count in
the log) when one is.

Page fields are reconstructed exactly as the scrape path builds them, so a
reprocessed record lands on the same `source_url` — and therefore the same
`evidence_id` — as the original run produced.

### Output, and why re-runs are safe

Reprocessed evidence goes to its own file:

```
data/processed/cache_reprocess_evidence.jsonl
```

The main `external_evidence.jsonl` is never read or written in this mode, so
reprocessing can never disturb evidence from a real scrape.

That file is **rebuilt, not appended**. Append-only is right for a scrape run,
where each page is fetched once; it is wrong for reprocessing, which re-derives
evidence for pages that already have rows. Appending would grow the file on
every pass, and skipping by `evidence_id` would not catch it, because a model
that rewords a claim produces a new id.

So rows belonging to the pages being reprocessed are dropped and rewritten,
while rows from any other page are preserved. Running three times over the same
cache yields the same file — verified. The write is atomic (temp file plus
`os.replace`), so an interrupted rebuild cannot truncate the store.

Cross-source duplicate marking reads from this same file, so a reprocess run
compares against its own output rather than the scrape store.

`--reprocess-cache` is rejected together with `--dry-run` (different modes) and
with `--force` (nothing is scraped, so it has no meaning).

## 11. Output file formats

All four outputs are append-only. JSONL is one JSON object per line.

### `data/raw/raw_pages.jsonl`

Successfully scraped pages. Markdown only — no binary content is ever stored.

```
url, canonical_url, title, source_name, published_at, query, topic,
retrieved_at, markdown
```

### `data/processed/external_evidence.jsonl`

The main output — see §19.

### `data/metadata/research_runs.jsonl`

One record per execution:

```
run_id, started_at, finished_at, topic, queries_attempted,
search_results_found, urls_skipped_duplicate, urls_skipped_filtered,
pages_scraped, pages_loaded_from_cache, pages_failed,
evidence_records_created, evidence_duplicates_found,
firecrawl_search_calls, firecrawl_scrape_calls, llm_calls
```

Read the two scrape counters together:

- **`firecrawl_scrape_calls`** counts HTTP *requests issued*, retries included.
  A page that succeeded on its third attempt contributes 3.
- **`pages_scraped`** counts pages actually obtained — the number that tracks
  billed credits, since Firecrawl bills successful scrapes.

So `firecrawl_scrape_calls: 3` with `pages_scraped: 1` means one page cost one
credit after two transient failures. The same applies to
`firecrawl_search_calls`.

### `data/metadata/visited_urls.json`

The ledger from §9.

### Idempotency

`evidence_id` is a hash of canonical URL + normalized claim, so re-running over
the same page and claim yields the same id, and the writer skips ids already on
disk. **Re-running a topic does not duplicate rows** — verified end to end: a
second `--topic charging` run served all pages from cache, spent zero credits
and added zero rows.

## 12. Candidate ranking and source diversity

Both steps are deterministic and LLM-free. They decide only *which pages get
scraped first*, never what the evidence means.

### Ranking

`source_scoring.classify_source_family` maps a URL's domain to a source family,
and `SOURCE_PRIORITY` gives that family a scrape priority:

| Tier | Source family | Priority | Examples |
|---:|---|---:|---|
| 1 | `government_statistics` | 100 | bundesnetzagentur.de, kba.de, destatis.de, eafo.eu |
| 2 | `independent_test_org` | 95 | adac.de, euroncap.com, test.de, dekra.de |
| 3 | `official_manufacturer` | 85 | bmw.de, audi.de, porsche.com, mercedes-benz.de, tesla.com |
| 4 | `professional_review` | 75 | motortrend.com, caranddriver.com, whatcar.com, autoexpress.co.uk, electrive.com, insideevs.com, evkx.net |
| — | `market_report` | 70 | iea.org, statista.com |
| 5 | `customer_forum` | 60 | motor-talk.de, goingelectric.de, bimmerpost.com |
| 6 | `reddit` | 50 | reddit.com |
| 7 | `youtube_review` | 40 | youtube.com, youtu.be |
| — | `app_review` | 30 | apps.apple.com, play.google.com |
| 8 | `dealer` / `other` | 20 / 10 | dealership and classified hosts, everything unrecognised |

`market_report` and `app_review` are not in the eight requested tiers; they are
placed next to their nearest neighbour and the tier order above still holds.

**Priority is a separate scale from `source_quality`** (§12). Quality scores the
evidence once collected and is part of the stored schema. Priority only orders
the scrape queue and is never written to disk. The two genuinely disagree: a
YouTube review scores **70** as evidence but ranks **below** a customer forum
for scraping, because a forum thread yields far more extractable owner claims
per page than a video transcript.

Unknown domains are classified by host heuristics before falling back to
`other` — dealership markers, `.gov`/`.bund.de`, and `forum`/`community` in the
host.

The sort key is, in order:

1. `priority` descending.
2. the preferred-domain allowlist, breaking ties inside a tier.
3. the provider's `position` ascending.
4. `canonical_url` ascending — so identical inputs always produce byte-identical
   ordering.

### Diversity

Ranking alone would spend a small budget on whichever domain happened to return
the most results. A five-page charging run can easily become five Motor-Talk
threads, which is a lot of credits for one independent source.

Selection therefore runs three passes over the ranked list:

1. **New family *and* new domain** — fills the early slots with genuinely
   different kinds of evidence.
2. **New domain**, family may repeat — adds breadth once every family is used.
3. **Global ranking** for whatever slots remain — this is where a second page
   from an already-used domain is allowed in.

The guarantee is: **every distinct domain available is used before any domain
repeats.** Diversity never starves the budget either — a pool containing only
Motor-Talk threads still fills all `--max-pages` slots.

For `--max-pages 5` against a realistic charging result set:

```
[1] government_statistics  | bundesnetzagentur.de | priority=100 | SCRAPE
[2] independent_test_org   | adac.de              | priority=95  | SCRAPE
[3] official_manufacturer  | bmw.de               | priority=85  | SCRAPE
[4] professional_review    | evkx.net             | priority=75  | SCRAPE
[5] customer_forum         | motor-talk.de        | priority=60  | SCRAPE
```

rather than five forum threads. Over-budget candidates are **deferred**, not
discarded; a later run picks them up. Growing `--max-pages` only appends — the
earlier slots never reorder.

## 13. Firecrawl rate limiting

The free tier limits requests per minute, and a 50-query run will hit it. The
pipeline values finishing a run over finishing it fast.

| Setting | Default | Meaning |
|---|---:|---|
| `FIRECRAWL_SEARCH_DELAY_SECONDS` | `2` | minimum seconds between Firecrawl requests |
| `FIRECRAWL_MAX_RETRIES` | `4` | total attempts per request, so up to 3 retries |

Both are overridable per run with `--search-delay` and `--max-retries`. Set the
delay to `0` to disable throttling on a paid plan.

**Throttling.** One `RateLimiter` is shared by the search *and* scrape clients,
so both endpoints draw on a single per-minute budget rather than two independent
ones. The first request is never delayed, and later ones wait only for the
remainder of the interval — if extraction already took 5 seconds, the next
request goes out immediately.

**On a 429, in order of preference:**

1. A `Retry-After` header — delta-seconds or an HTTP date.
2. An `X-RateLimit-Reset` header — delta-seconds or a Unix epoch.
3. A `retry_after` attribute on the exception.
4. "retry after 7s" / "try again in 13 seconds" / "resets in 5s" parsed from the
   message, since the SDK does not always surface headers.
5. Exponential backoff from the configured delay (2s → 4s → 8s, ±10% jitter).

Any wait is clamped to 120 seconds, so an implausible `Retry-After` cannot park
the run. A provider-requested cool-off also **penalises the shared limiter**, so
the whole query loop slows down rather than just the failing request.

**When the retry budget runs out**, that one query is abandoned, logged with a
hint to raise the delay or the retry count, and **the run continues** with the
remaining queries. A rate limit never ends a run.

Non-429 errors (timeouts, 5xx) use the same backoff but never consult
`Retry-After`.

## 14. Evidence yield per scraped page

A Firecrawl credit buys one page. What that page is worth depends entirely on
how much evidence comes out of it, so three deterministic steps sit between the
scrape and the model. The first real charging run motivated all of them:

| Page | Before | After |
|---|---|---|
| ADAC i5 Touring test, 2,650 chars | 8 records from 1 chunk | unchanged |
| InsideEVs A6 e-tron test, 14,844 chars | **0 records** - one oversized chunk hit the output cap and the whole page was lost | 3 chunks, each well inside the cap |
| BMW USA route-planning FAQ, 428 chars | **0 records** and one wasted LLM call - the page is a `"Loading … Sorry to interrupt"` JS shell | skipped before any model call |

### Thin-content gate

Below `MIN_CONTENT_CHARS` (default **1000**) of trimmed text, the page is
skipped without an extraction request and recorded as `pages_skipped_thin`. The
log names the dead-page markers it found, so a thin page says *why* it was thin
rather than just vanishing.

The old threshold was 400 characters, which the 428-char BMW FAQ cleared by 28.

### Relevance gate

`relevance.py` reads the scraped text and counts distinct hits from two
vocabularies. It is deterministic - no LLM - and shares its topic vocabulary
with the pre-scrape URL filter so the two cannot drift apart.

A page passes on **either** signal:

- `MIN_TOPIC_HITS` (default 3) distinct topic terms, counted across **all four
  topics**, or
- `MIN_VEHICLE_HITS` (default 2) distinct vehicle terms - a page clearly about
  the target car earns a look even if it words its topic unusually.

Terms are anchored with `\b` at the start but not the end, which handles German
compounds for free: `lade` matches `Ladeleistung`, `Ladekurve` and `Ladeplanung`
while the word boundary still stops it matching `Schokolade`.

The gate is deliberately **conservative** - extracting from a marginal page is
far cheaper than silently discarding a strong one. A comfort article with no
charging term and no model name still passes on its comfort vocabulary; a
Bundesnetzagentur infrastructure page passes with no vehicle term at all; an
Audi A6 e-tron charging test passes because competitor models are in the vehicle
vocabulary on purpose.

### Chunking

Trimmed text is split into `EXTRACTION_CHUNK_CHARS` (default **7000**) pieces
with `EXTRACTION_CHUNK_OVERLAP_CHARS` (default **600**) of overlap, and each
chunk gets its own request. Splitting on blank lines where possible, falling
back to a line or space break, and finally a hard cut.

7000 is chosen against the output ceiling, not the input one. The old 15,000
limit let the 14.8k-char InsideEVs page through as a single chunk; the model
then tried to emit every record it found in one response, hit the 8,000-token
output cap, and the truncated JSON was unusable.

**Cross-topic evidence is kept.** A claim is filed under its own topic, not the
topic of the query that found the page. A charging run over the InsideEVs
article keeps its comfort, infotainment and market-trend claims too - the page
is already paid for, and those records are exactly what raises yield per credit.

### Truncation and chunk failure

`finish_reason=length` (OpenAI) and `stop_reason=max_tokens` (Anthropic) now
raise a distinct `LLMTruncatedError` instead of surfacing as "invalid JSON".
That matters because the two need opposite responses: invalid JSON is worth
retrying as-is, whereas a truncated request will truncate again.

A truncated chunk is retried **once** as two overlapping halves. Recursion stops
there, so one chunk costs at most three requests. The error is raised outside
the retry wrapper, so the retry budget is never spent on a request that cannot
succeed as written.

A chunk that fails for any other reason is logged and skipped, and **the
remaining chunks still contribute**. A page is only reported as
`extraction_failed` when every one of its chunks failed.

### Merge and dedup after chunking

Overlap means a claim near a boundary is returned by both neighbouring chunks.
Within one page, records are collapsed on exact normalized claim text first,
then on near matches at the same similarity threshold used elsewhere (92).

When two records state the same claim the **more complete** one is kept, scored
by: carries a numeric value and unit, then longer `evidence_text`, then longer
`claim`. So a chunk that captured "10-80% in 30 minutes" with
`numeric_value=30` beats a neighbour that only caught "charges quickly".

This runs *before* the cross-source duplicate marking in §17, which is unchanged
and still never merges independent sources.

### Source span locators

`source_start_char` / `source_end_char` continue to address the exact quote in
the captured page. Offsets are resolved against the **whole page**, not the
chunk the quote arrived in, so splitting a page into more chunks cannot move
them. A quote the model paraphrased rather than copied is not a locatable span
and the record is rejected.

One known limit: the offset is the *first* occurrence of the quote in the page,
so a sentence repeated verbatim resolves to its first appearance.

## 15. Semantic normalization

Extraction yield is only half the problem. The first high-yield run produced
records that were technically valid and semantically wrong, so a deterministic
pass runs after extraction and before anything is written. It never touches
`evidence_text`, `source_start_char` or `source_end_char`.

Seven passes, in order: **scope filter → split → canonical unit → reclassify →
canonicalize subtopic → clean claim → measure language.**

The unit pass runs *before* reclassification on purpose: promoting `kWh` to
`kWh/100 km` is exactly the signal the consumption rule keys on, so
reclassifying first would miss every consumption figure not already written per
100 km.

### A rule reads the quote, not the claim

The single most important property here: the correction rules classify from
`evidence_text`, not from `claim`. The quote is verifiable text lifted from the
page; the claim is prose the model wrote. When they disagree about what a record
is about, the quote decides. A "ride comfort is excellent" claim whose quote is
a charging-power figure gets retopiced to charging, because the quote is the
evidence.

### Claim language

Claims are normalized to **English**; `evidence_text` stays verbatim in the
page's own language and is **never translated**.

The mechanism is the extraction prompt, which now requires an English claim and
a verbatim original-language quote. No deterministic rule can translate prose,
so `normalization.looks_non_english` is a *detector*, not a translator: it flags
a residual non-English claim, counts it in `non_english_claims`, and keeps the
record. That makes the prompt contract measurable instead of assumed.

Detection fires on a German-only character (`ä`, `ö`, `ü`, `ß`), on two distinct
German function words, or on one function word plus a German nominalisation
ending (`-ung`, `-keit`, `-heit`, `-lich`). The third test is what catches a
short ASCII-spelled sentence like "Die Ladeleistung faellt ab 60 Prozent ab."
An English claim naming a German model has no function word, so it never
reaches those tests.

### Correction rules

Each rule requires a *combination* of signals - a unit plus a keyword, or a
keyword plus a figure - so a passing mention of a word cannot retopic a record.
The first rule that fires wins; when none fires, the model's classification
stands untouched.

| Rule | Fires on | Result |
|---|---|---|
| `consumption_unit` | `kWh/100 km` in the quote or unit | `range` / `energy_consumption` |
| `wltp_range` | `WLTP` plus a distance, and no consumption unit | `range` / `wltp_range` |
| `winter_range` | measured range, winter context in quote or page | `range` / `winter_range` |
| `measured_range` | range word plus a test signal, not WLTP | `range` / `real_world_range` |
| `preconditioning` | names battery preconditioning | `charging` / `battery_preconditioning` |
| `charging_time` | charge-duration word, or a 10-80 % window with minutes | `charging` / `charging_time` |
| `charging_curve` | charging-curve word, or charge power that tapers | `charging` / `charging_curve` |
| `charge_port` | names a physical charging port or flap | `charging` / `charging_port_access` |
| `steering` | names steering behaviour, **not** the steering wheel | `driving_experience` / `steering_response` |
| `braking` | names braking | `driving_experience` / `braking_feel` |
| `charging_speed` | a kW figure **plus** a charging word | `charging` / `charging_speed` |

Two guards worth knowing, both drawn from the real pages:

- **Consumption beats the WLTP label.** `| WLTP-Verbrauch | 14,8 - 17,0 kWh/100 km |`
  is a consumption figure, not a range figure, so the unit rule is ordered first.
- **Range gained by charging is a charging metric.** `| Nachgeladene Reichweite in 20 Minuten | 184 km |`
  says "Reichweite" and quotes kilometres on a range-test page, but it measures
  charging speed in range units, so the range rules explicitly decline it.
- **The steering wheel is not the steering.** The real page says "Auch im
  Lenkrad finden sich Touchtasten" — touch buttons on the wheel, which is
  infotainment. The steering rule excludes `Lenkrad` so it cannot claim it.

`charging_speed` requires the charging word because `270 kW` on its own could
be a motor output.

Page context matters for one distinction: the same "Reichweite im Test" quote
becomes `winter_range` on the ADAC winter test page and `real_world_range` on a
launch review, decided from the page title, query and URL.

### Canonical numeric units

`numeric_unit` is mapped onto a fixed vocabulary so downstream aggregation can
group on it: `kW`, `kWh`, `kWh/100 km`, `V`, `A`, `km`, `km/h`, `minutes`,
`hours`, `percent`, `EUR`, `kg`, `litres`, `dB`.

`Min.`, `Minuten`, `min`, `mins` and `minute` all become **`minutes`**; `%` and
`Prozent` become `percent`; `Euro` and `€` become `EUR`; `Kilowatt` becomes
`kW`. An unrecognised unit is returned unchanged rather than forced into a
canonical form that would lose information.

**`kWh` is the one ambiguous case**, because it is both a consumption figure and
a battery capacity. It is resolved from the quote, in this order:

1. A capacity word (`Akku`, `Batterie`, `netto`, `usable`, `Kapazität`) → stays
   **`kWh`**. Capacity wins outright: mislabelling a 94,9 kWh pack as
   consumption is far worse than leaving a consumption figure unpromoted.
2. A consumption phrasing (`Verbrauch`, `Schnitt`, `Langstrecke`, `konstant`,
   `Tempo 100`, `/100 km`) → **`kWh/100 km`**.
3. Neither — then two weaker signals must agree: the *page* has to be about
   consumption **and** the figure has to be ≤ 40, since production EV
   consumption sits around 10–35 while usable pack sizes start near 50. This is
   what resolves a terse reviewer quote like "wir erreichten 16,3 kWh" without
   ever touching "| Akku netto | 94,9 kWh |".

### Out-of-scope filter

A record is dropped when its text is *primarily* about taxation, company-car
tax, financing, leasing, insurance, purchase incentives, dealer offers,
homologation or a pure business case — **and** names no customer-facing product
subject. Dropped records are counted in `records_filtered_out_of_scope`.

That ordering is the whole design, and it separates the two cases precisely:

| Text | Outcome |
|---|---|
| "the 0.25-percent company car taxation now applies up to 100,000 Euro" | **dropped** — taxation, no product subject |
| "für diesen Preis ist die Materialqualität enttäuschend" | **kept** — a price *and* material quality |
| "trotz des hohen Listenpreises ist die Verarbeitung gut" | **kept** — list price *and* build quality |

Perceived value and quality complaints, customer expectations, usability,
comfort, charging, range, software, design, driving experience, space and
competitor capabilities are all protected by the product-subject list.

One subtlety worth knowing if you edit those patterns: the product list mixes
anchored and unanchored alternatives on purpose. German compounds carry the
meaningful stem in the *middle* of a word (`Materialqualität`, `Rücksitz`,
`Ladeleistung`), so those stems stay unanchored; short English words must be
anchored, because an unanchored `app` matches **"applies"** — which is exactly
what let the company-car-taxation line through before it was fixed.

### Claim text cleanup

Formatting artifacts are repaired in the **claim only**. `evidence_text` stays
byte-for-byte identical and the offsets are untouched.

```
"The A6e-tron charges quickly."   -> "The A6 e-tron charges quickly."
"Available onlyfor the top trim." -> "Available only for the top trim."
"The cabin is veryquiet at speed."-> "The cabin is very quiet at speed."
```

Repairs are bounded on purpose: a glued pair is split only when **both** halves
appear in a curated list, so `notable` is not turned into "not able" and
`online` survives intact.

### Capability versus observation

Two records about the same number can be different evidence:

```
"DC charging power is rated at 270 kW."                     -> capability
"The A6 e-tron reaches 270 kW in the test, but only briefly." -> observed
```

Collapsing these would delete the nuance a product manager most needs, so a
record carrying an observation marker (`im Test`, `wir erreichten`, `gemessen`,
`only briefly`, `in der Praxis`) is never merged into one that does not.

The test is **observed versus not observed**, not capability versus observed: a
flat spec statement often carries no explicit capability marker, and requiring
the exact pair would merge it into the hedged observation and lose the hedge.
An observation marker also *wins* when both kinds appear, because the two
records usually share one quote — a rated phrasing in that shared quote would
otherwise cancel the observation only one of them actually makes.

Two records that genuinely state the same proposition still collapse, keeping
the more complete one. The role is computed when needed and never stored, so the
evidence schema is unchanged.

### Multi-value facts

`| Ladeleistung AC/DC | 11 kW / 270 kW |` arrived as one record with
`numeric_value: null`. It now becomes two atomic records:

```
charging/charging_speed   AC charging power is 11 kW.    numeric_value=11    unit=kW
charging/charging_speed   DC charging power is 270 kW.   numeric_value=270   unit=kW
```

Both keep the original quote and offsets, because both facts genuinely come from
that one row. Label-first (`AC 11 kW`) and value-first (`11 kW am AC-Lader`)
wordings are both handled, in either label order.

A *range* of one value - `14,8 - 17,0 kWh/100 km`, `627 - 720 km` - is one fact
with an interval, not two facts. It is deliberately left alone rather than
invented into a structure the schema cannot hold, so `numeric_value` stays null
and the text carries the interval.

German decimal commas are parsed correctly: `25,6` is 25.6 and `1.234,5` is
1234.5.

### Same-page deduplication

Five duplicate shapes are handled. The first four are claim-text based; the
fifth is the language-independent backstop:

1. exact normalized claim text;
2. paraphrases, at the same-page threshold of **88** - lower than the
   cross-source 92, because same page plus same subtopic is a much stronger
   prior;
3. overlapping-chunk repeats;
4. multilingual equivalents, once claims are English;
5. **same evidence span expressing one proposition** - spans overlapping by
   ≥60% of the shorter one, same topic *and* subtopic, with no conflicting
   numbers.

Rule 5 is what actually caught the observed bug. The English and German
wordings of one observation quote the *same German sentence*, so their spans
coincide even though their claim texts share almost no tokens.

It is deliberately narrow, because the brief is explicit that genuinely
distinct facts must not merge:

- **Same subtopic required** - seat comfort and ride comfort drawn from
  "Die Sitze sind bequem, aber der Fahrkomfort leidet" stay separate.
- **No numeric conflict** - the split `11 kW` and `270 kW` records share one
  span and one subtopic, and two numbers that disagree mean two facts.
- **Cross-source behaviour is untouched.** Independent sources reaching the same
  conclusion are still never merged (§17).

When two records do describe one proposition, the **more complete** one is kept:
carries a numeric value and unit, then longer `evidence_text`, then longer
`claim`.

### Before and after, on the real cached pages

Replaying the exact rows the real run stored:

| Before | After |
|---|---|
| `comfort/perceived_interior_quality` × 2, one English one German, same quote | one record, English claim |
| `charging/charging_speed`, `numeric_value: null` for `11 kW / 270 kW` | two records, 11 kW and 270 kW |
| `charging/long_distance_charging` for `WLTP-Reichweite 627 - 720 km` | `range/wltp_range` |
| `charging/charging_reliability` for `25,6 kWh/100km` | `range/energy_consumption` |
| `charging/long_distance_charging` for `Reichweite im Test 351 km` | `range/winter_range` |

Six observed rows become six records - one duplicate removed, one row split -
with every span still exact, every claim English and every quote verbatim
German.

## 16. Source quality policy

`source_quality` is a fixed table in `source_scoring.py`, applied after the
`source_family` has been decided **from the URL's domain**. The LLM never sets
either.

| Source family | Score |
|---|---:|
| `government_statistics` | 95 |
| `independent_test_org` | 95 |
| `official_manufacturer` | 90 |
| `professional_review` | 80 |
| `market_report` | 80 |
| `youtube_review` | 70 |
| `customer_forum` | 60 |
| `reddit` | 50 |
| `app_review` | 50 |
| `dealer` | 45 |
| `other` | 40 |

```python
from source_scoring import get_source_quality
get_source_quality("independent_test_org")   # 95
```

Classification resolves in this order: exact host, then registrable domain,
then host heuristics (dealer markers, `.gov`/`.bund.de`, `forum`/`community`),
then the LLM's validated hint, then `other`. So `adac.de` →
`independent_test_org` → 95 and `bundesnetzagentur.de` →
`government_statistics` → 95, whatever the model suggests.

A high score means *this kind of source is usually reliable*. It is not a truth
value for the individual claim, and a 90 from a manufacturer page is still
marketing — the extraction prompt says so explicitly.

### Preferred sources

`PREFERRED_DOMAINS` (ADAC, Bundesnetzagentur, KBA, EAFO/EU, IEA, Euro NCAP,
BMW press, the German automotive press, Motor-Talk, GoingElectric, …) get two
privileges: they skip the topic-keyword relevance gate, and they are ranked
first so that a capped run spends its page budget on them.

## 17. Deduplication behaviour

Two separate ideas, and conflating them is the usual mistake.

### Independence groups — "which document did this come from?"

`independence_group` is `SRC-<hash>` of the **origin document**. Pagination and
per-view parameters are stripped first, so:

- every page of one Motor-Talk thread → one group
- every comment permalink under one Reddit post → one group
- `viewtopic.php?t=9999&start=60` and `&start=0` → one group
- `watch?v=AAA&t=30s` and `watch?v=AAA` → one group

**Ten claims from one forum thread are ten signals but one independent source.**
Downstream aggregation should count groups, not rows:

```python
from dedup import count_independent_sources
count_independent_sources(records)
```

### Duplicates — "is this the same claim twice?"

Decided **only within one independence group**, by `rapidfuzz`
`token_set_ratio` on normalized claim text (lowercased, de-punctuated,
whitespace-collapsed) at a threshold of **92**.

Duplicates are **marked, never deleted**: the later record gets
`duplicate_of: "EXT-..."` pointing at the keeper. Nothing is lost, and a
consumer can filter on `duplicate_of is None`.

Measured behaviour at threshold 92:

| Pair | Score | Result |
|---|---:|---|
| `10-80% charging in 30 minutes.` / `10-80 % charging in 30 minutes` | 100 | duplicate |
| `Wind noise is noticeable above 130 km/h.` / `Above about 130 km/h wind noise becomes noticeable.` | 96 | duplicate |
| `...10 to 80 percent in about 30 minutes.` / `...10-80% in roughly 30 minutes.` | 91.5 | **kept** |
| `Front seats are comfortable.` / `Rear seat space is tight.` | 39 | kept |

The threshold errs toward keeping. It catches reorderings and formatting
variants — the real duplicate pattern from chunk overlap and thread quoting —
while leaving genuine paraphrases as separate signals.

### Independent sources are never merged

> ADAC: *i5 10–80% takes ~30 minutes*
> Independent EV test: *i5 10–80% takes ~30 minutes*

Different independence groups, so **both are kept**. This is corroboration, and
collapsing it would destroy the signal the pipeline exists to find. Such pairs
are logged as "cross-source corroboration pair(s) retained", which is also a
useful hint: a long list may mean syndicated copies the URL filter missed.

Three further dedup layers run earlier:

1. **URL** — canonical duplicates are dropped before scraping.
2. **Chunk overlap** — identical claims from overlapping chunks of one page are
   collapsed at extraction.
3. **Across runs** — new records are compared against stored records in the same
   independence group, so a second pass over one thread does not re-append
   near-duplicates.

## 18. Example raw evidence

The internal `RawEvidence` stage, after validation and before scoring. Note the
source fields are already filled in by the pipeline, not by the model.

```json
{
  "source_url": "https://www.adac.de/rund-ums-fahrzeug/autokatalog/marken-modelle/bmw/bmw-i5/",
  "source_name": "ADAC",
  "source_title": "BMW i5 im Test",
  "source_family": "independent_test_org",
  "published_at": "2026-03-14",
  "brand": "BMW",
  "vehicle": "BMW i5 eDrive40",
  "market": "DE",
  "topic": "charging",
  "subtopic": "charging_time",
  "claim": "ADAC measured 10-80% DC charging in 30 minutes for the tested i5 eDrive40.",
  "evidence_text": "Von 10 auf 80 Prozent in 30 Minuten.",
  "numeric_value": 30.0,
  "numeric_unit": "min"
}
```

## 19. Example processed evidence

One line of `data/processed/external_evidence.jsonl`, pretty-printed:

```json
{
  "evidence_id": "EXT-b40d957e14af",
  "source_url": "https://www.adac.de/rund-ums-fahrzeug/autokatalog/marken-modelle/bmw/bmw-i5/",
  "source_name": "ADAC",
  "source_title": "BMW i5 im Test",
  "source_family": "independent_test_org",
  "published_at": "2026-03-14",
  "retrieved_at": "2026-10-10T09:14:22Z",
  "brand": "BMW",
  "vehicle": "BMW i5 eDrive40",
  "market": "DE",
  "topic": "charging",
  "subtopic": "charging_time",
  "claim": "ADAC measured 10-80% DC charging in 30 minutes for the tested i5 eDrive40.",
  "evidence_text": "Von 10 auf 80 Prozent in 30 Minuten.",
  "numeric_value": 30.0,
  "numeric_unit": "min",
  "source_quality": 95,
  "independence_group": "SRC-09796aeebf42",
  "duplicate_of": null
}
```

Reading a few of these:

```python
import json, pathlib
rows = [json.loads(l) for l in
        pathlib.Path("data/processed/external_evidence.jsonl").read_text().splitlines() if l.strip()]

live = [r for r in rows if r["duplicate_of"] is None]
sources = {r["independence_group"] for r in live}
print(f"{len(live)} claims from {len(sources)} independent sources")
```

## 20. Controlled vocabulary

Validated by `models.py`; an invalid value is a rejected record, not a bad line
in the output.

**Topics and subtopics** — a subtopic is only valid inside its own topic. There
are five topics; `range` was added for figures that are neither charging nor
comfort:

- **infotainment**: `touchscreen`, `menu_complexity`, `physical_controls`,
  `climate_control_interaction`, `navigation`, `voice_assistant`,
  `smartphone_integration`, `software_reliability`, `connected_services`,
  `display_usability`
- **charging**: `charging_speed`, `charging_curve`, `charging_time`,
  `charging_reliability`, `battery_preconditioning`, `route_planning`,
  `public_charging`, `long_distance_charging`, `charging_stop_duration`,
  `plug_and_charge`, `charging_infrastructure`, `winter_charging`
- **comfort**: `front_seat_comfort`, `rear_seat_comfort`, `rear_seat_space`,
  `ride_comfort`, `cabin_noise`, `interior_space`, `climate_comfort`,
  `long_distance_comfort`, `suspension_comfort`, `perceived_interior_quality`,
  `material_quality`
- **range**: `wltp_range`, `real_world_range`, `winter_range`,
  `energy_consumption`
- **driving_experience**: `steering_response`, `handling`, `braking_feel` —
  deliberately *not* folded into comfort, because how a car steers, grips and
  stops is a different customer concern from how softly it rides
- **market_trend**: `infrastructure_growth`, `customer_expectation`,
  `competitive_benchmark`, `adoption_trend`, plus the earlier
  `ev_adoption`, `charging_network_growth`, `charging_behavior`,
  `future_customer_expectation`

Earlier subtopic names stay **valid** so evidence already on disk keeps
validating, and the normalization pass rewrites new records to the canonical
name so the vocabulary converges instead of splitting:

| Deprecated | Canonical |
|---|---|
| `charging_infrastructure` | `charging_network` |
| `charging_network_growth` | `infrastructure_growth` |
| `future_customer_expectation` | `customer_expectation` |
| `ev_adoption` | `adoption_trend` |

`public_charging` is deliberately **not** folded into `charging_network`: one is
about the experience of using a public charger, the other about the network
existing. The taxonomy is extended by editing `SUBTOPICS` in `models.py`, and an
alias by editing `SUBTOPIC_ALIASES` beside it.

A valid subtopic paired with the wrong topic is repaired from the subtopic. A
subtopic that is not in the list at all means the record is dropped and counted
in `records_rejected`.

## 21. Firecrawl SDK usage

Verified against **`firecrawl-py` 4.50.0**, released 2026-10-08, and the current
Firecrawl docs — not from memory.

**Search** (`search.py`):

```python
from firecrawl import Firecrawl

firecrawl = Firecrawl(api_key="fc-...")
result = firecrawl.search(
    "BMW i5 Ladegeschwindigkeit Test",
    limit=5,
    sources=["web"],
    location="Germany",
    timeout=60_000,          # milliseconds
)
for item in result.web or []:
    item.url, item.title, item.description, item.position
```

**Scrape** (`scraper.py`):

```python
doc = firecrawl.scrape(
    url,
    formats=["markdown"],
    only_main_content=True,
    max_age=172_800_000,     # Firecrawl's own 2-day cache
    timeout=60_000,
)
doc.markdown
doc.metadata.title, doc.metadata.source_url, doc.metadata.og_site_name
```

Points worth knowing, all of which this code handles:

- **The Python SDK converts response field names from camelCase to snake_case**,
  so `sourceURL` arrives as `source_url`. Every metadata read here accepts both
  spellings, and dict- or object-shaped metadata, so a minor SDK change does not
  break a run.
- Search results are grouped by source type; web results are on `result.web`,
  which can be `None`. The parser also tolerates a dict or a bare list.
- `search()` supports `scrape_options` for one-call search-and-scrape. **Not
  used on purpose** — it would scrape every result before the filter could
  reject it, which is exactly the spend this pipeline avoids.
- `max_age` is Firecrawl's server cache. It improves speed, **not** credits.
- Search costs 2 credits per 10 results, rounded up; a scrape costs 1.

**LLM SDKs**, checked the same way:

- `openai` **3.28.0** — `client.chat.completions.create(...)` with
  `response_format={"type": "json_schema", ...}`. `gpt-5*`/`o*` models take
  `max_completion_tokens` and reject `temperature`; older models take
  `max_tokens`. Parameters are selected per model family, and a rejection is
  retried once with the offending parameter removed.
- `anthropic` **1.13.0** — `client.messages.create(...)` with
  `output_config={"format": {"type": "json_schema", "schema": ...}}`. Assistant
  prefill is not used (current models reject it). `stop_reason == "refusal"`
  arrives as HTTP 200 and is checked explicitly.

## 22. Error handling

One bad page never ends a research run.

| Failure | Behaviour |
|---|---|
| Search fails for a query | logged, 3 retries with backoff, then that query is skipped |
| Scrape fails | 3 retries, then marked `failed` in the ledger; loop continues |
| Page has no usable text | skipped before any LLM call (`MIN_PAGE_CHARS = 400`) |
| LLM returns invalid JSON | one explicit repair retry, then that chunk is skipped |
| LLM returns empty / refuses | raised as `LLMError`, retried, then chunk skipped |
| A record fails validation | dropped and counted; the rest of the page is kept |
| Numeric value without a unit | number dropped, **claim kept** |
| Corrupt line in a JSONL store | logged and skipped; the run proceeds |
| Missing API key | clear message naming the variable and the file, exit code 2 |
| `Ctrl-C` | partial results stay on disk, exit code 130 |

Retries use `tenacity` with exponential backoff where it is installed, and an
equivalent internal loop where it is not.

## 23. Common errors

**`FIRECRAWL_API_KEY is not set`**
`.env` is missing or in the wrong place. It belongs at
`src/bmw_pm/data_pipeline/web_research/.env`, beside `main.py` — not at the repo root.

**`LLM_PROVIDER=openai but OPENAI_API_KEY is not set`**
Either add that key or switch `LLM_PROVIDER` to the provider you do have.

**`firecrawl-py is not installed`**
The venv is not active, or `pip install -r requirements.txt` has not run. Check
with `python -c "import firecrawl"`.

**`nothing to do: no candidate URL survived filtering`**
Every result was rejected. Run with `--verbose` to see each rejection reason.
Usually the query is too narrow, or the results were all listing pages.

**Everything is skipped and nothing happens**
The URLs are in `visited_urls.json` from an earlier run. That is the credit
guard working. Use `--force` to re-scrape, or `--dry-run` to confirm.

**Zero evidence extracted from pages that clearly scraped fine**
Check `pipeline.log` for `records_rejected`. Usually the model is returning
subtopics outside the vocabulary. Run with `--verbose` to see the rejected
records.

**`Unsupported parameter: 'temperature'` / `max_tokens`**
Handled automatically — the request is retried once without it. If you see it
repeatedly, `OPENAI_MODEL` is probably a model family the parameter selector
does not recognise; it still works, just with one wasted attempt.

**Rate limits or 429s**
Retried with exponential backoff. Lower `--max-pages` if it persists.

**No duplicates are ever marked**
`rapidfuzz` is probably missing, leaving the stricter `difflib` fallback.
`pip install rapidfuzz`.

## 24. Verification status

No automated test files or test configuration are included in this checkout, so
the following prior implementation notes are not independently reproducible
from this repository. They describe checks reported during development, not
results verified by the current validation run:

- URL canonicalization across 10 cases, including the `http`/`https` collapse
  that prevents paying twice for one page.
- Filter rules across 11 cases: aggregators, shorteners, binaries, listing and
  search pages, site roots, off-topic results, and cross-query URL duplicates.
- Source classification and scoring for government, test-org, manufacturer,
  forum, Reddit, YouTube, dealer and unknown domains, including that the domain
  table overrides the model's hint.
- Independence grouping for Motor-Talk pagination, GoingElectric `start=`,
  Reddit comment permalinks and YouTube timestamps.
- Duplicate marking within a group, with an identical claim from a second
  independent publisher left intact.
- Full run: 3 pages → 8 evidence records across 3 independence groups; all
  three on-disk schemas match their declared field order.
- **Re-run of the same topic: 0 new scrape credits, 0 new rows.**
- A failing page recorded as `pages_failed: 1` while the healthy page in the
  same run still produced evidence.
- Both providers' request parameters bound against the real installed
  `openai` 3.28.0 and `anthropic` 1.13.0 signatures.
- Ranking: all eight tiers order correctly even when the weakest source holds
  search position 1; identical under 5 shuffles of the input.
- Diversity: a pool where one forum holds positions 1-5 drops from 4 pages of
  that one domain to full domain coverage first; `max_pages` honoured exactly at
  0/1/3/5/12/13/50; growing the budget only appends; a single-domain pool still
  fills every slot; identical under 8 shuffles.
- Rate limiting: 19 detection cases (`status_code`, nested response, message
  wording, exception type name) and 10 `Retry-After` shapes (delta-seconds,
  HTTP date, epoch reset, attribute, four message phrasings); the retry budget
  is never exceeded at 1/2/4/6 attempts; a provider's 15s is used in place of
  backoff; 99999s is clamped to 120s; one abandoned query leaves the other three
  returning results; search and scrape share one limiter.

The final cleanup pass is verified the same way: `Min.`/`Minuten` canonicalize
to `minutes`, a long-distance `18,5 kWh` becomes `kWh/100 km` while
`| Akku netto | 94,9 kWh |` stays `kWh`, the real steering, braking and
`Ladeanschlüsse auf beiden Seiten` quotes land in `driving_experience` and
`charging_port_access`, `Lenkrad` touch buttons do **not**, a company-car
taxation line is filtered while a price-quality complaint is kept, and a rated
270 kW and an observed "only briefly" 270 kW both survive.

Semantic normalization is verified against the three real cached pages, with
every fixture quote asserted to be a verbatim span of the page it claims to come
from: the multilingual duplicate collapses, the AC/DC row splits into two
numbered records, `25,6 kWh/100km` becomes `range/energy_consumption`, WLTP
range becomes `range/wltp_range`, `Reichweite im Test` becomes `winter_range` on
the winter page and `real_world_range` on the launch review, and
`Nachgeladene Reichweite` is left as a charging metric.

Cache-only reprocessing is verified against the three real cached pages: zero
Firecrawl clients constructed, the 428-char page skipped as thin, the long
article split into three chunks, and three consecutive runs producing an
identical output file.

**Not yet verified:** a live Firecrawl run and a live LLM call, which need your
API keys. Start with `--dry-run`, then one `--max-pages 2` run, and check
`data/processed/external_evidence.jsonl` before going wider.
