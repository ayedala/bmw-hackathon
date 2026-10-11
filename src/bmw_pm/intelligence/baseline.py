"""Offline keyword extraction fallback; its output must never be presented as AI inference."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..contracts import (
    EvidenceSpan,
    FeedbackRecord,
    Polarity,
    ProviderDescriptor,
    Signal,
)
from ..utils import content_hash, stable_id
from .provider import ExtractionProvider


_POSITIVE = re.compile(r"\b(love|great|excellent|comfortable|quiet|easy|like|pleased|good)\b", re.I)
_NEGATIVE = re.compile(
    r"\b(hate|difficult|hard|poor|problem|issue|bug|annoy|missing|lack|slow|fail|uncomfortable|noisy|worse|not|never)\w*\b",
    re.I,
)
_ASPIRATION = re.compile(r"\b(wish|should|would like|want|needs? to|hope)\b", re.I)


class BaselineExtractionProvider(ExtractionProvider):
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    @classmethod
    def from_file(cls, path: str | Path) -> "BaselineExtractionProvider":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    @property
    def descriptor(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            name="keyword_taxonomy_baseline",
            mode="baseline_no_ai",
            model_id=None,
            prompt_version=str(self.config["version"]),
            label=str(self.config["label"]),
        )

    @property
    def configuration_hash(self) -> str:
        return content_hash(self.config)

    @staticmethod
    def _sentence_span(text: str, start: int, end: int) -> tuple[int, int]:
        left = max(text.rfind(".", 0, start), text.rfind("!", 0, start), text.rfind("?", 0, start))
        left = 0 if left < 0 else left + 1
        candidates = [position for mark in ".!?" if (position := text.find(mark, end)) >= 0]
        right = min(candidates) + 1 if candidates else len(text)
        while left < right and text[left].isspace():
            left += 1
        while right > left and text[right - 1].isspace():
            right -= 1
        return left, right

    @staticmethod
    def _polarity(sentence: str) -> Polarity:
        positive = bool(_POSITIVE.search(sentence))
        negative = bool(_NEGATIVE.search(sentence))
        aspiration = bool(_ASPIRATION.search(sentence))
        if positive and negative:
            return Polarity.MIXED
        if negative:
            return Polarity.COMPLAINT
        if aspiration:
            return Polarity.ASPIRATION
        if positive:
            return Polarity.PRAISE
        return Polarity.OBSERVATION

    def extract(self, records: list[FeedbackRecord], *, run_id: str) -> list[Signal]:
        signals: list[Signal] = []
        for record in records:
            text = record.redacted_text
            for domain, definition in self.config["domains"].items():
                applicable = definition.get("applicable_powertrains")
                if applicable and record.powertrain not in applicable and record.powertrain != "BEVE":
                    continue
                matches = []
                for phrase in sorted(definition["phrases"], key=len, reverse=True):
                    match = re.search(re.escape(phrase), text, flags=re.IGNORECASE)
                    if match:
                        matches.append(match)
                if not matches:
                    continue
                match = min(matches, key=lambda item: item.start())
                start, end = self._sentence_span(text, match.start(), match.end())
                evidence_text = text[start:end]
                polarity = self._polarity(evidence_text)
                atomic_claim = evidence_text
                locator = record.row_locators[0].model_copy(
                    update={"exact_quote": evidence_text}
                )
                signal_id = stable_id(
                    "signal",
                    str(self.config["version"]),
                    record.record_id,
                    domain,
                    evidence_text.casefold(),
                )
                signals.append(
                    Signal(
                        signal_id=signal_id,
                        feedback_record_id=record.record_id,
                        need_domain=domain,
                        atomic_claim=atomic_claim,
                        customer_outcome=str(definition["customer_outcome"]),
                        polarity=polarity,
                        use_context=None,
                        vehicle_scope={
                            "model": record.model_code,
                            "country": record.country,
                            "powertrain": record.powertrain,
                        },
                        evidence_spans=[
                            EvidenceSpan(
                                record_id=record.record_id,
                                locator=locator,
                                text=evidence_text,
                                start=start,
                                end=end,
                            )
                        ],
                        run_id=run_id,
                        provider_mode="baseline_no_ai",
                    )
                )
        return signals
