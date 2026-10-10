"""Hosting safety fixtures are synthetic; not model-quality evaluations."""
import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError
from streamlit.testing.v1 import AppTest

from bmw_pm.contracts import HostedSettings
from bmw_pm.hosting import hosted_mode, hosted_settings, install_snapshot, password_matches
from bmw_pm.storage import Database

APP_PASSWORD = "synthetic-team-password-long"
ADMIN_PASSWORD = "synthetic-admin-password-long"


def settings(path, payload):
    return HostedSettings(database_path=str(path), app_password=APP_PASSWORD,
        admin_password=ADMIN_PASSWORD, bootstrap_sha256=hashlib.sha256(payload).hexdigest())


def test_hosted_access_fails_closed_and_handles_unicode():
    assert hosted_mode({"RENDER": "true", "BMW_PM_HOSTED": "0"})
    assert not hosted_mode({})
    with pytest.raises(ValidationError):
        hosted_settings({})
    with pytest.raises(ValueError, match="differ"):
        hosted_settings({"BMW_PM_APP_PASSWORD": APP_PASSWORD, "BMW_PM_ADMIN_PASSWORD": APP_PASSWORD})
    assert not password_matches("incorrect", APP_PASSWORD)
    assert not password_matches("wrong \N{SNOWMAN}", APP_PASSWORD)
    assert password_matches(APP_PASSWORD, APP_PASSWORD)


def test_setup_rejects_unauthorized_or_changed_upload_and_preserves_existing(tmp_path):
    source = Database(tmp_path / "synthetic.db")
    source.initialize()
    payload = source.path.read_bytes()
    target = tmp_path / "hosted.db"
    config = settings(target, payload)
    with pytest.raises(ValueError, match="Incorrect"):
        install_snapshot(payload, config, "incorrect")
    with pytest.raises(ValueError, match="SHA-256"):
        install_snapshot(payload + b"changed", config, ADMIN_PASSWORD)
    assert not target.exists()
    target.write_bytes(b"existing decision history")
    with pytest.raises(ValueError, match="already exists"):
        install_snapshot(payload, config, ADMIN_PASSWORD)
    assert target.read_bytes() == b"existing decision history"


def test_setup_rejects_noncanonical_snapshot(tmp_path):
    db = Database(tmp_path / "empty.db")
    db.initialize()
    payload = db.path.read_bytes()
    target = tmp_path / "hosted.db"
    with pytest.raises(ValueError, match="validation"):
        install_snapshot(payload, settings(target, payload), ADMIN_PASSWORD)
    assert not target.exists()
    assert not (tmp_path / ".bootstrap-lock").exists()


def test_unauthenticated_ui_never_opens_database(tmp_path, monkeypatch):
    target = tmp_path / "must-not-exist.db"
    monkeypatch.setenv("BMW_PM_HOSTED", "1")
    monkeypatch.setenv("BMW_PM_DB_PATH", str(target))
    monkeypatch.setenv("BMW_PM_APP_PASSWORD", APP_PASSWORD)
    monkeypatch.setenv("BMW_PM_ADMIN_PASSWORD", ADMIN_PASSWORD)
    app = AppTest.from_file(str(Path("ui/app.py").resolve())).run(timeout=30)
    assert not app.exception
    assert any(item.value == "Team sign-in" for item in app.subheader)
    assert not target.exists()
    assert not app.selectbox
    app.text_input[0].set_value("incorrect")
    app.button[0].click().run(timeout=30)
    assert not app.exception
    assert not target.exists()
    assert any(item.value == "Incorrect password." for item in app.error)
    app.text_input[0].set_value(APP_PASSWORD)
    app.button[0].click().run(timeout=30)
    assert not app.exception
    assert any(item.value == "Initial database setup" for item in app.subheader)
    assert not target.exists()


def test_hosted_workbench_audits_access_and_hides_raw_locator_channel(tmp_path, monkeypatch):
    db = Database(tmp_path / "synthetic.db")
    db.initialize()
    monkeypatch.setenv("BMW_PM_HOSTED", "1")
    monkeypatch.setenv("BMW_PM_DB_PATH", str(db.path))
    monkeypatch.setenv("BMW_PM_APP_PASSWORD", APP_PASSWORD)
    monkeypatch.setenv("BMW_PM_ADMIN_PASSWORD", ADMIN_PASSWORD)
    app = AppTest.from_file(str(Path("ui/app.py").resolve())).run(timeout=30)
    app.text_input[0].set_value(APP_PASSWORD)
    app.button[0].click().run(timeout=30)
    assert not app.exception
    assert "source_locator" not in app.selectbox[0].options
    assert all(field.label != "SQLite database" for field in app.text_input)
    assert db.audit_events()[-1].action == "read_hosted_workbench"
    assert db.verify_audit_chain()[0]
