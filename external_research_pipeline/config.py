"""Runtime configuration, paths and target research context.

All state produced by this pipeline lives under ``BASE_DIR`` (this folder). No
path here ever points outside it, which is what keeps the addition isolated
from the rest of the repository.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from utils import LOGGER_NAME, load_env_file

# --------------------------------------------------------------------------- #
# Paths - everything is relative to this folder
# --------------------------------------------------------------------------- #

BASE_DIR: Final[Path] = Path(__file__).resolve().parent
DATA_DIR: Final[Path] = BASE_DIR / "data"
RAW_DIR: Final[Path] = DATA_DIR / "raw"
PROCESSED_DIR: Final[Path] = DATA_DIR / "processed"
METADATA_DIR: Final[Path] = DATA_DIR / "metadata"
CACHE_DIR: Final[Path] = DATA_DIR / "cache"

RAW_PAGES_PATH: Final[Path] = RAW_DIR / "raw_pages.jsonl"
PROCESSED_EVIDENCE_PATH: Final[Path] = PROCESSED_DIR / "external_evidence.jsonl"

#: Output of ``--reprocess-cache``. Kept separate from the main store so a
#: reprocess run can never disturb evidence collected by a real scrape.
CACHE_REPROCESS_EVIDENCE_PATH: Final[Path] = (
    PROCESSED_DIR / "cache_reprocess_evidence.jsonl"
)

VISITED_URLS_PATH: Final[Path] = METADATA_DIR / "visited_urls.json"
RESEARCH_RUNS_PATH: Final[Path] = METADATA_DIR / "research_runs.jsonl"

#: In-progress run counters, rewritten atomically after every page. Lets an
#: interrupted run be diagnosed, and proves how far it got.
RUN_CHECKPOINT_PATH: Final[Path] = METADATA_DIR / "run_checkpoint.json"

LOG_PATH: Final[Path] = BASE_DIR / "pipeline.log"
ENV_PATH: Final[Path] = BASE_DIR / ".env"

# --------------------------------------------------------------------------- #
# Research target - fixed context handed to the extraction model
# --------------------------------------------------------------------------- #

TARGET_BRAND: Final[str] = "BMW"
TARGET_VEHICLE: Final[str] = "BMW 5 Series / BMW i5"
TARGET_GENERATION: Final[str] = "G60"
PRIMARY_MARKET: Final[str] = "DE"
PRIMARY_MARKET_NAME: Final[str] = "Germany"
TIME_HORIZON: Final[str] = "3-5 years ahead"
SEARCH_LOCATION: Final[str] = "Germany"

# --------------------------------------------------------------------------- #
# Credit-saving and request-shaping defaults
# --------------------------------------------------------------------------- #

DEFAULT_SEARCH_LIMIT: Final[int] = 5
DEFAULT_MAX_PAGES_PER_RUN: Final[int] = 20

#: Characters of page text per extraction request. Kept well below the model's
#: output ceiling: a chunk that is too large makes the model emit more records
#: than fit in one response, which truncates the JSON and loses the whole chunk.
DEFAULT_EXTRACTION_CHUNK_CHARS: Final[int] = 7_000

#: Characters shared between consecutive chunks, so a claim spanning a boundary
#: is visible in full to at least one request.
DEFAULT_EXTRACTION_CHUNK_OVERLAP_CHARS: Final[int] = 600

#: Ceiling applied to a chunk size inherited from the deprecated
#: ``MAX_CONTENT_CHARS`` variable. That name defaulted to 15000 under the old
#: semantics, and a leftover line in an existing .env would otherwise silently
#: restore the oversized chunking that truncates the model's response.
MAX_SAFE_LEGACY_CHUNK_CHARS: Final[int] = 10_000

#: Minimum trimmed page length worth an extraction request. Below this a page
#: is almost always a cookie wall, a JS shell or an error page.
DEFAULT_MIN_CONTENT_CHARS: Final[int] = 1_000

#: Topic-vocabulary hits a page needs to clear the post-scrape relevance gate.
DEFAULT_MIN_TOPIC_HITS: Final[int] = 3

#: Vehicle-vocabulary hits that alone clear the gate, for a page clearly about
#: the target car even when its topic wording is unusual.
DEFAULT_MIN_VEHICLE_HITS: Final[int] = 2

#: rapidfuzz ``token_set_ratio`` at or above which two same-origin claims are
#: treated as the same claim. Cross-origin claims are never deduplicated.
DUPLICATE_SIMILARITY_THRESHOLD: Final[float] = 92.0

#: Threshold for two claims from the *same page*. Lower than the cross-source
#: figure on purpose: same page plus same subtopic is a much stronger prior
#: that two wordings describe one observation.
SAME_PAGE_DUPLICATE_THRESHOLD: Final[float] = 88.0

#: Fraction of the shorter evidence span that must overlap before two same-page
#: records are considered to quote the same proposition.
SPAN_OVERLAP_RATIO: Final[float] = 0.6

#: Seconds to leave between consecutive Firecrawl requests.
DEFAULT_SEARCH_DELAY_SECONDS: Final[float] = 2.0

#: Total attempts per Firecrawl request, so 4 means up to 3 retries.
DEFAULT_FIRECRAWL_MAX_RETRIES: Final[int] = 4

#: Upper bound on any single backoff or provider-requested pause, seconds.
MAX_RATE_LIMIT_SLEEP_SECONDS: Final[float] = 120.0

#: Firecrawl scrape request timeout, milliseconds.
SCRAPE_TIMEOUT_MS: Final[int] = 60_000

#: Firecrawl search request timeout, milliseconds.
SEARCH_TIMEOUT_MS: Final[int] = 60_000

#: Firecrawl server-side cache window, milliseconds (2 days).
SCRAPE_MAX_AGE_MS: Final[int] = 172_800_000

#: Output token ceiling for one extraction request. On a reasoning model this
#: budget covers reasoning and output.
LLM_MAX_OUTPUT_TOKENS: Final[int] = 16_000

# --------------------------------------------------------------------------- #
# LLM defaults
# --------------------------------------------------------------------------- #

DEFAULT_OPENAI_MODEL: Final[str] = "gpt-5-mini"

#: Per-request OpenAI timeout in seconds.
DEFAULT_OPENAI_TIMEOUT_SECONDS: Final[float] = 180.0

#: SDK retry count. 1 means one retry after the first failed attempt.
DEFAULT_OPENAI_MAX_RETRIES: Final[int] = 1

#: Claude model used when ``ANTHROPIC_MODEL`` is unset.
DEFAULT_ANTHROPIC_MODEL: Final[str] = "claude-opus-5"


class ConfigError(RuntimeError):
    """Raised when required configuration or credentials are missing."""


@dataclass(frozen=True)
class Settings:
    """Resolved runtime settings for one pipeline execution."""

    # Required / non-default fields first.
    firecrawl_api_key: str | None
    llm_provider: str
    openai_api_key: str | None
    openai_model: str
    anthropic_api_key: str | None
    anthropic_model: str
    search_limit: int
    max_pages_per_run: int
    extraction_chunk_chars: int

    # Fields with defaults must come afterwards in a dataclass.
    openai_timeout_seconds: float = DEFAULT_OPENAI_TIMEOUT_SECONDS
    openai_max_retries: int = DEFAULT_OPENAI_MAX_RETRIES

    extraction_chunk_overlap_chars: int = DEFAULT_EXTRACTION_CHUNK_OVERLAP_CHARS
    min_content_chars: int = DEFAULT_MIN_CONTENT_CHARS
    min_topic_hits: int = DEFAULT_MIN_TOPIC_HITS
    min_vehicle_hits: int = DEFAULT_MIN_VEHICLE_HITS
    search_delay_seconds: float = DEFAULT_SEARCH_DELAY_SECONDS
    firecrawl_max_retries: int = DEFAULT_FIRECRAWL_MAX_RETRIES
    max_rate_limit_sleep: float = MAX_RATE_LIMIT_SLEEP_SECONDS
    duplicate_threshold: float = DUPLICATE_SIMILARITY_THRESHOLD
    same_page_duplicate_threshold: float = SAME_PAGE_DUPLICATE_THRESHOLD
    span_overlap_ratio: float = SPAN_OVERLAP_RATIO

    # -- credential guards ------------------------------------------------- #

    def require_firecrawl_key(self) -> str:
        """Return the Firecrawl key or raise ConfigError naming the fix."""
        if not self.firecrawl_api_key:
            raise ConfigError(
                "FIRECRAWL_API_KEY is not set. Copy .env.example to .env inside "
                "external_research_pipeline/ and add your Firecrawl key "
                "(https://www.firecrawl.dev/app/api-keys)."
            )
        return self.firecrawl_api_key

    def require_llm_credentials(self) -> tuple[str, str, str]:
        """Validate LLM configuration and return (provider, model, api_key)."""

        provider = self.llm_provider

        if provider == "openai":
            if not self.openai_api_key:
                raise ConfigError(
                    "LLM_PROVIDER=openai but OPENAI_API_KEY is not set. "
                    "Set OPENAI_API_KEY in external_research_pipeline/.env, or "
                    "switch to LLM_PROVIDER=anthropic."
                )
            return provider, self.openai_model, self.openai_api_key

        if provider == "anthropic":
            if not self.anthropic_api_key:
                raise ConfigError(
                    "LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set. "
                    "Set ANTHROPIC_API_KEY in external_research_pipeline/.env, or "
                    "switch to LLM_PROVIDER=openai."
                )
            return provider, self.anthropic_model, self.anthropic_api_key

        raise ConfigError(
            f"LLM_PROVIDER={provider!r} is not supported. "
            "Use 'openai' or 'anthropic'."
        )


def _env_int(name: str, default: int) -> int:
    """Read a positive integer from the environment, falling back to default."""
    raw = os.environ.get(name, "").strip()

    if not raw:
        return default

    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc

    if value <= 0:
        raise ConfigError(f"{name} must be greater than zero, got {value}")

    return value


def _env_float(
    name: str,
    default: float,
    *,
    minimum: float = 0.0,
) -> float:
    """Read a float from the environment, falling back to default."""
    raw = os.environ.get(name, "").strip()

    if not raw:
        return default

    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number, got {raw!r}") from exc

    if value < minimum:
        raise ConfigError(f"{name} must be at least {minimum}, got {value}")

    return value


def _env_str(name: str, default: str | None = None) -> str | None:
    """Read a stripped string from the environment, treating blanks as unset."""
    value = os.environ.get(name, "").strip()
    return value or default


def _resolve_chunk_chars() -> int:
    """Resolve the extraction chunk size from the environment.

    EXTRACTION_CHUNK_CHARS wins outright.

    MAX_CONTENT_CHARS is the deprecated name and is still read, but oversized
    legacy values are clamped back to the safe default.
    """

    explicit = os.environ.get("EXTRACTION_CHUNK_CHARS", "").strip()

    if explicit:
        return _env_int(
            "EXTRACTION_CHUNK_CHARS",
            DEFAULT_EXTRACTION_CHUNK_CHARS,
        )

    legacy_raw = os.environ.get("MAX_CONTENT_CHARS", "").strip()

    if not legacy_raw:
        return DEFAULT_EXTRACTION_CHUNK_CHARS

    legacy = _env_int(
        "MAX_CONTENT_CHARS",
        DEFAULT_EXTRACTION_CHUNK_CHARS,
    )

    log = logging.getLogger(LOGGER_NAME)

    if legacy > MAX_SAFE_LEGACY_CHUNK_CHARS:
        log.warning(
            "MAX_CONTENT_CHARS=%d is the deprecated name for "
            "EXTRACTION_CHUNK_CHARS and is too large: chunks that big overflow "
            "the model's output budget and lose the whole chunk. Using %d "
            "instead. Remove MAX_CONTENT_CHARS from your .env, or set "
            "EXTRACTION_CHUNK_CHARS explicitly if you really want %d.",
            legacy,
            DEFAULT_EXTRACTION_CHUNK_CHARS,
            legacy,
        )
        return DEFAULT_EXTRACTION_CHUNK_CHARS

    log.warning(
        "MAX_CONTENT_CHARS is deprecated; rename it to "
        "EXTRACTION_CHUNK_CHARS (using %d)",
        legacy,
    )

    return legacy


def ensure_directories() -> None:
    """Create the data directories this pipeline writes to."""
    for directory in (
        RAW_DIR,
        PROCESSED_DIR,
        METADATA_DIR,
        CACHE_DIR,
    ):
        directory.mkdir(parents=True, exist_ok=True)


def load_settings(
    *,
    search_limit: int | None = None,
    max_pages: int | None = None,
    chunk_chars: int | None = None,
    search_delay: float | None = None,
    max_retries: int | None = None,
) -> Settings:
    """Build Settings from .env, environment variables and CLI overrides.

    Precedence is CLI argument > environment variable > built-in default.

    Credentials are not validated here; call the require_* methods at the
    point of use so that --dry-run never demands an LLM key it will not use.
    """

    load_env_file(ENV_PATH)

    provider = (
        _env_str("LLM_PROVIDER", "openai") or "openai"
    ).lower()

    return Settings(
        firecrawl_api_key=_env_str("FIRECRAWL_API_KEY"),
        llm_provider=provider,

        openai_api_key=_env_str("OPENAI_API_KEY"),
        openai_model=(
            _env_str("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
            or DEFAULT_OPENAI_MODEL
        ),
        openai_timeout_seconds=_env_float(
            "OPENAI_TIMEOUT_SECONDS",
            DEFAULT_OPENAI_TIMEOUT_SECONDS,
        ),
        openai_max_retries=_env_int(
            "OPENAI_MAX_RETRIES",
            DEFAULT_OPENAI_MAX_RETRIES,
        ),

        anthropic_api_key=_env_str("ANTHROPIC_API_KEY"),
        anthropic_model=(
            _env_str(
                "ANTHROPIC_MODEL",
                DEFAULT_ANTHROPIC_MODEL,
            )
            or DEFAULT_ANTHROPIC_MODEL
        ),

        search_limit=(
            search_limit
            or _env_int(
                "SEARCH_LIMIT",
                DEFAULT_SEARCH_LIMIT,
            )
        ),

        max_pages_per_run=(
            max_pages
            or _env_int(
                "MAX_PAGES_PER_RUN",
                DEFAULT_MAX_PAGES_PER_RUN,
            )
        ),

        extraction_chunk_chars=(
            chunk_chars
            or _resolve_chunk_chars()
        ),

        extraction_chunk_overlap_chars=_env_int(
            "EXTRACTION_CHUNK_OVERLAP_CHARS",
            DEFAULT_EXTRACTION_CHUNK_OVERLAP_CHARS,
        ),

        min_content_chars=_env_int(
            "MIN_CONTENT_CHARS",
            DEFAULT_MIN_CONTENT_CHARS,
        ),

        min_topic_hits=_env_int(
            "MIN_TOPIC_HITS",
            DEFAULT_MIN_TOPIC_HITS,
        ),

        min_vehicle_hits=_env_int(
            "MIN_VEHICLE_HITS",
            DEFAULT_MIN_VEHICLE_HITS,
        ),

        search_delay_seconds=(
            search_delay
            if search_delay is not None
            else _env_float(
                "FIRECRAWL_SEARCH_DELAY_SECONDS",
                DEFAULT_SEARCH_DELAY_SECONDS,
            )
        ),

        firecrawl_max_retries=(
            max_retries
            or _env_int(
                "FIRECRAWL_MAX_RETRIES",
                DEFAULT_FIRECRAWL_MAX_RETRIES,
            )
        ),
    )