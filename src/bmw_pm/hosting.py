"""Bounded deployment/bootstrap helpers. No cloud-provider dependency."""
from __future__ import annotations

import hashlib
import hmac
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Mapping
from uuid import uuid4

from .contracts import HostedSettings
from .storage import Database
from .utils import sha256_file
from .validation import validate_database


def hosted_mode(env: Mapping[str, str] | None = None) -> bool:
    env = os.environ if env is None else env
    return env.get("BMW_PM_HOSTED") == "1" or env.get("RENDER") == "true"


def hosted_settings(env: Mapping[str, str] | None = None) -> HostedSettings:
    env = os.environ if env is None else env
    settings = HostedSettings(database_path=env.get("BMW_PM_DB_PATH", "/var/data/bmw_pm.db"),
        app_password=env.get("BMW_PM_APP_PASSWORD", ""),
        admin_password=env.get("BMW_PM_ADMIN_PASSWORD", ""),
        bootstrap_sha256=env.get("BMW_PM_BOOTSTRAP_SHA256") or None)
    if hmac.compare_digest(settings.app_password, settings.admin_password):
        raise ValueError("Team and setup passwords must differ")
    return settings


def password_matches(candidate: str, secret: str) -> bool:
    # Bytes support non-ASCII inputs while comparison remains constant-time.
    return hmac.compare_digest(candidate.encode("utf-8"), secret.encode("utf-8"))


def session_fingerprint(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def prepare_snapshot(source: Path, destination: Path) -> dict:
    if not source.is_file():
        raise FileNotFoundError(source)
    if destination.exists() or source.resolve() == destination.resolve():
        raise ValueError("Snapshot destination must be new")
    db = Database(source)
    if not validate_database(db, expect_supplied_shape=True)["passed"]:
        raise ValueError("Source database validation failed")
    with db.connect() as c:
        db._append_audit(c, actor_id="hosting-preparation", actor_type="pipeline",
            action="export_hosted_database", object_type="database", object_id="canonical",
            object_revision=None, before_hash=None, after_hash=None,
            reason="Create private, consistent deployment snapshot; no public Git upload.",
            request_id=f"hosting-export:{uuid4().hex}", result="success")
        c.commit()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as original:
        with closing(sqlite3.connect(destination)) as snapshot:
            original.backup(snapshot)
            snapshot.execute("PRAGMA journal_mode=DELETE")
    return {"path": str(destination), "sha256": sha256_file(destination),
            "byte_count": destination.stat().st_size}


def install_snapshot(payload: bytes, settings: HostedSettings, admin_password: str) -> dict:
    if not password_matches(admin_password, settings.admin_password):
        raise ValueError("Incorrect setup password")
    if not settings.bootstrap_sha256:
        raise ValueError("Set the approved database SHA-256 before uploading")
    if len(payload) > 256 * 1024 * 1024 or not payload.startswith(b"SQLite format 3\x00"):
        raise ValueError("Expected a SQLite snapshot no larger than 256 MiB")
    digest = hashlib.sha256(payload).hexdigest()
    if not hmac.compare_digest(digest, settings.bootstrap_sha256):
        raise ValueError("Snapshot does not match the approved SHA-256")
    target = Path(settings.database_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lock = target.parent / ".bootstrap-lock"
    lock.mkdir()  # Fail closed if another setup is in progress.
    temporary = target.parent / f".bootstrap-{uuid4().hex}.db"
    try:
        if target.exists():
            raise ValueError("A database already exists; refusing to replace review history")
        temporary.write_bytes(payload)
        with closing(sqlite3.connect(temporary)) as c:
            c.execute("PRAGMA trusted_schema=OFF")
            if c.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Snapshot integrity check failed")
            if c.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise ValueError("Snapshot contains unresolved references")
        db = Database(temporary)
        report = validate_database(db, expect_supplied_shape=True)
        if not report["passed"]:
            raise ValueError("Snapshot failed canonical evidence/audit validation")
        with db.connect() as c:
            db._append_audit(c, actor_id="hosted-setup", actor_type="pipeline",
                action="restore_hosted_database", object_type="database_snapshot", object_id=digest,
                object_revision=None, before_hash=None, after_hash=digest,
                reason="One-time private restore of hash-approved canonical evidence.",
                request_id=f"hosting-restore:{digest}", result="success")
            c.commit()
            c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            c.execute("PRAGMA journal_mode=DELETE")
        temporary.rename(target)
        return {"approved_sha256": digest, "validation": report}
    finally:
        for suffix in ("", "-wal", "-shm"):
            Path(str(temporary) + suffix).unlink(missing_ok=True)
        lock.rmdir()
