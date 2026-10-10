# Data search, ingestion and cleaning

All evidence acquisition code lives here. Preserve source bytes, record transformations, and keep uncertain facts visible. This module does not rank or approve requirements.

| File or directory | Purpose |
|---|---|
| `feedback.py` | Parse workbook feedback, normalize labels, redact text, reconcile duplicate annotation rows and preserve exact locators |
| `studies.py` | Parse customer-study aggregates without treating them as individual feedback |
| `legacy_database.py` | Import allowlisted foreign evidence and immutable snapshots as unreviewed context |
| [web_research](web_research/README.md) | Public web search, filtering, scraping, model claim extraction, normalization, source quality and deduplication |
| [youtube_research](youtube_research/README.md) | Video discovery, captions or authorized uploads, quote/timestamp checks and local evidence browsing |

Core imports use `bmw_pm.data_pipeline`. From the repository root:

```bash
uv run bmw-pm ingest --input data/raw/provided --profile configs/g60.json
```

Optional collectors retain script-local imports and their own `requirements.txt` and `.env.example`. Enter the collector directory before running its documented commands. For a web plan without any API requests:

```bash
cd src/bmw_pm/data_pipeline/web_research
python main.py --topic charging --dry-run --no-search
```

Collector data, keys, caches and logs remain local and ignored. Their JSONL/JSON output is **not yet imported into the core requirement workflow**. Source-quality scores are evidence metadata, not requirement priorities. The web default is Germany while the core demo profile is US; do not mix those scopes implicitly.

The top-level `pipeline.py` owns orchestration and storage calls. Parsers expose typed batches; storage owns the database transactions. Keep the lightweight core import free of optional collector dependencies.
