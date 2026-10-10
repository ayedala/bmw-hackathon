"""LLM provider abstraction for evidence extraction.

The extractor depends only on :class:`BaseLLMProvider`, so no provider-specific
import, parameter name or response shape leaks into the rest of the pipeline.
Exactly one provider is required at runtime - configuring OpenAI never obliges
you to hold an Anthropic key, or the reverse.

Both implementations request schema-constrained JSON and return the raw JSON
text; parsing and validation happen in :mod:`extractor`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import config
from config import ConfigError, Settings
from utils import get_logger, redact_sensitive_text, with_retries


class LLMError(RuntimeError):
    """Raised when a provider call fails or returns no usable content."""


class BaseLLMProvider(ABC):
    """Interface every extraction backend implements."""

    #: Short provider identifier, used in logs.
    name: str = "base"

    def __init__(self, *, model: str, api_key: str) -> None:
        self.model = model
        self._api_key = api_key
        self.call_count = 0
        self._log = get_logger()
        self._client: Any | None = None

    @abstractmethod
    def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
        schema_name: str = "extraction",
        max_output_tokens: int = config.LLM_MAX_OUTPUT_TOKENS,
    ) -> str:
        """Return raw JSON text conforming to *schema*.

        Raises:
            LLMError: on API failure, refusal or an empty response.
        """

    def describe(self) -> str:
        """Provider and model, for the startup log line."""
        return f"{self.name}:{self.model}"


# --------------------------------------------------------------------------- #
# OpenAI
# --------------------------------------------------------------------------- #


class OpenAIProvider(BaseLLMProvider):
    """OpenAI Chat Completions backend using structured JSON output.

    Newer model families (``gpt-5*``, ``o1``/``o3``/``o4``) take
    ``max_completion_tokens`` and reject ``temperature``, while older ones take
    ``max_tokens``. Parameters are chosen per model family and any remaining
    rejection is retried once with the offending parameter removed.
    """

    name = "openai"

    #: Model name prefixes that use the reasoning-model parameter set.
    _REASONING_PREFIXES: tuple[str, ...] = ("gpt-5", "o1", "o3", "o4")

    @property
    def client(self) -> Any:
        """Lazily construct the OpenAI client."""
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:  # pragma: no cover - environment dependent
                raise LLMError(
                    "The 'openai' package is not installed. Run "
                    "`pip install -r requirements.txt` inside external_research_pipeline/."
                ) from exc
            self._client = OpenAI(api_key=self._api_key)
        return self._client

    def _is_reasoning_model(self) -> bool:
        """Whether the configured model uses the reasoning parameter set."""
        return self.model.startswith(self._REASONING_PREFIXES)

    def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
        schema_name: str = "extraction",
        max_output_tokens: int = config.LLM_MAX_OUTPUT_TOKENS,
    ) -> str:
        params: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "schema": schema, "strict": True},
            },
        }
        if self._is_reasoning_model():
            params["max_completion_tokens"] = max_output_tokens
        else:
            params["max_tokens"] = max_output_tokens
            params["temperature"] = 0

        return self._invoke(params)

    @with_retries(attempts=3, initial_wait=2.0, max_wait=20.0, exceptions=(LLMError,))
    def _invoke(self, params: dict[str, Any]) -> str:
        """Call the API, downgrading unsupported parameters once if rejected."""
        self.call_count += 1
        try:
            response = self.client.chat.completions.create(**params)
        except Exception as exc:  # noqa: BLE001 - SDK raises several error types
            downgraded = self._downgrade(params, exc)
            if downgraded is None:
                raise LLMError(f"OpenAI request failed: {redact_sensitive_text(exc)}") from exc
            self._log.warning("retrying OpenAI request without unsupported parameter: %s", redact_sensitive_text(exc))
            try:
                response = self.client.chat.completions.create(**downgraded)
            except Exception as retry_exc:  # noqa: BLE001
                raise LLMError(f"OpenAI request failed: {redact_sensitive_text(retry_exc)}") from retry_exc
            params.clear()
            params.update(downgraded)

        choices = getattr(response, "choices", None) or []
        if not choices:
            raise LLMError("OpenAI returned no choices")
        message = choices[0].message
        if getattr(message, "refusal", None):
            raise LLMError(f"OpenAI refused the request: {message.refusal}")
        content = (getattr(message, "content", None) or "").strip()
        if not content:
            finish = getattr(choices[0], "finish_reason", "unknown")
            raise LLMError(f"OpenAI returned empty content (finish_reason={finish})")
        return content

    @staticmethod
    def _downgrade(params: dict[str, Any], exc: Exception) -> dict[str, Any] | None:
        """Return *params* minus a parameter the API complained about, or ``None``.

        Covers the two common mismatches: a reasoning model rejecting
        ``temperature`` or ``max_tokens``, and an older model or gateway that
        does not support ``json_schema`` response formats.
        """
        message = str(exc).lower()
        candidate = dict(params)

        if "temperature" in message and "temperature" in candidate:
            candidate.pop("temperature")
            return candidate
        if "max_tokens" in message and "max_tokens" in candidate:
            candidate["max_completion_tokens"] = candidate.pop("max_tokens")
            candidate.pop("temperature", None)
            return candidate
        if ("response_format" in message or "json_schema" in message) and "response_format" in candidate:
            candidate["response_format"] = {"type": "json_object"}
            return candidate
        return None


# --------------------------------------------------------------------------- #
# Anthropic
# --------------------------------------------------------------------------- #


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Messages API backend using structured JSON output.

    Uses ``output_config.format`` with a JSON schema, which guarantees the first
    content block is valid JSON. If the installed SDK predates that parameter,
    the call is retried without it and the prompt's own JSON instruction plus
    the extractor's tolerant parser carry the result.

    ``stop_reason == "refusal"`` arrives as HTTP 200, so it is checked
    explicitly rather than surfacing as a confusing empty response.
    """

    name = "anthropic"

    @property
    def client(self) -> Any:
        """Lazily construct the Anthropic client."""
        if self._client is None:
            try:
                import anthropic
            except ImportError as exc:  # pragma: no cover - environment dependent
                raise LLMError(
                    "The 'anthropic' package is not installed. Run "
                    "`pip install -r requirements.txt` inside external_research_pipeline/."
                ) from exc
            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
        schema_name: str = "extraction",
        max_output_tokens: int = config.LLM_MAX_OUTPUT_TOKENS,
    ) -> str:
        params: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_output_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "output_config": {"format": {"type": "json_schema", "schema": schema}},
        }
        return self._invoke(params)

    @with_retries(attempts=3, initial_wait=2.0, max_wait=20.0, exceptions=(LLMError,))
    def _invoke(self, params: dict[str, Any]) -> str:
        """Call the Messages API, dropping ``output_config`` if unsupported."""
        self.call_count += 1
        try:
            response = self.client.messages.create(**params)
        except Exception as exc:  # noqa: BLE001 - SDK raises several error types
            if "output_config" in str(exc).lower() and "output_config" in params:
                self._log.warning(
                    "installed anthropic SDK rejected output_config (%s); "
                    "falling back to prompt-instructed JSON",
                    redact_sensitive_text(exc),
                )
                params.pop("output_config")
                try:
                    response = self.client.messages.create(**params)
                except Exception as retry_exc:  # noqa: BLE001
                    raise LLMError(f"Anthropic request failed: {redact_sensitive_text(retry_exc)}") from retry_exc
            else:
                raise LLMError(f"Anthropic request failed: {redact_sensitive_text(exc)}") from exc

        stop_reason = getattr(response, "stop_reason", None)
        if stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            category = getattr(details, "category", None) if details else None
            raise LLMError(f"Anthropic declined this page (refusal category={category})")

        text = self._first_text_block(response)
        if not text:
            raise LLMError(f"Anthropic returned no text content (stop_reason={stop_reason})")
        return text

    @staticmethod
    def _first_text_block(response: Any) -> str:
        """Concatenate the text blocks of a Messages response."""
        blocks = getattr(response, "content", None) or []
        parts: list[str] = []
        for block in blocks:
            if getattr(block, "type", None) == "text":
                parts.append(getattr(block, "text", "") or "")
        return "".join(parts).strip()


# --------------------------------------------------------------------------- #
# Factory
# --------------------------------------------------------------------------- #

PROVIDERS: dict[str, type[BaseLLMProvider]] = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
}


def get_provider(settings: Settings) -> BaseLLMProvider:
    """Build the configured provider, validating only its own credentials.

    Raises:
        ConfigError: if ``LLM_PROVIDER`` is unknown or its API key is missing.
    """
    provider_name, model, api_key = settings.require_llm_credentials()
    provider_cls = PROVIDERS.get(provider_name)
    if provider_cls is None:  # pragma: no cover - guarded by require_llm_credentials
        raise ConfigError(f"unsupported LLM_PROVIDER {provider_name!r}")
    provider = provider_cls(model=model, api_key=api_key)
    get_logger().info("LLM provider: %s", provider.describe())
    return provider
