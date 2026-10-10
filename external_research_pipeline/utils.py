"""Shared helpers: URL canonicalization, hashing, text normalization, retries, logging.

This module is intentionally dependency-light. Three preferred third-party
packages are used when installed and transparently replaced by standard-library
equivalents when they are not, so that ``--dry-run`` and offline planning work
on a bare interpreter:

* ``python-dotenv``  -> minimal ``.env`` parser
* ``rapidfuzz``      -> :mod:`difflib` ratio
* ``tenacity``       -> small internal exponential-backoff decorator

Install ``requirements.txt`` to get the preferred implementations.
"""

from __future__ import annotations

import email.utils
import functools
import hashlib
import ipaddress
import logging
import random
import re
import socket
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Sequence, TypeVar
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

T = TypeVar("T")

LOGGER_NAME = "external_research_pipeline"

# --------------------------------------------------------------------------- #
# Optional dependency probes
# --------------------------------------------------------------------------- #

try:  # pragma: no cover - exercised by whichever branch is installed
    from rapidfuzz import fuzz as _rapidfuzz_fuzz
except ImportError:  # pragma: no cover
    _rapidfuzz_fuzz = None

try:  # pragma: no cover
    from tenacity import (
        retry as _tenacity_retry,
        retry_if_exception_type as _tenacity_retry_if,
        stop_after_attempt as _tenacity_stop,
        wait_exponential as _tenacity_wait,
    )
except ImportError:  # pragma: no cover
    _tenacity_retry = None

HAVE_RAPIDFUZZ = _rapidfuzz_fuzz is not None
HAVE_TENACITY = _tenacity_retry is not None


# --------------------------------------------------------------------------- #
# Environment loading
# --------------------------------------------------------------------------- #


def load_env_file(path: Path) -> dict[str, str]:
    """Load ``KEY=value`` pairs from *path* into :data:`os.environ`.

    Existing environment variables always win, so an exported shell variable
    overrides the file. Returns the mapping that was read from disk (whether or
    not it was applied), which makes the behaviour easy to assert in tests.
    """
    import os

    try:  # Preferred implementation.
        from dotenv import dotenv_values

        values = {k: v for k, v in dotenv_values(path).items() if v is not None}
    except ImportError:
        values = _parse_env_file(path)

    for key, value in values.items():
        os.environ.setdefault(key, value)
    return values


def _parse_env_file(path: Path) -> dict[str, str]:
    """Minimal ``.env`` parser used when ``python-dotenv`` is unavailable."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, raw = line.partition("=")
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export ") :].strip()
        value = raw.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            values[key] = value
    return values


# --------------------------------------------------------------------------- #
# Time
# --------------------------------------------------------------------------- #


def utc_now_iso() -> str:
    """Current UTC time as a second-precision ISO-8601 string ending in ``Z``."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# --------------------------------------------------------------------------- #
# URL handling
# --------------------------------------------------------------------------- #

#: Query parameters removed during canonicalization. These carry campaign or
#: click attribution only and never change which document is served.
TRACKING_PARAMS: frozenset[str] = frozenset(
    {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "utm_id",
        "utm_name",
        "utm_reader",
        "utm_brand",
        "gclid",
        "gbraid",
        "wbraid",
        "dclid",
        "fbclid",
        "msclkid",
        "twclid",
        "yclid",
        "igshid",
        "mc_cid",
        "mc_eid",
        "ref",
        "ref_src",
        "referrer",
        "spm",
        "scid",
        "trk",
        "cmpid",
        "ncid",
        "_ga",
        "_gl",
        "s_kwcid",
        "at_medium",
        "at_campaign",
        "sr_share",
    }
)

_MULTISLASH = re.compile(r"/{2,}")
_SCHEME_PREFIX = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://")

#: Query keys that carry credentials rather than document identity. URLs with
#: these parameters are rejected before scraping, and their values are also
#: redacted from defensive error/log formatting below.
AUTH_QUERY_KEYS: frozenset[str] = frozenset(
    {
        "access_token",
        "api-key",
        "api_key",
        "apikey",
        "auth",
        "authorization",
        "client_secret",
        "credential",
        "jwt",
        "key",
        "password",
        "secret",
        "session",
        "sig",
        "signature",
        "token",
        "x-amz-credential",
        "x-amz-signature",
    }
)

