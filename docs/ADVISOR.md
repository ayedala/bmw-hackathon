# Guided product research website

Start with `uv run streamlit run ui/agent.py` (or the compatible `ui/mocktest.py` entry point). Install the `ai` extra and import the private dataset first. Use Agent settings to select the saved project research connection, server environment, or a manually entered API key. Saved connection discovery reads `.env` first, then `youtube_research_agent/.env`; it accepts only key/project fields and never executes dotenv contents. The selected connection is shown explicitly. The model is configurable through the UI or `BMW_PM_OPENAI_MODEL`.

## User journeys

- **Assess my idea:** supply a proposal, model, market and objective. The report examines customer need, competitor implementations, technical dependencies, release gates, cost drivers and revenue mechanism, alongside an alternative.
- **Find the next improvement:** choose the 1, 5 or 7 Series. All configured customer-need topics remain available for comparison. The LLM proposes concrete options and explains a provisional preference with supporting and preservation evidence.
- **Compare several ideas:** enter two to five distinct ideas, one per line. Each receives its own option in the original order. Citation and option-coverage validation rejects missing or merged options.

The agent asks decision-relevant follow-up questions in the result. Enter answers in the constraints field and rerun to refine the assessment. A report retains its original scope even if the next request's widgets change.

## Evidence and research flow

1. Open the database in a read-only SQLite snapshot. Filter feedback by exact generation, country and selected powertrain. Missing market coverage remains visible. Undated feedback cannot be filtered to a model year.
2. Recompute the existing deterministic taxonomy summaries in memory. Count unique feedback records, preserve praise and mixed statements, and retrieve a bounded selection of relevant examples. These are baseline topic counts, not measured LLM accuracy or representative customer demand.
3. Ask the LLM for retrieval synonyms and public research questions. Retrieve supporting context from matched studies, supplied sales/equipment, stored public/company context, and canonical equipment/video evidence when those tables exist. Preserve market, family, year and source limitations. State charging counts are excluded unless a state scope exists; only their national total can be selected here.
4. Use a separate web-enabled call with public topic questions. Private database excerpts and financial assumptions are excluded from this call. It is bounded to eight tool calls; it is not an exhaustive market census. Preserve actual search annotations, source URLs, actions and returned model identity. Missing searches/citations fail visibly.
5. Send selected redacted excerpts and public research to the synthesis call. No database rows are modified. The output distinguishes sourced claims, inference, assumptions and unknowns, and explains comparison and delivery gates. Exact evidence-ID validation prevents nonexistent citations but does not establish semantic entailment, engineering feasibility or forecast accuracy.
6. Keep the report in the current browser session, with input fingerprint, prompt version, source selection, completed steps and API usage metadata. JSON download includes evidence locators and should be treated as private. This new session trace does not extend the main database's central read/export audit; cross-session history remains in the main review workbench.

API requests use `store=False`. This requests no Responses application-state storage; it is not a promise about all provider retention controls. The client uses the documented [Responses web search](https://developers.openai.com/api/docs/guides/tools-web-search) and [structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs) interfaces. Web citation links remain visible in the UI.

## Economics and release readiness

Public retail option prices, corporate R&D budgets, complaint counts and competitor implementations cannot establish BMW feature-specific development cost or incremental sales. The report must state those gaps and suggest estimation/validation work. A preferred option is a provisional product hypothesis, not investment or release approval.

The optional scenario editor requires explicit downside/base/upside values, an estimate source/owner or a hypothetical label, a horizon and discount rate. The existing deterministic financial calculator accounts for additional vehicle revenue, baseline cost of additional vehicles, feature revenue on existing adopters, feature cost on all adopters, annual support and upfront investment. Inputs repeat annually across the selected horizon. NPV is conditional on those inputs. No automatic ranking across incomplete or unreviewed business cases is made.

## Verification scope

Synthetic tests check scope isolation, praise retention, redaction, read-only retrieval, missing-market handling, citation rejection, comparison completeness, bounded calls, private-data exclusion from web search, financial arithmetic and all three UI journeys including reruns. These are software checks. Human relevance/entailment review, held-out recommendation evaluation, calibrated economics and engineering validation remain open.
