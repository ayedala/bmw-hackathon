# Guided product research website

For collaborators working against the same database, see [shared Supabase setup](SUPABASE.md). Both local interfaces and the CLI support the configured shared PostgreSQL connection while preserving the existing advisor logic.

The new frontend is available through `cd web` then `npm run dev` at `http://127.0.0.1:3000`. It uses the incoming Next.js workbench's components and the same Python advisor described below. See [frontend and transcript-memory setup](../web/README.md#run-decision-studio). The Streamlit entry points remain available.

The web adapter synchronizes saved YouTube runs through the existing quote/timestamp validator before calling `run_advisor`. Retrieved transcripts with a recorded research generation and manually supplied transcripts are kept as immutable, deduplicated source memory in SQLite, including transcripts whose extraction was empty or failed. The source's URL, hash, supplied scope and exact stored character range accompany selected excerpts. Known incompatible markets/generations are excluded; unknown market/powertrain and user-supplied scope remain explicit limitations. Video findings and transcript excerpts are not additional customer records, and can describe the same video. Manual transcript saving needs no YouTube or LLM quota. This is evidence retrieval memory, not model training or automatic approval.

Start with `uv run streamlit run ui/agent.py` (or the compatible `ui/mocktest.py` entry point). Install the `ai` extra and import the private dataset first.

## Configure the app

Open **App settings**, enter the API key in the password field and optionally a project ID, then select **Save and test connection**. The check sends only a short public test message, with a 32-token output cap and no search or customer data. It verifies generation access and available quota at that moment; it does not verify the full research workflow or future quota. A response stopped at the probe's token limit counts as accepted access, as described in the official [OpenAI reasoning documentation](https://developers.openai.com/api/docs/guides/reasoning); incomplete research responses still fail.

**Remember on this computer** saves a tested key in the unencrypted local `.env.advisor` file, excluded from Git. It does not modify existing `.env` files. Leave the box unchecked for browser-session use only; hosted mode supports session-only changes. A failed check or save leaves the previous connection active. The form clears entered credentials after submission and never prefills stored keys. The checked indicator applies only to the exact key, project and server-configured model used in that session.

New sessions discover `.env.advisor`, then `.env.local`, then the tracked `.env` template, then `youtube_research_agent/.env`, then the server's `OPENAI_API_KEY`. The settings screen also permits explicitly selecting the server connection. Dotenv discovery accepts only key/project fields and never executes file contents. Keys are never included in reports. The normal Decision Studio interface has no API-key or AI-model inputs; `BMW_PM_OPENAI_MODEL` is an app-owner server setting. Model identity remains in the downloaded run provenance for reproducibility, rather than in the decision interface. Return with **Back to Decision Studio**; submitted decision fields and completed reports survive this navigation.

## User journeys

- **Assess my idea:** supply a proposal, model, market and objective. The report examines customer need, competitor implementations, technical dependencies, release gates, cost drivers and revenue mechanism, alongside an alternative.
- **Find the next improvement:** choose the 1, 5 or 7 Series. All configured customer-need topics remain available for comparison. The LLM proposes concrete options and explains a provisional preference with supporting and preservation evidence.
- **Compare several ideas:** enter two to five distinct ideas, one per line. Each receives its own option in the original order. Citation and option-coverage validation rejects missing or merged options.

The agent asks decision-relevant follow-up questions in the result. Enter answers in the constraints field and rerun to refine the assessment. A report retains its original scope even if the next request's widgets change.

## Evidence and research flow

1. Open the database in a read-only SQLite snapshot. Filter feedback by exact generation, country and selected powertrain. Missing market coverage remains visible. Undated feedback cannot be filtered to a model year.
2. Recompute the existing deterministic taxonomy summaries in memory. Count unique feedback records, preserve praise and mixed statements, and retrieve a bounded selection of relevant examples. These are baseline topic counts, not measured LLM accuracy or representative customer demand.
3. Ask the LLM for retrieval synonyms and public research questions. Retrieve supporting context from matched studies, supplied sales/equipment, stored public/company context, and canonical equipment/video evidence when those tables exist. Preserve market, family, year and source limitations. State charging counts are excluded unless a state scope exists; only their national total can be selected here.
4. Use a separate web-enabled call with public topic questions. Private database excerpts and financial assumptions are excluded from this call. It is bounded to eight web tool calls; it is not an exhaustive market census. Preserve actual search annotations, source URLs, actions and returned model identity. Missing searches/citations fail visibly. With `FIRECRAWL_API_KEY` in the server environment or Git-ignored `.env.local`, the model may additionally request up to two of those exact cited public HTTPS pages for bounded main-text inspection. Install `uv sync --extra ai --extra scrape` locally. These inspected pages are attached as separate evidence with their URL and retrieval date; failed inspections do not become evidence. No private excerpts are sent to the page-inspection service.
5. Send selected redacted excerpts and public research to the synthesis call. No database rows are modified. The output distinguishes sourced claims, inference, assumptions and unknowns, and explains comparison and delivery gates. Exact evidence-ID validation prevents nonexistent citations but does not establish semantic entailment, engineering feasibility or forecast accuracy.
6. Keep the report in the current browser session, with input fingerprint, prompt version, source selection, completed steps and API usage metadata. JSON download includes evidence locators and should be treated as private. This new session trace does not extend the main database's central read/export audit; cross-session history remains in the main review workbench.

API requests use `store=False`. This requests no Responses application-state storage; it is not a promise about all provider retention controls. The client uses the documented [Responses web search](https://developers.openai.com/api/docs/guides/tools-web-search) and [structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs) interfaces. Web citation links remain visible in the UI.

## Economics and release readiness

Public retail option prices, corporate R&D budgets, complaint counts and competitor implementations cannot establish BMW feature-specific development cost or incremental sales. The report must state those gaps and suggest estimation/validation work. A preferred option is a provisional product hypothesis, not investment or release approval.

The optional scenario editor requires explicit downside/base/upside values, an estimate source/owner or a hypothetical label, a horizon and discount rate. The existing deterministic financial calculator accounts for additional vehicle revenue, baseline cost of additional vehicles, feature revenue on existing adopters, feature cost on all adopters, annual support and upfront investment. Inputs repeat annually across the selected horizon. NPV is conditional on those inputs. No automatic ranking across incomplete or unreviewed business cases is made.

## Verification scope

Synthetic tests check scope isolation, praise retention, redaction, read-only retrieval, missing-market handling, citation rejection, comparison completeness, bounded calls, private-data exclusion from web search, financial arithmetic and all three UI journeys including reruns. These are software checks. Human relevance/entailment review, held-out recommendation evaluation, calibrated economics and engineering validation remain open.
