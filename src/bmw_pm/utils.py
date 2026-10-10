from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, date, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from .contracts import SpanMapSegment


def utc_now() -> datetime:
    return datetime.now(UTC)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")

    def encode(item: Any) -> Any:
        if isinstance(item, (date, datetime)):
            return item.isoformat()
        if isinstance(item, Enum):
            return item.value
        if isinstance(item, Path):
            return str(item)
        raise TypeError(f"cannot canonically encode {type(item).__name__}")

    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=encode,
    )


def content_hash(value: Any) -> str:
    return sha256_bytes(canonical_json(value).encode("utf-8"))


def stable_id(prefix: str, *parts: str, length: int = 24) -> str:
    payload = "\x1f".join(parts).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(payload).hexdigest()[:length]}"


def normalize_whitespace(raw: str) -> tuple[str, list[SpanMapSegment]]:
    """Collapse whitespace while retaining a map back to the immutable source text."""
    tokens = list(re.finditer(r"\S+", raw, flags=re.UNICODE))
    if not tokens:
        return "", []
    chunks: list[str] = []
    segments: list[SpanMapSegment] = []
    clean_position = 0
    previous_end: int | None = None
    for match in tokens:
        if previous_end is not None:
            chunks.append(" ")
            segments.append(
                SpanMapSegment(
                    clean_start=clean_position,
                    clean_end=clean_position + 1,
                    raw_start=previous_end,
                    raw_end=match.start(),
                )
            )
            clean_position += 1
        token = match.group(0)
        chunks.append(token)
        segments.append(
            SpanMapSegment(
                clean_start=clean_position,
                clean_end=clean_position + len(token),
                raw_start=match.start(),
                raw_end=match.end(),
            )
        )
        clean_position += len(token)
        previous_end = match.end()
    return "".join(chunks), segments


_PII_PATTERNS = {
    "email": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    "phone_candidate": re.compile(r"(?<!\w)(?:\+?\d[\d(). -]{6,}\d)(?!\w)"),
}


def redact_pii_same_length(text: str) -> tuple[str, dict[str, int]]:
    """Conservative local redaction; offsets stay stable for evidence validation."""
    redacted = text
    counts: dict[str, int] = {}
    for label, pattern in _PII_PATTERNS.items():
        matches = list(pattern.finditer(redacted))
        counts[label] = len(matches)
        if not matches:
            continue
        chars = list(redacted)
        for match in matches:
            for index in range(match.start(), match.end()):
                if not chars[index].isspace():
                    chars[index] = "█"
        redacted = "".join(chars)
    return redacted, {key: value for key, value in counts.items() if value}
