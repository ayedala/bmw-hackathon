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
extractor.py        trim -> chunk -> LLM -> atomic claim records
      |                (llm_provider.py: OpenAI or Anthropic)
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
issued — they differ when a page needed retries (see §10).

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

## 10. Output file formats

All four outputs are append-only. JSONL is one JSON object per line.

### `data/raw/raw_pages.jsonl`

Successfully scraped pages. Markdown only — no binary content is ever stored.

```
url, canonical_url, title, source_name, published_at, query, topic,
retrieved_at, markdown
```

### `data/processed/external_evidence.jsonl`

The main output — see §16.

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

## 11. Candidate ranking and source diversity

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

## 12. Firecrawl rate limiting

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

## 13. Source quality policy

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

## 14. Deduplication behaviour

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

## 15. Example raw evidence

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

## 16. Example processed evidence

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

## 17. Controlled vocabulary

Validated by `models.py`; an invalid value is a rejected record, not a bad line
in the output.

**Topics and subtopics** — a subtopic is only valid inside its own topic:

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
- **market_trend**: `ev_adoption`, `charging_network_growth`,
  `charging_behavior`, `future_customer_expectation`

A valid subtopic paired with the wrong topic is repaired from the subtopic. A
subtopic that is not in the list at all means the record is dropped and counted
in `records_rejected`.

## 18. Firecrawl SDK usage

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

## 19. Error handling

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

## 20. Common errors

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

## 21. Verification status

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

**Not yet verified:** a live Firecrawl run and a live LLM call, which need your
API keys. Start with `--dry-run`, then one `--max-pages 2` run, and check
`data/processed/external_evidence.jsonl` before going wider.