#: Two-level public suffixes that need three labels for a registrable domain.
_COMPOUND_SUFFIXES: frozenset[str] = frozenset(
    {
        "co.uk",
        "org.uk",
        "ac.uk",
        "gov.uk",
        "com.au",
        "net.au",
        "org.au",
        "co.nz",
        "co.jp",
        "com.br",
        "co.za",
        "com.tr",
    }
)


def canonicalize_url(url: str) -> str:
    """Return a stable canonical form of *url* for caching and deduplication.

    Normalizations applied: scheme forced to ``https``, lowercased host,
    ``www.`` and default-port removal, fragment removal, tracking parameter
    removal, remaining query parameters sorted, duplicate slashes collapsed and
    a trailing slash stripped.

    The scheme is unified so that the ``http://`` and ``https://`` forms of one
    page share a cache key and are not scraped (and paid for) twice. The
    canonical form is an *identity key*, not a fetch target - the scraper always
    requests the URL exactly as the search provider returned it.

    Parameters that are not in :data:`TRACKING_PARAMS` are preserved, so pages
    that are genuinely addressed by a query string (forum pagination, article
    IDs) keep their identity.
    """
    raw = (url or "").strip()
    if not raw:
        return ""
    if not _SCHEME_PREFIX.match(raw):
        # Schemeless input such as "adac.de/a/b"; a "//" inside the path must
        # not be mistaken for a scheme separator.
        raw = "https://" + raw.lstrip("/")

    try:
        parts = urlsplit(raw)
        host = (parts.hostname or "").lower()
        port = parts.port
    except ValueError:
        # Malformed IPv6 brackets and invalid ports are common provider noise.
        # An empty canonical URL makes the pre-scrape filter reject the hit.
        return ""
    # Unify the scheme: http and https serve the same document for every source
    # this pipeline targets, and separate keys would mean paying twice.
    scheme = "https"

    if host.startswith("www."):
        host = host[4:]
    netloc = host
    if port and port not in (80, 443):
        # urlsplit().hostname removes IPv6 brackets; restore them in a URL.
        rendered_host = f"[{host}]" if ":" in host else host
        netloc = f"{rendered_host}:{port}"
    elif ":" in host:
        netloc = f"[{host}]"

    path = _MULTISLASH.sub("/", parts.path or "/")
    if len(path) > 1:
        path = path.rstrip("/") or "/"

    kept = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() not in TRACKING_PARAMS]
    query = urlencode(sorted(kept), doseq=True)

    return urlunsplit((scheme, netloc, path, query, ""))


def url_safety_rejection_reason(url: str) -> str | None:
    """Return why *url* is unsafe to fetch, or ``None`` when locally allowed.

    This check deliberately does not perform DNS resolution: search results are
    untrusted input and resolving them locally would itself cross a network
    boundary. It rejects every non-HTTP(S) scheme, local-use names, embedded
    credentials, credential-bearing query strings, and literal non-global IP
    addresses (private, loopback, link-local, reserved, multicast, unspecified,
    documentation ranges, and carrier-grade NAT).

    A public hostname can still resolve to a private address after this check.
    The remote scraping provider must enforce its own redirect/DNS egress rules;
    this predicate is the deterministic pre-selection guard available locally.
    """
    raw = (url or "").strip()
    if not raw:
        return "empty url"
    if not _SCHEME_PREFIX.match(raw):
        raw = "https://" + raw.lstrip("/")
    try:
        parts = urlsplit(raw)
        scheme = parts.scheme.lower()
        host = (parts.hostname or "").rstrip(".").lower()
        # Accessing ``port`` validates malformed and out-of-range values.
        _ = parts.port
    except ValueError:
        return "malformed url"

    if scheme not in {"http", "https"}:
        return "unsupported url scheme"
    if not host:
        return "no host"
    if parts.username is not None or parts.password is not None:
        return "embedded url credentials"
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        return "local-use host"

    try:
        query_keys = {key.casefold() for key, _ in parse_qsl(parts.query, keep_blank_values=True)}
    except ValueError:
        return "malformed query string"
    if query_keys & AUTH_QUERY_KEYS:
        return "credential-bearing query"

    address = _literal_ip_address(host)
    if address is not None and not address.is_global:
        return "non-public IP address"
    return None


