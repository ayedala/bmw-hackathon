"""Runtime configuration, paths and target research context.

All state produced by this pipeline lives under ``BASE_DIR`` (this folder). No
path here ever points outside it, which is what keeps the addition isolated
from the rest of the repository.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from utils import load_env_file

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
VISITED_URLS_PATH: Final[Path] = METADATA_DIR / "visited_urls.json"
RESEARCH_RUNS_PATH: Final[Path] = METADATA_DIR / "research_runs.jsonl"
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
DEFAULT_MAX_CONTENT_CHARS: Final[int] = 15_000
DEFAULT_CHUNK_OVERLAP_CHARS: Final[int] = 400

#: Minimum trimmed markdown length worth sending to the extraction model.
MIN_PAGE_CHARS: Final[int] = 400

#: rapidfuzz ``token_set_ratio`` at or above which two same-origin claims are
#: treated as the same claim. Cross-origin claims are never deduplicated.
DUPLICATE_SIMILARITY_THRESHOLD: Final[float] = 92.0

#: Seconds to leave between consecutive Firecrawl requests. The free tier is
#: limited per minute, and the project values completing a run over finishing
#: it quickly, so this defaults to a deliberately conservative pause.
DEFAULT_SEARCH_DELAY_SECONDS: Final[float] = 2.0

#: Total attempts per Firecrawl request, so 4 means up to 3 retries.
DEFAULT_FIRECRAWL_MAX_RETRIES: Final[int] = 4

#: Upper bound on any single backoff or provider-requested pause, seconds.
#: Protects the run from an implausible ``Retry-After``.
MAX_RATE_LIMIT_SLEEP_SECONDS: Final[float] = 120.0

#: Firecrawl scrape request timeout, milliseconds.
SCRAPE_TIMEOUT_MS: Final[int] = 60_000
#: Firecrawl search request timeout, milliseconds.
SEARCH_TIMEOUT_MS: Final[int] = 60_000
#: Firecrawl server-side cache window, milliseconds (2 days). Note that a
#: Firecrawl cache hit still costs 1 credit - the local cache in
#: ``data/cache/`` is what actually avoids spend.
SCRAPE_MAX_AGE_MS: Final[int] = 172_800_000

#: Output token ceiling for one extraction request.
LLM_MAX_OUTPUT_TOKENS: Final[int] = 8_000

DEFAULT_OPENAI_MODEL: Final[str] = "gpt-5-mini"
#: Claude model used when ``ANTHROPIC_MODEL`` is unset.
DEFAULT_ANTHROPIC_MODEL: Final[str] = "claude-opus-5"


class ConfigError(RuntimeError):
    """Raised when required configuration or credentials are missing."""


@dataclass(frozen=True)
class Settings:
    """Resolved runtime settings for one pipeline execution."""

    firecrawl_api_key: str | None
    llm_provider: str
    openai_api_key: str | None
    openai_model: str
    anthropic_api_key: str | None
    anthropic_model: str
    search_limit: int
    max_pages_per_run: int
    max_content_chars: int
    search_delay_seconds: float = DEFAULT_SEARCH_DELAY_SECONDS
    firecrawl_max_retries: int = DEFAULT_FIRECRAWL_MAX_RETRIES
    max_rate_limit_sleep: float = MAX_RATE_LIMIT_SLEEP_SECONDS
    chunk_overlap_chars: int = DEFAULT_CHUNK_OVERLAP_CHARS
    duplicate_threshold: float = DUPLICATE_SIMILARITY_THRESHOLD

    # -- credential guards ------------------------------------------------- #

    def require_firecrawl_key(self) -> str:
        """Return the Firecrawl key or raise a :class:`ConfigError` naming the fix."""
        if not self.firecrawl_api_key:
            raise ConfigError(
                "FIRECRAWL_API_KEY is not set. Copy .env.example to .env inside "
                "src/bmw_pm/data_pipeline/web_research/ and add your Firecrawl key "
                "(https://www.firecrawl.dev/app/api-keys)."
            )
        return self.firecrawl_api_key

    def require_llm_credentials(self) -> tuple[str, str, str]:
        """Validate LLM configuration and return ``(provider, model, api_key)``.

        Only the selected provider's key is required - configuring one provider
        never obliges you to supply credentials for the other.
        """
        provider = self.llm_provider
        if provider == "openai":
            if not self.openai_api_key:
                raise ConfigError(
                    "LLM_PROVIDER=openai but OPENAI_API_KEY is not set. "
                    "Set OPENAI_API_KEY in src/bmw_pm/data_pipeline/web_research/.env, or "
                    "switch to LLM_PROVIDER=anthropic."
                )
            return provider, self.openai_model, self.openai_api_key
        if provider == "anthropic":
            if not self.anthropic_api_key:
                raise ConfigError(
                    "LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set. "
                    "Set ANTHROPIC_API_KEY in src/bmw_pm/data_pipeline/web_research/.env, or "
                    "switch to LLM_PROVIDER=openai."
                )
            return provider, self.anthropic_model, self.anthropic_api_key
        raise ConfigError(
            f"LLM_PROVIDER={provider!r} is not supported. Use 'openai' or 'anthropic'."
        )


def _env_int(name: str, default: int) -> int:
    """Read a positive integer from the environment, falling back to *default*."""
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


def _env_float(name: str, default: float, *, minimum: float = 0.0) -> float:
    """Read a non-negative float from the environment, falling back to *default*."""
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


def ensure_directories() -> None:
    """Create the data directories this pipeline writes to."""
    for directory in (RAW_DIR, PROCESSED_DIR, METADATA_DIR, CACHE_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def load_settings(
    *,
    search_limit: int | None = None,
    max_pages: int | None = None,
    max_content_chars: int | None = None,
    search_delay: float | None = None,
    max_retries: int | None = None,
) -> Settings:
    """Build :class:`Settings` from ``.env``, the environment and CLI overrides.

    Precedence is CLI argument > environment variable > built-in default.
    Credentials are not validated here; call the ``require_*`` methods at the
    point of use so that ``--dry-run`` never demands an LLM key it will not use.
    """
    load_env_file(ENV_PATH)

    provider = (_env_str("LLM_PROVIDER", "openai") or "openai").lower()

    return Settings(
        firecrawl_api_key=_env_str("FIRECRAWL_API_KEY"),
        llm_provider=provider,
        openai_api_key=_env_str("OPENAI_API_KEY"),
        openai_model=_env_str("OPENAI_MODEL", DEFAULT_OPENAI_MODEL) or DEFAULT_OPENAI_MODEL,
        anthropic_api_key=_env_str("ANTHROPIC_API_KEY"),
        anthropic_model=_env_str("ANTHROPIC_MODEL", DEFAULT_ANTHROPIC_MODEL) or DEFAULT_ANTHROPIC_MODEL,
        search_limit=search_limit or _env_int("SEARCH_LIMIT", DEFAULT_SEARCH_LIMIT),
        max_pages_per_run=max_pages or _env_int("MAX_PAGES_PER_RUN", DEFAULT_MAX_PAGES_PER_RUN),
        max_content_chars=max_content_chars or _env_int("MAX_CONTENT_CHARS", DEFAULT_MAX_CONTENT_CHARS),
        search_delay_seconds=(
            search_delay
            if search_delay is not None
            else _env_float("FIRECRAWL_SEARCH_DELAY_SECONDS", DEFAULT_SEARCH_DELAY_SECONDS)
        ),
        firecrawl_max_retries=max_retries or _env_int("FIRECRAWL_MAX_RETRIES", DEFAULT_FIRECRAWL_MAX_RETRIES),
    )
