# BMW Product Decision Lab — web UI

Next.js 15 (App Router, TypeScript strict), Tailwind CSS 3, Radix primitives (shadcn-style components in `components/ui`), Recharts, cmdk.
The Streamlit workbench in `ui/` and the Python packages are unchanged.

```bash
cd web
npm install
npm run dev        # http://localhost:3000
npm run typecheck && npm run lint && npm run build
```

## Data

The UI follows the successor-planning work on `main` (`42dc8ab`, "Integrate refined Figma workbench"): same brand tokens, IBM Plex Sans, the 7 authored successor proposals and the `PriorityFactors` / `PriorityPolicy` method. The Streamlit workbench in `ui/` is unchanged.

`lib/data/load.ts` reads, on each request, relative to the repository root (override with `BMW_REPO_ROOT`):

| File | Used as |
|---|---|
| `configs/successor_proposals_v1.json` | The 7 requirements: outcome, value, interpretation, future assumption, contrary evidence, validation, review trigger, anchors, seed factors |
| `configs/planning_public_context.json` | Curated planning context (ADAC, Mercedes-Benz USA, IEA) |
| `configs/exploratory_equal_v1.json`, `configs/g60.json` | Decision-engine value policy and vehicle profile |
| `src/bmw_pm/data_pipeline/web_research/data/…` (falls back to `external_research_pipeline/data/…`) | `ProcessedEvidence` and `ResearchRun` from the web-research pipeline |
| `research/web_evidence_seed.jsonl` | Curated research seeds |

Anchor records (G60-0271 etc.) are real supplied feedback IDs; their verbatim text stays in the private `bmw_pm.db` and is never copied here. Hypotheses, findings, additional customer signals and competitor specs in `lib/data/fixtures/` are labelled **Synthetic** in the UI.

**CRPS** is `bmw_pm.decision.planning.priority_score` — `25 × [impact·w + evidence·w + market fit·w + (4 − uncertainty)·w]` — ported to `lib/domain/scoring.ts`. The what-if weights are shown on Prioritization, in every workspace and in Settings.

PM actions follow the workbench rules: priority ratings are saved as immutable `PriorityAssessment`s with reviewer ID and rationale; approval needs a saved assessment, a reviewer ID and an explicit uncertainty acknowledgement; editing creates a new revision that does not inherit the old priority; evidence links can be assessed (`EvidenceLinkJudgment`); Decisions exports a Markdown decision brief. Everything is appended to a hash-chained audit trail stored on this device (not in `bmw_pm.db`; reset under Settings).

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
