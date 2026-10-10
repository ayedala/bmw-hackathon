"""YouTube research stays visible before credentials arrive and preserves source runs."""
import json
from pathlib import Path
import sys
import shutil
from uuid import uuid4

from streamlit.testing.v1 import AppTest

from bmw_pm.storage import Database
sys.path.insert(0, str(Path(__file__).parents[1] / "ui"))
from youtube_research_view import _env_value, _runs


def fresh_test_dir(name: str) -> Path:
    path = Path(".tmp") / f"{name}-{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=False)
    return path


def test_credential_readiness_never_requires_displaying_values(monkeypatch):
    research = fresh_test_dir("youtube-keys")
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert not _env_value("YOUTUBE_API_KEY", research)
    (research / ".env").write_text("YOUTUBE_API_KEY=private-example\nOPENAI_API_KEY=\n", encoding="utf-8")
    assert _env_value("YOUTUBE_API_KEY", research)
    assert not _env_value("OPENAI_API_KEY", research)
    shutil.rmtree(research)


def test_saved_runs_keep_source_quote_and_video_locator():
    workspace = fresh_test_dir("youtube-runs")
    out = workspace / "output" / "run-one"
    out.mkdir(parents=True)
    (out / "sources.json").write_text(json.dumps([{"video_id": "abcdefghijk"}]), encoding="utf-8")
    (out / "evidence.json").write_text(json.dumps([{
        "video_id": "abcdefghijk", "supporting_excerpt": "Exact transcript words",
        "timestamp_seconds": 12.0, "generation": "G60", "feedback_type": "negative",
    }]), encoding="utf-8")
    runs = _runs(workspace / "output")
    assert len(runs) == 1
    assert runs[0]["findings"][0]["supporting_excerpt"] == "Exact transcript words"
    assert runs[0]["findings"][0]["timestamp_seconds"] == 12.0
    shutil.rmtree(workspace)


def test_youtube_workspace_renders_without_bmw_requirements(monkeypatch):
    monkeypatch.delenv("BMW_PM_HOSTED", raising=False)
    monkeypatch.delenv("RENDER", raising=False)
    workspace = fresh_test_dir("youtube-app")
    db = Database(workspace / "empty.db")
    db.initialize()
    monkeypatch.setenv("BMW_PM_DATABASE", str(db.path))
    app = AppTest.from_file(str(Path("ui/app.py").resolve()), default_timeout=30).run()
    app.radio[0].set_value("YouTube research").run()
    assert not app.exception
    assert any("YouTube customer research" in item.value for item in app.subheader)
    assert any("YouTube Data API key" in item.value for item in app.markdown)
    assert any("Not configured" in item.value for item in app.markdown)
    shutil.rmtree(workspace)
