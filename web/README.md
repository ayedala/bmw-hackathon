# BMW Product Decision Lab — web UI

Next.js 15 (App Router, TypeScript strict), Tailwind CSS 3, Radix primitives (shadcn-style components in `components/ui`), Recharts, cmdk.
The default page is Decision Studio, connected to the existing Python advisor and configured evidence database. The planning workbench at `/overview` reads US G60 customer evidence from that database and keeps its review actions browser-local.

## Run Decision Studio

For a shared team dataset, configure `DATABASE_URL` and follow the [Supabase migration and collaborator setup](../docs/SUPABASE.md). The same frontend uses the shared database; each collaborator keeps their connection string in their own ignored `.env.local`. The tracked root `.env` contains blank placeholders only.

Keep `OPENAI_API_KEY` in the repository-root `.env.local` file. Install the Python `ai` dependencies in the repository's `.venv` and import the private database first. Then:

```powershell
cd web
npm ci --ignore-scripts
npm run dev
```

Open `http://127.0.0.1:3000`. The single Next.js server launches a bounded Python worker for each request; no separate API server is required. `BMW_REPO_ROOT` overrides the repository location and `BMW_PYTHON` can select another Python executable. API credentials and model selection remain server-side. The server binds to loopback; the advisor route rejects non-local hosts and cross-origin requests. This adapter is for the local app, not an authenticated hosted deployment.

The three input paths call the same `run_advisor` used by `ui/agent.py`: assess an idea, recommend an improvement, or compare 2–5 ideas. They retain existing scope filters, public web research, citation validation, unknown costs and deterministic scenario arithmetic. Progress streams while research runs, and errors never substitute demo recommendations. Requests/results stay in browser memory across navigation; download a completed brief to retain it across a reload. Model identity remains in its JSON provenance, not in the normal interface. Planning drafts are never passed to the live advisor as evidence.

## Transcript memory and YouTube quota

Open **Video memory** to paste or upload a `.txt`, `.vtt` or `.srt` transcript, with its YouTube URL, generation and optional established market. This saves immutable, deduplicated transcript versions in the same local database without using YouTube or OpenAI quota. Supplied scope and transcript claims remain unreviewed. The advisor selects up to six relevant excerpts, with at most two per video, and retains the exact stored character span, hash and source link. Feedback denominators do not include video excerpts.

**Import saved research** runs the existing transcript/quote validator over outputs from both the new collector directory and its legacy location. Retrieved transcripts with a known research generation also become reusable whole-transcript memory, even if extraction is empty or fails because of quota; original transcript bytes and hashes are retained. Older runs can establish generation through an accepted finding. Live assessments perform this synchronization before retrieval. Missing or unreadable transcripts contribute no invented evidence. Future collector runs can be imported when quota returns; the upload route works now with transcripts already available to you.

The `/api/advisor` route uses newline-delimited events from `python -m bmw_pm.advisor.bridge`. Actions are allowlisted, request bodies are capped at 1 MB, one live research run is allowed at a time, and workers have a ten-minute limit. There are no browser-controlled model IDs, command arguments, database paths or API credentials. Financial scenarios reuse `bmw_pm.advisor.finance.scenario_results`.

```bash
cd web
npm install
npm run dev        # http://localhost:3000
npm run typecheck && npm run lint && npm run build
```

## Planning workbench data

The UI follows the successor-planning work on `main` (`42dc8ab`, "Integrate refined Figma workbench"): same brand tokens, IBM Plex Sans, the 7 authored successor proposals and the `PriorityFactors` / `PriorityPolicy` method. The Streamlit workbench in `ui/` is unchanged.

`lib/data/load.ts` reads, on each request, relative to the repository root (override with `BMW_REPO_ROOT`):

| File | Used as |
|---|---|
| `configs/successor_proposals_v1.json` | The 7 requirements: outcome, value, interpretation, future assumption, contrary evidence, validation, review trigger, anchors, seed factors |
| `configs/planning_public_context.json` | Curated planning context (ADAC, Mercedes-Benz USA, IEA) |
| `configs/exploratory_equal_v1.json`, `configs/g60.json` | Decision-engine value policy and vehicle profile |
| `src/bmw_pm/data_pipeline/web_research/data/…` (falls back to `external_research_pipeline/data/…`) | `ProcessedEvidence` and `ResearchRun` from the web-research pipeline |
| `research/web_evidence_seed.jsonl` | Curated research seeds |
| Configured private SQLite/PostgreSQL database | Redacted US G60 anchors, validated signal spans and unique-ID denominator (read-only) |

`scripts/export_planning_snapshot.py` opens the configured SQLite or PostgreSQL database read-only. It returns the nine proposal anchors as redacted source text with spreadsheet locators, all validated US G60 extracted signals, and the unique feedback-ID denominator. The server caches the snapshot for five minutes. No private customer text is committed to Git. If the database is missing or any proposal anchor does not resolve, that proposal is hidden. The seven authored proposals and their factor ratings are still unreviewed drafts, not BMW-approved requirements or measured impacts.

Feedback-theme rows are built from extracted signal domains and unique feedback IDs. A complaint or aspiration is a potential concern; praise is preservation context, not automatic contradiction. A source span does not establish that the proposed solution is correct. The fabricated customer comments, competitor comparison and seeded PM decision formerly supplied by `lib/data/fixtures/` have been removed. Curated web seeds remain discovery notes until matched and verified; the UI does not rate competitive parity from them.

**CRPS** is `bmw_pm.decision.planning.priority_score` — `25 × [impact·w + evidence·w + market fit·w + (4 − uncertainty)·w]` — ported to `lib/domain/scoring.ts`. The what-if weights are shown on Prioritization, in every workspace and in Settings.

PM actions on the Next.js planning pages create browser-local `PriorityAssessment`s and an audit trail on this device. They are not shared database decisions. Use the Python review workbench (`uv run streamlit run ui/app.py`) for shared, persisted requirements and audited PM actions. The local web actions require a reviewer ID, rationale and explicit acknowledgement for approval; editing creates a new local revision. Decisions can export a Markdown brief.

As in `proposal_for()`, the US 5 Series proposals are never transferred to another market. DE / CN / EU show which evidence exists and what a transfer would need.

## Desktop app (macOS)

A ready-built app is at `web/dist/BMW Product Decision Lab.app` (Apple Silicon). Double-click it, or drag it to Applications.
It runs the UI in its own window with a local server bound to 127.0.0.1, and reads evidence from this repository
(found automatically at `~/bmw-hackathon`; change it under File → Choose Repository Folder). External source links open in your browser.

Rebuild on a Mac:

```bash
cd web
npm install
npm run app:mac:arm64      # → dist/BMW Product Decision Lab-0.1.0-arm64.dmg (ad-hoc signed)
npm run app                # run the desktop app without packaging
```
