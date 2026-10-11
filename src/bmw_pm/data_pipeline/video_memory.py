"""Immutable transcript memory. Saving text never approves its claims or scope."""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from pydantic import Field, model_validator

from ..contracts import Contract
from ..storage import Database
from ..utils import content_hash, sha256_bytes, stable_id, utc_now


class TranscriptInput(Contract):
    video_url: str = Field(max_length=500)
    title: str = Field(min_length=1, max_length=300)
    model_code: Literal["F70", "G60", "G70"]
    market: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    transcript: str = Field(min_length=50, max_length=200000)

    @model_validator(mode="after")
    def valid_video(self) -> "TranscriptInput":
        video_id(self.video_url)
        if not self.title.strip() or len(self.transcript.strip()) < 50:
            raise ValueError("Provide a title and at least 50 characters of transcript text.")
        return self


def video_id(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme not in {"https", "http"} or parsed.username or parsed.password:
        raise ValueError("Use a YouTube video URL.")
    host = (parsed.hostname or "").lower()
    if host == "youtu.be":
        value = parsed.path.strip("/").split("/")[0]
    elif host in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        parts = parsed.path.strip("/").split("/")
        value = parts[1] if len(parts) == 2 and parts[0] in {"shorts", "embed", "live"} else parse_qs(parsed.query).get("v", [""])[0]
    else:
        raise ValueError("Use a YouTube video URL.")
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", value):
        raise ValueError("The YouTube URL must contain a valid video ID.")
    return value


def save_transcript(database: str | Path, request: TranscriptInput, *,
                    source_kind: str = "user_supplied_transcript", source_locator: dict | None = None,
                    original_transcript_json: str | None = None) -> dict:
    if not Database(database).exists():
        raise ValueError("Import the evidence database before saving transcript memory.")
    identifier = video_id(request.video_url)
    digest = sha256_bytes(request.transcript.encode("utf-8"))
    memory_id = stable_id("video_memory", identifier, request.model_code, request.market or "unknown", digest)
    payload = {**request.model_dump(mode="json"), "video_url": f"https://www.youtube.com/watch?v={identifier}",
               "video_id": identifier, "memory_id": memory_id, "transcript_sha256": digest,
               "source_kind": source_kind, "source_locator": source_locator or {}, "created_at": utc_now().isoformat()}
    if original_transcript_json is not None:
        payload["original_transcript_json"] = original_transcript_json
    storage = Database(database)
    storage.initialize()
    with storage.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("CREATE TABLE IF NOT EXISTS video_memories (memory_id TEXT PRIMARY KEY, video_id TEXT NOT NULL, model_code TEXT NOT NULL, market TEXT, created_at TEXT NOT NULL, payload_json TEXT NOT NULL)")
        inserted = connection.execute("INSERT OR IGNORE INTO video_memories VALUES (?,?,?,?,?,?)",
            (memory_id, identifier, request.model_code, request.market, payload["created_at"], json.dumps(payload))).rowcount
        if inserted:
            storage._append_audit(connection, actor_id="transcript-memory", actor_type="pipeline",
                action="save_video_transcript", object_type="video_memory", object_id=memory_id,
                object_revision=None, before_hash=None, after_hash=content_hash(payload),
                reason="Stored an immutable transcript and supplied scope; claims and scope remain unreviewed.",
                request_id=f"transcript-memory:{uuid4().hex}", result="success")
        connection.commit()
    return {"memory_id": memory_id, "inserted": bool(inserted), "video_id": identifier,
            "characters": len(request.transcript), "transcript_sha256": digest}


def memory_excerpts(connection: sqlite3.Connection, model_code: str, market: str, terms: set[str]) -> list[dict]:
    candidates, seen = [], set()
    for result in connection.execute(
        "SELECT payload_json FROM video_memories WHERE model_code=? AND (market IS NULL OR market=?) ORDER BY CASE WHEN market=? THEN 1 ELSE 0 END DESC,created_at DESC,memory_id DESC",
        (model_code, market, market)):
        row = json.loads(result[0])
        if row["video_id"] in seen:
            continue
        seen.add(row["video_id"])
        text = row["transcript"]
        if sha256_bytes(text.encode("utf-8")) != row["transcript_sha256"]:
            continue
        chunks = []
        for start in range(0, len(text), 1200):
            excerpt = text[start:start + 1200]
            if not excerpt.strip():
                continue
            relevance = len(set(re.findall(r"[a-z]{3,}", excerpt.lower())) & terms)
            chunks.append({**row, "text": excerpt, "start_char": start,
                           "end_char": start + len(excerpt), "relevance": relevance})
        chunks.sort(key=lambda chunk: (-chunk["relevance"], chunk["start_char"]))
        candidates.extend(chunks[:2])
    candidates.sort(key=lambda chunk: (-chunk["relevance"], chunk["memory_id"], chunk["start_char"]))
    return candidates[:6]