def _literal_ip_address(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """Parse ordinary and legacy numeric IP literals without resolving DNS."""
    candidate = host.split("%", 1)[0]  # strip an IPv6 zone identifier
    try:
        return ipaddress.ip_address(candidate)
    except ValueError:
        pass

    # Some URL stacks accept legacy IPv4 forms such as 127.1, 0177.0.0.1 or
    # 0x7f000001. Recognise only all-numeric forms so a normal hostname is never
    # passed to a resolver by accident.
    component = r"(?:0[xX][0-9a-fA-F]+|[0-9]+)"
    if not re.fullmatch(rf"{component}(?:\.{component}){{0,3}}", candidate):
        return None
    try:
        return ipaddress.ip_address(socket.inet_aton(candidate))
    except (OSError, ValueError):
        return None


def domain_of(url: str) -> str:
    """Return the lowercased host of *url* without a leading ``www.``."""
    canonical = canonicalize_url(url)
    if not canonical:
        return ""
    try:
        return (urlsplit(canonical).hostname or "").lower()
    except ValueError:
        return ""


def registrable_domain(url: str) -> str:
    """Return the registrable domain (``adac.de``) for *url*.

    Uses a small compound-suffix table rather than a full public-suffix list;
    that is sufficient for the European and US sources this pipeline targets.
    """
    host = domain_of(url)
    labels = host.split(".")
    if len(labels) <= 2:
        return host
    if ".".join(labels[-2:]) in _COMPOUND_SUFFIXES:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def url_hash(url: str, length: int = 12) -> str:
    """Deterministic short hash of the canonical form of *url*."""
    canonical = canonicalize_url(url)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:length]


def cache_filename(url: str) -> str:
    """Deterministic cache file name for *url* (stable across runs and machines)."""
    return f"{url_hash(url, 32)}.json"


# --------------------------------------------------------------------------- #
# Identifiers
# --------------------------------------------------------------------------- #


def evidence_id(source_url: str, claim: str) -> str:
    """Stable evidence identifier derived from canonical URL plus normalized claim.

    Re-running the pipeline over the same page and the same extracted claim
    yields the same ``EXT-`` id, which is what lets the processed store skip
    records it already holds instead of appending duplicates.
    """
    seed = f"{canonicalize_url(source_url)}\n{normalize_claim(claim)}"
    return "EXT-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]


def independence_group_id(canonical_url: str) -> str:
    """Stable independence-group identifier for a single origin document."""
    digest = hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()[:12]
    return "SRC-" + digest


# --------------------------------------------------------------------------- #
# Text handling
# --------------------------------------------------------------------------- #

_PUNCT = re.compile(r"[^\w\s]", flags=re.UNICODE)
_WS = re.compile(r"\s+")


def normalize_claim(text: str) -> str:
    """Normalize claim text for comparison: NFKC, casefold, de-punctuate, collapse.

    German umlauts are preserved rather than folded, because ``Ladezeit`` and
    ``Lädezeit`` are not the same word; NFKC only unifies compatibility forms.
    """
    normalized = unicodedata.normalize("NFKC", text or "")
    normalized = normalized.casefold()
    normalized = _PUNCT.sub(" ", normalized)
    return _WS.sub(" ", normalized).strip()


def claim_similarity(left: str, right: str) -> float:
    """Similarity of two claims on a 0-100 scale.

    Uses ``rapidfuzz.fuzz.token_set_ratio`` when available, which is tolerant of
    reordered and partially overlapping wording. The :mod:`difflib` fallback is
    stricter, so near-duplicates may be missed without ``rapidfuzz`` installed.
    """
    a, b = normalize_claim(left), normalize_claim(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 100.0
    if _rapidfuzz_fuzz is not None:
        return float(_rapidfuzz_fuzz.token_set_ratio(a, b))
    from difflib import SequenceMatcher

    return float(SequenceMatcher(None, a, b).ratio() * 100.0)


_BOILERPLATE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\s*!\[[^\]]*\]\([^)]*\)\s*$"),            # image-only line
    re.compile(r"^\s*\[!\[[^\]]*\]\([^)]*\)\]\([^)]*\)\s*$"),  # linked image
    re.compile(r"^\s*(cookie|datenschutz|privacy|impressum|newsletter)\b.*$", re.I),
    re.compile(r"^\s*(teilen|share|drucken|print|zur startseite)\s*$", re.I),
    re.compile(r"^\s*\|?\s*-{3,}\s*\|?\s*$"),                # orphan table rules
)


