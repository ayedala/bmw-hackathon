# YouTube vehicle research agent

Uses **YouTube Data API v3** to search without video URLs, selects generation-matching video metadata across channels, retrieves accessible caption segments with `youtube-transcript-api`, then passes actual retrieved transcript text to the existing saved agent using the **OpenAI Agents HTTP API**, called with `curl`. Unsupported quote/timestamp pairs are discarded. No comment scraping, DRM circumvention, or fabricated transcripts.

This optional collector now lives under `src/bmw_pm/data_pipeline/youtube_research/`. It retains its own dependencies and local output. The primary Streamlit workbench exposes a **YouTube research** workspace for readiness, discovery setup, saved-run review and an explicit combine action. Imported findings are revalidated against saved transcript segments before they can link to shared requirement cards. PM requirement decisions remain in the workbench.

## Setup

Enter this directory from the repository root before running the following commands:

```bash
cd src/bmw_pm/data_pipeline/youtube_research
```

```bash
python -m venv .venv
# macOS/Linux: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env   # on Windows: copy .env.example .env
# Fill only .env locally; never commit credentials.
```

Required: **YOUTUBE_API_KEY** (enable YouTube Data API v3 on a Google Cloud project); **OPENAI_API_KEY** authorized for the saved agent, and matching OpenAI project (`OPENAI_PROJECT_ID`). The saved `OPENAI_AGENT_ID` is preconfigured. Captions use the publicly accessible caption interface where allowed; there is no special transcript key. Some videos or networks do not expose captions; those failures are recorded. The official YouTube captions.download endpoint would instead require OAuth and permission to access the relevant caption track.

## Local review interface

On Windows, run `.venv\Scripts\python.exe web.py` from this folder, then open http://127.0.0.1:8765.
The interface loads saved runs under `output/`, filters findings, links to the
original video at each quote's timestamp, and displays the retrieved transcript
with the matching segment highlighted. The Sources tab shows retrieval and
extraction failures, and Run summary shows coverage limitations.

Use New research to run the existing agent with your local `.env` credentials.
Browser runs save to `output/browser`; starting another browser run replaces
that run's result files. Other saved runs remain available in the selector.
The server binds only to your local computer. Keep this terminal running while
using the interface; press Ctrl+C to stop it.

## First video verification (CLI)

```bash
python agent.py --vehicle 'BMW 5 Series' --generation G60 --market Europe --region DE --languages en de --from-date 2023-01-01 --to-date 2026-10-10 --max-videos 0 --probe-only --out output/probe
```

After inspecting `output/probe/transcripts/*.json` and matching every cited quote/timestamp in `output/probe/evidence.json`:

```bash
python agent.py --vehicle 'BMW 5 Series' --generation G60 --market Europe --region DE --languages en de --from-date 2023-01-01 --to-date 2026-10-10 --max-videos 0 --out output/full
```

The program persists `sources.json`, `evidence.json`, `evidence.csv`, `summary.md` and retrieved transcript JSON files incrementally. A failed selected video is recorded; processing continues to the next selected candidate. `--probe-only` stops after the first *readable* transcript. `--max-videos 0` selects all metadata-matched videos discovered across search result pages; a positive value caps transcript processing.

## Combine findings with BMW evidence

From the repository root, run `bmw-pm run --provider baseline --full` after research finishes. The shared engine discovers saved YouTube output directories, revalidates quotes against saved transcripts, and combines findings with BMW feedback, studies and imported context. Alternatively use the Streamlit workbench's **YouTube research** view and select **Combine this run with BMW evidence**. `--youtube-run <output-directory>` selects an explicit saved run in the CLI and can be repeated. Missing or blocked transcripts cannot contribute evidence. See the root README for provenance, scope and scoring limitations.

## Verification and limitations

```bash
pytest -q
```

Discovery follows YouTube search result pages and selects every candidate that passes the metadata relevance filter by default. `--max-videos N` optionally limits processing; `--max-videos 0` means no selection limit. The UI also offers an optional probe mode that stops after the first readable transcript.

YouTube search still depends on its relevance-ranked results, and the metadata filter may miss videos that omit the generation name. Google currently assigns a default quota of 100 `search.list` requests per day; each additional result page is another request. If that quota runs out, the agent keeps and processes videos found so far and records a warning. Searching everything can therefore take a large share of daily quota. Search region and language are discovery aids, not evidence of where the vehicle was used or sold. The extractor does not assume reviewers are owners, never merges viewer comments with spoken statements, and validates excerpts by exact transcript substring and timestamp. Agents API permissions, actual model output structure and real-world transcript accessibility require a live integration test with working credentials. The saved agent's tools may be preserved, but a tool-dependent saved definition can require additional actions that this standalone no-environment runner does not service; failures are recorded instead of fabricated as success.

### Transcript reuse and IP blocking

Newly retrieved transcripts are cached under the selected run's `transcript_cache/`, keyed by video ID and language preference order. Repeating a browser run reuses this cache and labels the source `transcript_origin: saved`; extraction still runs again. Legacy transcript files without language provenance are retained but not automatically reused. Cache reuse is local to the output directory.

After `IpBlocked` or `RequestBlocked`, no further network transcript requests are made during that run. Remaining videos with valid saved transcripts are still processed; uncached videos are explicitly marked `skipped_ip_blocked`. Exit code 4 means transcript access was blocked, not successful complete coverage. This does not lift YouTube's restriction, and a later user-started run may attempt retrieval again.

## Analyze an authorized local file (no YouTube quota required)

Use **Analyze a file** in the review interface. Enter the original YouTube video ID, title, vehicle and generation, then choose a full-video MP3/MP4/MPEG/MPGA/M4A/WAV/WEBM file (up to 24 MiB) or UTF-8 SRT/VTT subtitles. Supply only public material you are authorized to use, with no private personal data. Uploading sends media to OpenAI for transcription and transcript text to the configured extraction agent; API charges apply.

Media transcription uses the official OpenAI audio transcription endpoint with `whisper-1` and segment timestamps. Identical media bytes reuse a local transcription cache. Subtitle files need no speech transcription. Original bytes, hashes, timestamped segments, source metadata and findings are saved in a separate `output/upload-...` run. No YouTube search or caption endpoint is called in this path. Source metadata and vehicle match are user asserted, and transcription accuracy still needs review. Supply full-video timing: an excerpt starting halfway through a video will otherwise have incorrect YouTube timestamp links.

The existing OpenAI key must have billing and permission for transcription and the configured extraction agent. Live integration is not established by fixture tests. This path requires an authorized file; it does not automatically obtain blocked YouTube media or restore automatic discovery.

API documentation: https://developers.openai.com/api/docs/guides/speech-to-text
