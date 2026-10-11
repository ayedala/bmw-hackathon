# File-by-file repository inventory

Reviewed tracked text files, Python module contracts/imports and configuration. Paths below reflect the cleanup. Generated data, virtual environments and private local artifacts are excluded. This is an ownership map, not a claim of exhaustive defect detection. New module README files are linked from their parent guides.

| File | Responsibility | Review disposition |
|---|---|---|
| `.codex/hooks.json` | Development tool settings; review owner before removing. | Retain |
| `.dockerignore` | Restrict Docker context, including private collector artifacts. | Retain |
| `.entire/.gitignore` | Exclude secrets, local data, caches and generated artifacts. | Retain |
| `.entire/settings.json` | Development tool settings; review owner before removing. | Review removal/consolidation recommendation |
| `.env.example` | Credential/configuration template; actual .env stays ignored. | Retain |
| `.gitignore` | Exclude secrets, local data, caches and generated artifacts. | Retain |
| `.streamlit/config.toml` | Supporting configuration or placeholder; retain unless its owning workflow is retired. | Retain |
| `Dockerfile` | Hosted core image; optional research collectors are excluded from its context. | Retain |
| `README.md` | BMW Product Decision Lab | Retain |
| `configs/baseline_taxonomy_v1.json` | Offline extraction taxonomy, keywords and customer outcomes. | Retain |
| `configs/exploratory_equal_v1.json` | Versioned exploratory equal-weight prioritization policy. | Retain |
| `configs/g60.json` | US G60 scope and explicit alias assumptions. | Retain |
| `docs/ARCHITECTURE.md` | MVP architecture | Retain |
| `docs/DATA_AUDIT.md` | Supplied data audit and ingestion rules | Retain |
| `docs/DATA_CONTRACTS.md` | Data contracts and validation boundaries | Retain |
| `docs/DECISION_ENGINE.md` | Evidence, prioritization and decision logic | Retain |
| `docs/DEMO.md` | Demonstration and presentation plan | Retain |
| `docs/EVALUATION.md` | Evaluation and release evidence | Retain |
| `docs/HOSTING.md` | Hosted decision workbench | Retain |
| `docs/HUMAN_REVIEW_AND_AUDIT.md` | PM review, audit and decision memory | Retain |
| `docs/MODEL_TRANSFER.md` | Transfer to other vehicles, markets and unseen data | Retain |
| `docs/REPORT.md` | Strategy report: BMW Product Decision Lab | Retain |
| `docs/WEB_RESEARCH.md` | Web evidence and enrichment plan | Retain |
| `src/bmw_pm/data_pipeline/web_research/.env.example` | Credential/configuration template; actual .env stays ignored. | Moved; keep responsibility isolated |
| `src/bmw_pm/data_pipeline/web_research/.gitignore` | Exclude secrets, local data, caches and generated artifacts. | Moved; keep responsibility isolated |
| `src/bmw_pm/data_pipeline/web_research/README.md` | External Research Pipeline | Moved; keep responsibility isolated |
| `src/bmw_pm/data_pipeline/web_research/config.py` | Runtime configuration, paths and target research context. | Moved; keep responsibility isolated |
| `src/bmw_pm/data_pipeline/web_research/data/cache/.gitkeep` | Supporting configuration or placeholder; retain unless its owning workflow is retired. | Moved; keep responsibility isolated |
| `src/bmw_pm/data_pipeline/web_research/data/metadata/.gitkeep` | Supporting configuration or placeholder; retain unless its owning workflow is retired. | Moved; keep responsibility isolated |
| `src/bmw_pm/data_pipeline/web_research/data/processed/.gitkeep` | Supporting configuration or placeholder; retain unless its owning workflow is retired. | Moved; keep responsibility isolated |
| `src/bmw_pm/data_pipeline/web_research/data/raw/.gitkeep` | Supporting configuration or placeholder; retain unless its owning workflow is retired. | Moved; keep responsibility isolated |
| `src/bmw_pm/data_pipeline/web_research/dedup.py` | Independence grouping and claim deduplication. | Moved; keep responsibility isolated |
| `src/bmw_pm/data_pipeline/web_research/extractor.py` | LLM evidence extraction: prompt contract, chunking, parsing and validation. | Moved; keep responsibility isolated |
| `src/bmw_pm/data_pipeline/web_research/llm_provider.py` | LLM provider abstraction for evidence extraction. | Moved; keep responsibility isolated |
| `src/bmw_pm/data_pipeline/web_research/main.py` | CLI entry point for the external research pipeline. | Moved; keep responsibility isolated |
| `src/bmw_pm/data_pipeline/web_research/models.py` | Pydantic schemas and the controlled vocabularies they validate against. | Moved; keep responsibility isolated |
| `src/bmw_pm/data_pipeline/web_research/queries.py` | The search-query catalogue, grouped by category and tagged with a topic. | Moved; keep responsibility isolated |
| `src/bmw_pm/data_pipeline/web_research/requirements.txt` | Isolated optional collector dependencies; not part of the core environment. | Moved; keep responsibility isolated |
| `src/bmw_pm/data_pipeline/web_research/scraper.py` | Scrape layer: the Firecrawl Scrape adapter and the credit-guarding coordinator. | Moved; keep responsibility isolated |
| `src/bmw_pm/data_pipeline/web_research/search.py` | Search layer: the Firecrawl Search adapter and the pre-scrape URL filter. | Moved; keep responsibility isolated |
| `src/bmw_pm/data_pipeline/web_research/source_scoring.py` | Deterministic source-family classification and quality scoring. | Moved; keep responsibility isolated |
| `src/bmw_pm/data_pipeline/web_research/storage.py` | Persistence: JSONL append, the local page cache and the visited-URL ledger. | Moved; keep responsibility isolated |
| `src/bmw_pm/data_pipeline/web_research/utils.py` | Shared helpers: URL canonicalization, hashing, text normalization, retries, logging. | Moved; keep responsibility isolated |
| `internal/AGENTS.md` | Repository instructions for coding agents | Historical development guidance; review stale paths before archiving |
| `internal/CODEX_KICKOFF.md` | First implementation task for Codex | Historical development guidance; review stale paths before archiving |
| `internal/DECISIONS.md` | Decision and assumption register | Historical development guidance; review stale paths before archiving |
| `internal/IMPLEMENTATION_PLAN.md` | Remaining-work implementation plan | Historical development guidance; review stale paths before archiving |
| `internal/README.md` | Internal development files | Historical development guidance; review stale paths before archiving |
| `internal/TASKS.md` | Task board | Historical development guidance; review stale paths before archiving |
| `internal/agent-guides/core.md` | Core implementation rules | Historical development guidance; review stale paths before archiving |
| `internal/agent-guides/tests.md` | Test and evaluation instructions | Historical development guidance; review stale paths before archiving |
| `internal/agent-guides/ui.md` | UI implementation rules | Historical development guidance; review stale paths before archiving |
| `prompts/DRAFT_REQUIREMENTS.md` | Runtime template: draft customer requirements | Retain |
| `prompts/EXTRACT_SIGNALS.md` | Runtime template: extract atomic signals | Retain |
| `prompts/README.md` | Prompt contracts | Retain |
| `prompts/REVIEW_ARGUMENT.md` | Runtime template: review an argument or PM challenge | Retain |
| `pyproject.toml` | Core package, entry point, dependencies, wheel boundaries and test configuration. | Retain |
| `render.yaml` | Hosted deployment manifest and persistent database settings. | Retain |
| `research/web_evidence_seed.jsonl` | Curated external evidence seeds, requiring source snapshot/locator validation. | Retain |
| `scripts/inspect_supplied_data.py` | Read supplied BMW files locally; preserve bytes and produce a reproducible profile. | Retain |
| `scripts/prepare_hosted_database.py` | Create a private WAL-consistent canonical snapshot; never commit the output. | Retain |
| `scripts/profile_feedback.py` | Compute descriptive diagnostics only; labels are not model evaluation truth. | Retain |
| `scripts/validate_preparation.py` | Validate this preparation pack, not the unimplemented AI application. | Retain |
| `settings.json` | Development tool settings; review owner before removing. | Review removal/consolidation recommendation |
| `src/bmw_pm/__init__.py` | BMW Product Decision Lab core package. | Retain |
| `src/bmw_pm/cli.py` | Command-line application boundary; domain rules live in the underlying services. | Retain |
| `src/bmw_pm/contracts.py` | Typed evidence, requirement, score and audit contracts shared across modules. | Retain |
| `src/bmw_pm/decision/__init__.py` | Public module exports; keeps the application boundary explicit. | Retain |
| `src/bmw_pm/decision/scoring.py` | Pure deterministic requirement scoring: unknown inputs retain their weight as intervals. | Retain |
| `src/bmw_pm/hosting.py` | Bounded deployment/bootstrap helpers. No cloud-provider dependency. | Retain |
| `src/bmw_pm/data_pipeline/__init__.py` | Public module exports; keeps the application boundary explicit. | Moved; keep responsibility isolated |
| `src/bmw_pm/data_pipeline/feedback.py` | Parse and clean workbook feedback while retaining raw hashes, row locators and transformations. | Moved; keep responsibility isolated |
| `src/bmw_pm/data_pipeline/legacy_database.py` | Import allowlisted foreign evidence as unreviewed context, preserving its original lineage. | Moved; keep responsibility isolated |
| `src/bmw_pm/data_pipeline/studies.py` | Parse aggregate customer studies separately from individual feedback recurrence counts. | Moved; keep responsibility isolated |
| `src/bmw_pm/intelligence/__init__.py` | Public module exports; keeps the application boundary explicit. | Retain |
| `src/bmw_pm/intelligence/baseline.py` | Offline keyword extraction fallback; its output must never be presented as AI inference. | Retain |
| `src/bmw_pm/intelligence/provider.py` | Bounded model extraction with typed output and exact evidence-span validation. | Retain |
| `src/bmw_pm/decision/requirements.py` | Deterministically consolidate validated signals into source-linked customer requirements. | Moved; keep responsibility isolated |
| `src/bmw_pm/pipeline.py` | Application orchestration: compose ingestion, extraction, deterministic decisions and persistence. | Retain |
| `src/bmw_pm/review/__init__.py` | Public module exports; keeps the application boundary explicit. | Retain |
| `src/bmw_pm/review/service.py` | PM decisions and immutable edits; persistence enforces concurrency and records audit events. | Retain |
| `src/bmw_pm/storage/__init__.py` | Public module exports; keeps the application boundary explicit. | Retain |
| `src/bmw_pm/storage/database.py` | SQLite persistence, immutable revisions and an append-only chained application audit trail. | Retain |
| `src/bmw_pm/utils.py` | Core hashing, timestamps and reversible-position text redaction helpers. | Retain |
| `src/bmw_pm/validation.py` | Check stored provenance, scope and scoring invariants without calling a model. | Retain |
| `tests/test_audit.py` | Exports: _requirement, test_review_revision_idempotency_stale_conflict_and_replay, test_audit_is_append_only_and_tamper_is_detected | Retain |
| `tests/test_hosting.py` | Hosting safety fixtures are synthetic; not model-quality evaluations. | Retain |
| `tests/test_provenance.py` | Exports: _feedback_book, test_feedback_grouping_provenance_and_unknowns, test_one_feedback_id_remains_one_evidence_unit_after_100_duplicate_rows, test_ambiguous_headers_are_not_guessed, test_source_instruction_cannot_change_application_state | Retain |
| `tests/test_scoring.py` | Exports: _policy, _requirement, _score, test_documented_score_arithmetic_and_policy_reversal, test_unknowns_are_intervals_and_known_weights_are_not_renormalized, test_partial_processing_expands_reach_and_zero_scope_stays_unknown, test_duplicate_signals_do_not_inflate_unique_record_recurrence, test_mixed_and_neutral_signals_are_context_not_numeric_support, test_requirement_reach_uses_configured_applicable_powertrain_scope | Retain |
| `tests/test_workspace_import.py` | Synthetic compatibility fixtures; no customer material. | Retain |
| `ui/app.py` | Streamlit PM workbench; delegate workflow rules to core application services. | Retain |
| `ui/hosting_access.py` | Hosted access boundary for the prototype review workbench. | Retain |
| `uv.lock` | Locked core dependency resolution; retain for reproducibility. | Retain |
| `yazid-scraping-attempt` | Blank placeholder; recommended removal. | Review removal/consolidation recommendation |
| `src/bmw_pm/data_pipeline/youtube_research/.env.example` | Credential/configuration template; actual .env stays ignored. | Moved; keep responsibility isolated |
| `src/bmw_pm/data_pipeline/youtube_research/.gitignore` | Exclude secrets, local data, caches and generated artifacts. | Moved; keep responsibility isolated |
| `src/bmw_pm/data_pipeline/youtube_research/README.md` | YouTube vehicle research agent | Moved; keep responsibility isolated |
| `src/bmw_pm/data_pipeline/youtube_research/agent.py` | CLI-only YouTube evidence research; no user-supplied video links needed. | Moved; keep responsibility isolated |
| `src/bmw_pm/data_pipeline/youtube_research/frontend/index.html` | Optional collector browser; primary PM decisions remain in ui/app.py. | Moved; keep responsibility isolated |
| `src/bmw_pm/data_pipeline/youtube_research/requirements.txt` | Isolated optional collector dependencies; not part of the core environment. | Moved; keep responsibility isolated |
| `src/bmw_pm/data_pipeline/youtube_research/tests/test_agent.py` | Exports: test_daily_quota_does_not_retry, test_ip_block_stops_requests_but_processes_saved_transcripts, test_transcript_cache_language_scope_and_corruption, test_rate_limit_retries_and_redacts, test_discovery_preserves_results_when_limited, test_rate_limit_without_results_is_not_success, test_queries, test_selection_dedup, test_quote_timestamp_validation, test_parse, test_parse_rejects_missing_observations, test_generation_match_and_repeat_selection, test_duplicate_segment_starts_and_malformed_observations, test_invalid_dates | Moved; keep responsibility isolated |
| `src/bmw_pm/data_pipeline/youtube_research/tests/test_upload.py` | Exports: payload, test_parse_subtitles_and_vtt, test_invalid_subtitles, test_upload_contract_rejects_bad_input, test_subtitle_analysis_preserves_bytes_and_validates_quotes, test_media_transcription_reused_for_identical_bytes, test_transcription_failure_keeps_original | Moved; keep responsibility isolated |
| `src/bmw_pm/data_pipeline/youtube_research/tests/test_web.py` | Exports: server, request, test_saved_runs_and_transcripts, test_paths_cannot_escape_output, test_cross_origin_run_rejected, test_upload_route_origin_validation_and_launch, test_run_passes_form_as_arguments | Moved; keep responsibility isolated |
| `src/bmw_pm/data_pipeline/youtube_research/upload_research.py` | Authorized local media/transcript input; no YouTube network access. | Moved; keep responsibility isolated |
| `src/bmw_pm/data_pipeline/youtube_research/web.py` | Local review interface. Run: python web.py | Moved; keep responsibility isolated |
