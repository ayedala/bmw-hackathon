"""YouTube discovery, readiness and handoff into the decision workbench."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import streamlit as st


def _env_value(name: str, research_dir: Path) -> bool:
    if os.environ.get(name, "").strip():
        return True
    env_file = research_dir / ".env"
    if not env_file.is_file():
        return False
    try:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            match = re.match(rf"\s*(?:export\s+)?{re.escape(name)}\s*=\s*(.*?)\s*$", line)
            if match and match.group(1).strip().strip("\"'"):
                return True
    except OSError:
        return False
    return False


def _runs(output_dir: Path, *additional_output_dirs: Path) -> list[dict]:
    runs = []
    for source_dir in dict.fromkeys((output_dir, *additional_output_dirs)):
        if not source_dir.exists():
            continue
        for evidence_file in sorted(source_dir.glob("*/evidence.json"), key=lambda p: p.parent.name, reverse=True):
            try:
                findings = json.loads(evidence_file.read_text(encoding="utf-8"))
                sources_file = evidence_file.parent / "sources.json"
                sources = json.loads(sources_file.read_text(encoding="utf-8")) if sources_file.exists() else []
                runs.append({"path": evidence_file.parent, "name": evidence_file.parent.name,
                             "findings": findings if isinstance(findings, list) else [],
                             "sources": sources if isinstance(sources, list) else []})
            except (OSError, ValueError):
                continue
    return runs


def render(database, root: Path, *, hosted: bool = False) -> None:
    research_dir = root / "src/bmw_pm/data_pipeline/youtube_research"
    output_dir = research_dir / "output"
    st.subheader("YouTube customer research")
    st.write("Discover owner and reviewer videos for a BMW generation, validate findings against retrieved transcript quotes, then bring eligible evidence into the shared BMW decision workflow.")
    st.caption("YouTube search region is a discovery filter, not proof of the speaker’s market. Video counts never become BMW customer-prevalence counts. Drafts and priorities remain subject to PM review.")

    api_ready = _env_value("YOUTUBE_API_KEY", research_dir)
    agent_ready = _env_value("OPENAI_API_KEY", research_dir)
    runtime = research_dir / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    runtime_ready = runtime.is_file()
    if hosted:
        st.info("Live YouTube collection runs locally because it retrieves public captions and uses your configured research credentials. Imported YouTube findings remain available here for decision review.")
    else:
        status, setup = st.columns(2)
        with status, st.container(border=True):
            st.markdown("**Research readiness**")
            st.write(f"YouTube Data API key: {'Ready' if api_ready else 'Not configured'}")
            st.write(f"OpenAI extraction key: {'Ready' if agent_ready else 'Not configured'}")
            st.write(f"Research runtime: {'Ready' if runtime_ready else 'Not installed'}")
            st.caption("Key values are never displayed. Configure them only in the ignored local `.env` file in the YouTube research folder.")
        with setup, st.container(border=True):
            st.markdown("**One-time local setup**")
            st.code("cd src/bmw_pm/data_pipeline/youtube_research\npython -m venv .venv\n.venv/Scripts/python.exe -m pip install -r requirements.txt\ncopy .env.example .env", language="powershell")
            st.caption("Then add YOUTUBE_API_KEY and OPENAI_API_KEY to that local .env. The key fields are intentionally not collected or stored by this app.")

        if not runtime_ready:
            st.info("Install the research runtime using the setup commands above. You can still inspect any saved research runs below.")
        elif not (api_ready and agent_ready):
            absent = [name for name, ready in (("YOUTUBE_API_KEY", api_ready), ("OPENAI_API_KEY", agent_ready)) if not ready]
            st.info("Research is ready to launch once these local credentials are configured: " + ", ".join(absent) + ".")
        else:
            with st.container(border=True):
                st.markdown("**Start a new discovery run**")
                profile = st.selectbox("Vehicle generation", ["BMW 5 Series · G60", "BMW 1 Series · F70", "BMW 7 Series · G70"], key="yt_vehicle")
                config = {
                    "BMW 5 Series · G60": ("BMW 5 Series", "G60", "Europe", "DE", ["en", "de"]),
                    "BMW 1 Series · F70": ("BMW 1 Series", "F70", "Europe", "DE", ["en", "de"]),
                    "BMW 7 Series · G70": ("BMW 7 Series", "G70", "Europe", "DE", ["en", "de"]),
                }[profile]
                vehicle, generation, market, region, languages = config
                period, cap = st.columns(2)
                with period:
                    start_date = st.date_input("Published from", value=date(2023, 1, 1), key="yt_from")
                    end_date = st.date_input("Published through", value=date.today(), key="yt_to")
                with cap:
                    max_videos = st.number_input("Maximum videos (0 = all matched)", min_value=0, max_value=200, value=5, key="yt_max")
                    probe = st.checkbox("Probe mode: stop after first readable transcript", value=True, key="yt_probe")
                state = st.session_state.get("youtube_research_process")
                if state and state["process"].poll() is None:
                    st.warning("A YouTube research run is still running. Refresh this page to check its status.")
                else:
                    if st.button("Start YouTube research", type="primary", key="start_youtube_research"):
                        if start_date > end_date:
                            st.error("The start date must be on or before the end date.")
                        else:
                            from uuid import uuid4
                            run_dir = output_dir / ("workbench-" + uuid4().hex[:12])
                            run_dir.mkdir(parents=True, exist_ok=False)
                            command = [str(runtime), str(research_dir / "agent.py"),
                                "--vehicle", vehicle, "--generation", generation,
                                "--market", market, "--region", region,
                                "--languages", *languages,
                                "--from-date", start_date.isoformat(), "--to-date", end_date.isoformat(),
                                "--max-videos", str(int(max_videos)), "--out", str(run_dir)]
                            if probe:
                                command.append("--probe-only")
                            log_path = run_dir / "workbench.log"
                            log_file = log_path.open("ab")
                            process = subprocess.Popen(command, cwd=research_dir,
                                stdout=log_file, stderr=subprocess.STDOUT,
                                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                            st.session_state["youtube_research_process"] = {
                                "process": process, "log_file": log_file, "run_dir": run_dir, "log_path": log_path}
                            st.success(f"Research started. Output will be saved under `{run_dir.relative_to(root)}`.")
                            st.rerun()
                state = st.session_state.get("youtube_research_process")
                if state:
                    code = state["process"].poll()
                    if code is None:
                        st.info("Research is running. Select **Refresh run status** to check progress.")
                    else:
                        st.success("Research finished." if code == 0 else f"Research finished with status {code}; inspect the run log and source-level errors.")
                    if state["log_path"].exists():
                        try:
                            st.code(state["log_path"].read_text(encoding="utf-8", errors="replace")[-8000:])
                        except OSError:
                            pass
                    if st.button("Refresh run status", key="refresh_youtube_status"):
                        st.rerun()

    runs = _runs(output_dir, root / "youtube_research_agent/output")
    st.divider()
    st.subheader("Saved research runs")
    if not runs:
        st.caption("No YouTube runs are saved in this workspace yet.")
    else:
        for run in runs:
            with st.expander(f"{run['name']} · {len(run['sources'])} discovered videos · {len(run['findings'])} validated findings"):
                st.caption(str(run["path"]))
                if run["sources"]:
                    st.dataframe([{
                        "Video": source.get("title", "Untitled"),
                        "Channel": source.get("channel", "Unknown"),
                        "Generation": source.get("generation", "Unknown"),
                        "Selected": source.get("selected", False),
                        "Transcript": source.get("retrieval_status", "unknown"),
                        "Extraction": source.get("extraction_status", "unknown"),
                        "Reason / limitation": source.get("selection_reason") or source.get("retrieval_error") or source.get("extraction_error", ""),
                    } for source in run["sources"]], hide_index=True, width="stretch")
                st.markdown("**Transcript-validated findings**")
                if not run["findings"]:
                    st.caption("No validated quote findings in this run. Video discovery alone cannot support a customer requirement.")
                for finding in run["findings"][:25]:
                    url = finding.get("url") or f"https://www.youtube.com/watch?v={finding.get('video_id', '')}&t={int(float(finding.get('timestamp_seconds') or 0))}s"
                    st.markdown(f"- [{finding.get('supporting_excerpt') or finding.get('source_statement') or 'Open cited source'}]({url}) · {finding.get('feedback_type', 'unclassified')} · `{finding.get('generation', 'generation unknown')}`")
                if len(run["findings"]) > 25:
                    st.caption(f"Showing 25 of {len(run['findings'])} findings. Full run files remain in the output folder.")
                if not hosted and st.button("Combine this run with BMW evidence", key=f"combine_{run['name']}"):
                    from bmw_pm.contracts import PolicyVersion
                    from bmw_pm.intelligence.provider import select_provider
                    from bmw_pm.pipeline import load_json, run_candidate_pipeline
                    profiles = {"G60": "g60.json", "F70": "f70.json", "G70": "g70.json"}
                    generations = sorted({item["generation"] for item in run["findings"] if item.get("generation") in profiles})
                    generation = generations[0] if generations else "G60"
                    with st.spinner("Revalidating source quotes and combining eligible evidence…"):
                        result = run_candidate_pipeline(database=database,
                            profile=load_json(root / "configs" / profiles[generation]),
                            policy=PolicyVersion.model_validate(load_json(root / "configs/exploratory_equal_v1.json")),
                            provider=select_provider("baseline", baseline_config=root / "configs/baseline_taxonomy_v1.json"),
                            youtube_runs=[run["path"]])
                    st.success(f"Created or updated {len(result['requirements'])} combined requirement cards. YouTube import accepted {sum(item['accepted'] for item in result['youtube_imports'])} findings; {len(result['unlinked_youtube_findings'])} remain unlinked for human review.")
                    st.caption("Source quote and transcript hashes were checked by the fusion importer. Alignment and customer-market applicability still require reviewer assessment.")