def trim_markdown(markdown: str, *, min_line_chars: int = 2) -> str:
    """Drop obvious navigation and decoration lines from scraped markdown.

    This reduces the token volume sent to the extraction model. It is a cheap
    line filter, not a content extractor - Firecrawl's ``only_main_content`` has
    already done the structural work.
    """
    kept: list[str] = []
    for line in (markdown or "").splitlines():
        stripped = line.strip()
        if len(stripped) < min_line_chars:
            if kept and kept[-1] != "":
                kept.append("")
            continue
        if any(pattern.match(stripped) for pattern in _BOILERPLATE_PATTERNS):
            continue
        kept.append(line.rstrip())
    text = "\n".join(kept)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def chunk_text(text: str, max_chars: int, overlap: int = 400) -> list[str]:
    """Split *text* into chunks of at most *max_chars*, preferring clean breaks.

    Splits on blank lines where possible and falls back to a hard character cut
    for single oversized paragraphs. Consecutive chunks share *overlap*
    characters so a claim spanning a boundary is still visible in full to at
    least one request.
    """
    body = (text or "").strip()
    if not body:
        return []
    if len(body) <= max_chars:
        return [body]
    if overlap >= max_chars:
        overlap = max_chars // 4

    chunks: list[str] = []
    cursor = 0
    length = len(body)
    while cursor < length:
        window_end = min(cursor + max_chars, length)
        if window_end < length:
            break_at = body.rfind("\n\n", cursor + max_chars // 2, window_end)
            if break_at == -1:
                break_at = body.rfind("\n", cursor + max_chars // 2, window_end)
            if break_at == -1:
                break_at = body.rfind(" ", cursor + max_chars // 2, window_end)
            if break_at != -1:
                window_end = break_at
        chunk = body[cursor:window_end].strip()
        if chunk:
            chunks.append(chunk)
        if window_end >= length:
            break
        cursor = max(window_end - overlap, cursor + 1)
    return chunks


def safe_truncate(text: str, limit: int) -> str:
    """Truncate *text* to *limit* characters with an explicit ellipsis marker."""
    if text is None:
        return ""
    return text if len(text) <= limit else text[: max(0, limit - 3)] + "..."


_SECRET_VALUE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(?:sk-(?:proj-|ant-)?|fc-)[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"(?i)(\bAuthorization\s*:\s*Bearer\s+)([^\s,;]+)"),
    re.compile(r"(?i)(\b(?:api[_-]?key|access[_-]?token|auth(?:orization)?|client[_-]?secret|key|password|secret|token)\b\s*[=:]\s*)([^\s&,;]+)"),
    re.compile(r"(?i)(\bBearer\s+)([^\s,;]+)"),
    re.compile(r"(?i)(https?://[^\s?#]+\?[^\s#]*?(?:access_token|api[_-]?key|auth|key|password|secret|signature|token)=)([^&#\s]+)"),
)


def redact_sensitive_text(value: Any, *, limit: int = 500) -> str:
    """Redact common credential forms before exception text is logged or saved."""
    text = str(value)
    text = _SECRET_VALUE_PATTERNS[0].sub("[REDACTED]", text)
    for pattern in _SECRET_VALUE_PATTERNS[1:]:
        text = pattern.sub(r"\1[REDACTED]", text)
    return safe_truncate(text, limit)


# --------------------------------------------------------------------------- #
# Retries
# --------------------------------------------------------------------------- #


def with_retries(
    *,
    attempts: int = 3,
    initial_wait: float = 1.0,
    max_wait: float = 20.0,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Retry decorator with exponential backoff, re-raising the final error.

    Delegates to ``tenacity`` when installed; otherwise applies the same policy
    with a small internal loop so behaviour does not change with the
    environment.
    """
    if _tenacity_retry is not None:  # pragma: no branch
        return _tenacity_retry(
            stop=_tenacity_stop(attempts),
            wait=_tenacity_wait(multiplier=initial_wait, max=max_wait),
            retry=_tenacity_retry_if(exceptions),
            reraise=True,
        )

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            log = logging.getLogger(LOGGER_NAME)
            delay = initial_wait
            for attempt in range(1, attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    if attempt == attempts:
                        raise
                    sleep_for = min(delay, max_wait) * (1 + random.random() * 0.1)
                    log.warning(
                        "%s failed (attempt %d/%d): %s - retrying in %.1fs",
                        func.__name__,
                        attempt,
                        attempts,
                        redact_sensitive_text(exc),
                        sleep_for,
                    )
                    time.sleep(sleep_for)
                    delay *= 2
            raise AssertionError("unreachable")  # pragma: no cover

        return wrapper

    return decorator


# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #


def setup_logging(log_path: Path, *, verbose: bool = False) -> logging.Logger:
    """Configure and return the pipeline logger.

    Writes to *log_path* (inside this folder only) and mirrors to stderr.
    Repeated calls replace handlers rather than stacking them.
    """
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")

    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    stream_handler.setFormatter(logging.Formatter("%(levelname)-7s %(message)s"))
    logger.addHandler(stream_handler)
    return logger


def get_logger() -> logging.Logger:
    """Return the pipeline logger without reconfiguring handlers."""
    return logging.getLogger(LOGGER_NAME)


# --------------------------------------------------------------------------- #
# Rate limiting
# --------------------------------------------------------------------------- #

#: Substrings that identify a provider rate-limit rejection. Matched against
#: both the exception type name and its message, because the Firecrawl SDK
#: surfaces 429s differently depending on transport.
_RATE_LIMIT_MARKERS: tuple[str, ...] = (
    "429",
    "rate limit",
    "rate-limit",
    "ratelimit",
    "too many requests",
    "quota exceeded",
    "request limit",
)

_RETRY_AFTER_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"retry[-_ ]?after[\s:=]+(\d+(?:\.\d+)?)", re.I),
    re.compile(r"retry (?:again )?(?:in|after)\s+(\d+(?:\.\d+)?)\s*(?:s|sec|secs|seconds)?", re.I),
    re.compile(r"try again in\s+(\d+(?:\.\d+)?)\s*(?:s|sec|secs|seconds)?", re.I),
    re.compile(r"resets? in\s+(\d+(?:\.\d+)?)\s*(?:s|sec|secs|seconds)?", re.I),
    re.compile(r"wait\s+(\d+(?:\.\d+)?)\s*(?:s|sec|secs|seconds)", re.I),
)


def is_rate_limit_error(exc: BaseException) -> bool:
    """Whether *exc* looks like a provider rate-limit rejection.

    Checks an explicit status code first, then falls back to scanning the
    exception type name and message for the usual 429 wording.
    """
    status = _status_code_of(exc)
    if status == 429:
        return True
    if status is not None and status != 429:
        return False
    haystack = f"{type(exc).__name__} {exc}".lower()
    return any(marker in haystack for marker in _RATE_LIMIT_MARKERS)


def _status_code_of(exc: BaseException) -> int | None:
    """Best-effort HTTP status code for *exc*, or ``None`` if it has none."""
    for attr in ("status_code", "status", "code", "http_status"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    response = getattr(exc, "response", None)
    if response is not None:
        value = getattr(response, "status_code", None)
        if isinstance(value, int):
            return value
    return None


def _headers_of(exc: BaseException) -> dict[str, str]:
    """Lowercased response headers carried by *exc*, if any."""
    for holder in (getattr(exc, "response", None), exc):
        headers = getattr(holder, "headers", None)
        if headers is None:
            continue
        try:
            items = headers.items()
        except AttributeError:
            continue
        return {str(key).lower(): str(value) for key, value in items}
    return {}


def retry_after_seconds(exc: BaseException, *, now: float | None = None) -> float | None:
    """Seconds the provider asked us to wait, or ``None`` if it did not say.

    Reads, in order of trust: a ``Retry-After`` header (delta-seconds or an
    HTTP date), an ``X-RateLimit-Reset`` header (delta-seconds or a Unix
    epoch), a ``retry_after`` attribute, then any "retry after N seconds"
    wording in the message.

    A non-positive or unparsable value yields ``None`` so the caller falls back
    to exponential backoff.
    """
    headers = _headers_of(exc)
    now = time.time() if now is None else now

    raw = headers.get("retry-after")
    if raw:
        seconds = _parse_delta_or_date(raw, now=now)
        if seconds is not None:
            return seconds

    for key in ("x-ratelimit-reset", "x-rate-limit-reset", "ratelimit-reset"):
        raw = headers.get(key)
        if not raw:
            continue
        try:
            value = float(raw)
        except ValueError:
            continue
        # Large values are absolute epoch timestamps, small ones are deltas.
        seconds = value - now if value > 1_000_000_000 else value
        if seconds > 0:
            return seconds

    attr = getattr(exc, "retry_after", None)
    if isinstance(attr, (int, float)) and attr > 0:
        return float(attr)

    message = str(exc)
    for pattern in _RETRY_AFTER_PATTERNS:
        match = pattern.search(message)
        if match:
            try:
                seconds = float(match.group(1))
            except ValueError:
                continue
            if seconds > 0:
                return seconds
    return None


def _parse_delta_or_date(raw: str, *, now: float) -> float | None:
    """Parse a ``Retry-After`` value as delta-seconds or an HTTP date."""
    text = raw.strip()
    try:
        seconds = float(text)
    except ValueError:
        try:
            when = email.utils.parsedate_to_datetime(text)
        except (TypeError, ValueError):
            return None
        if when is None:
            return None
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        seconds = when.timestamp() - now
    return seconds if seconds > 0 else None


class RateLimiter:
    """Enforces a minimum interval between calls, plus provider-ordered pauses.

    The first call is never delayed; later calls wait only for the remainder of
    the interval. :meth:`penalize` records a provider-requested cool-off that
    the next :meth:`wait` honours, which is how a 429's ``Retry-After`` slows
    the whole query loop rather than just the one failing request.

    *sleeper* and *clock* are injectable so tests can assert on the delays
    without spending wall-clock time.
    """

    def __init__(
        self,
        min_interval_seconds: float,
        *,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.min_interval = max(0.0, float(min_interval_seconds))
        self._sleep = sleeper
        self._clock = clock
        self._last_call: float | None = None
        self._penalty_until: float | None = None
        self.total_waited = 0.0
        self.waits = 0

    def wait(self) -> float:
        """Block until the next call is allowed. Returns the seconds slept."""
        now = self._clock()
        targets = []
        if self._last_call is not None and self.min_interval > 0:
            targets.append(self._last_call + self.min_interval)
        if self._penalty_until is not None:
            targets.append(self._penalty_until)

        delay = max([target - now for target in targets], default=0.0)
        if delay > 0:
            self._sleep(delay)
            self.total_waited += delay
            self.waits += 1
            now = self._clock() if self._clock is not time.monotonic else now + delay

        self._penalty_until = None
        self._last_call = now
        return max(delay, 0.0)

    def penalize(self, seconds: float) -> None:
        """Require an extra *seconds* pause before the next call."""
        if seconds <= 0:
            return
        until = self._clock() + seconds
        self._penalty_until = max(self._penalty_until or 0.0, until)


def call_with_rate_limit_retry(
    func: Callable[[], T],
    *,
    attempts: int,
    base_delay: float,
    max_sleep: float,
    label: str,
    limiter: RateLimiter | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    logger: logging.Logger | None = None,
) -> T:
    """Call *func* with throttling and rate-limit-aware retries.

    A rate-limit rejection waits for the provider's own ``Retry-After`` when it
    supplies one, and falls back to exponential backoff when it does not. Other
    errors always use exponential backoff. ``attempts`` is the total number of
    tries, so ``attempts=4`` means at most 3 retries; the final failure is
    re-raised for the caller to handle.
    """
    log = logger or get_logger()
    attempts = max(1, int(attempts))

    for attempt in range(1, attempts + 1):
        if limiter is not None:
            limiter.wait()
        try:
            return func()
        except Exception as exc:  # noqa: BLE001 - provider errors are varied
            rate_limited = is_rate_limit_error(exc)
            if attempt == attempts:
                if rate_limited:
                    log.error("%s: rate limited and out of retries (%d/%d): %s", redact_sensitive_text(label), attempt, attempts, redact_sensitive_text(exc))
                raise

            requested = retry_after_seconds(exc) if rate_limited else None
            if requested is not None:
                delay = min(requested, max_sleep)
                reason = f"provider asked for {requested:.1f}s"
            else:
                delay = min(base_delay * (2 ** (attempt - 1)), max_sleep)
                delay *= 1 + random.random() * 0.1
                delay = min(delay, max_sleep)
                reason = "rate limited, exponential backoff" if rate_limited else "error, exponential backoff"

            log.warning(
                "%s failed (attempt %d/%d): %s - %s, sleeping %.1fs",
                redact_sensitive_text(label), attempt, attempts, redact_sensitive_text(exc), reason, delay,
            )
            if rate_limited and limiter is not None:
                limiter.penalize(delay)
            sleeper(delay)

    raise AssertionError("unreachable")  # pragma: no cover


def first_present(mapping: Any, keys: Sequence[str]) -> Any:
    """Return the first non-empty value for *keys* in a dict or attribute object.

    Firecrawl metadata arrives either as a dict or as a typed object depending
    on SDK version and endpoint, so every metadata read goes through this.
    """
    if mapping is None:
        return None
    for key in keys:
        value = None
        if isinstance(mapping, dict):
            value = mapping.get(key)
        else:
            value = getattr(mapping, key, None)
        if value not in (None, "", [], {}):
            return value
    return None


def dedupe_preserving_order(items: Iterable[T]) -> Iterator[T]:
    """Yield *items* once each, preserving first-seen order."""
    seen: set[T] = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        yield item
