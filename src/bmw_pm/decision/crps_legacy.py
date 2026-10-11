"""CRPS v2: deterministic, provenance-aware implementation of the supplied framework.

Unmeasured inputs retain their full weight as an interval. The result is a
priority *assessment*, not a probability, demand forecast, or release decision.
"""
from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from ..contracts import Contract


POLICY_VERSION = "crps-framework-v1"
WEIGHTS = {
    "customer_impact": .25, "evidence_strength": .20, "frequency": .15,
    "market_relevance": .15, "competitive_gap": .10,
    "future_relevance": .10, "strategic_fit": .05,
}
EVIDENCE_WEIGHTS = {
    "source_quality": .30, "source_diversity": .25, "consistency": .20,
    "volume": .15, "recency": .10,
}


class RatedInput(Contract):
    value: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    basis: Literal["missing", "source_review", "reviewer_judgment"] = "missing"
    explanation: str = ""
    evidence_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def supported_rating(self):
        if self.value is None:
            if self.basis != "missing" or self.explanation or self.evidence_ids:
                raise ValueError("An unknown rating cannot claim a source or explanation")
        elif (self.basis == "missing" or not self.explanation.strip() or
              (self.basis == "source_review" and not self.evidence_ids)):
            raise ValueError("A rated input needs a basis, explanation and source IDs when source-reviewed")
        return self


class EvidenceInputs(Contract):
    source_quality: RatedInput = Field(default_factory=RatedInput)
    source_diversity: RatedInput = Field(default_factory=RatedInput)
    consistency: RatedInput = Field(default_factory=RatedInput)
    volume: RatedInput = Field(default_factory=RatedInput)
    recency: RatedInput = Field(default_factory=RatedInput)


class CrpsInputs(Contract):
    customer_impact: RatedInput = Field(default_factory=RatedInput)
    evidence: EvidenceInputs = Field(default_factory=EvidenceInputs)
    frequency: RatedInput = Field(default_factory=RatedInput)
    market_relevance: RatedInput = Field(default_factory=RatedInput)
    competitive_gap: RatedInput = Field(default_factory=RatedInput)
    future_relevance: RatedInput = Field(default_factory=RatedInput)
    strategic_fit: RatedInput = Field(default_factory=RatedInput)
    feasibility: Literal["unknown", "very_high", "high", "medium", "low", "very_low"] = "unknown"
    feasibility_explanation: str = ""

    @model_validator(mode="after")
    def feasibility_basis(self):
        if self.feasibility != "unknown" and not self.feasibility_explanation.strip():
            raise ValueError("An indicative feasibility level needs an explanation")
        if self.frequency.value is not None and self.frequency.basis != "source_review":
            raise ValueError("Frequency requires a source-reviewed eligible population, not reviewer judgment")
        return self


class ScoreInterval(Contract):
    lower: float = Field(ge=0, le=100)
    upper: float = Field(ge=0, le=100)
    value: float | None = Field(default=None, ge=0, le=100)


class CrpsResult(Contract):
    policy_version: str = POLICY_VERSION
    evidence_strength: ScoreInterval
    customer_priority: ScoreInterval
    priority_band: Literal["P1 Critical", "P2 High", "P3 Medium", "P4 Low", "P5 Watch"] | None
    contributions: dict[str, ScoreInterval]
    missing_inputs: list[str]
    feasibility: str


def _interval(inputs: dict[str, RatedInput], weights: dict[str, float]) -> ScoreInterval:
    known = sum(inputs[name].value * weight for name, weight in weights.items() if inputs[name].value is not None)
    missing_weight = sum(weight for name, weight in weights.items() if inputs[name].value is None)
    lower, upper = round(known, 4), round(known + 100 * missing_weight, 4)
    return ScoreInterval(lower=lower, upper=upper, value=lower if not missing_weight else None)


def evaluate_crps(inputs: CrpsInputs) -> CrpsResult:
    evidence_parts = {name: getattr(inputs.evidence, name) for name in EVIDENCE_WEIGHTS}
    evidence = _interval(evidence_parts, EVIDENCE_WEIGHTS)
    dimensions = {name: getattr(inputs, name) for name in WEIGHTS if name != "evidence_strength"}
    contributions = {}
    for name, weight in WEIGHTS.items():
        interval = evidence if name == "evidence_strength" else _interval({name: dimensions[name]}, {name: 1.0})
        contributions[name] = ScoreInterval(lower=round(weight * interval.lower, 4),
                                             upper=round(weight * interval.upper, 4),
                                             value=round(weight * interval.value, 4) if interval.value is not None else None)
    lower = round(sum(item.lower for item in contributions.values()), 4)
    upper = round(sum(item.upper for item in contributions.values()), 4)
    complete = all(item.value is not None for item in contributions.values())
    band = None
    if complete:
        band = ("P1 Critical" if lower >= 80 else "P2 High" if lower >= 65 else
                "P3 Medium" if lower >= 50 else "P4 Low" if lower >= 35 else "P5 Watch")
    missing = [name for name in WEIGHTS if name != "evidence_strength" and dimensions[name].value is None]
    missing += [f"evidence.{name}" for name, part in evidence_parts.items() if part.value is None]
    return CrpsResult(evidence_strength=evidence,
                      customer_priority=ScoreInterval(lower=lower, upper=upper, value=lower if complete else None),
                      priority_band=band, contributions=contributions, missing_inputs=missing,
                      feasibility=inputs.feasibility)


def frequency_from_sample(relevant: int, eligible: int, *, representative: bool,
                          requirement_matched: bool) -> int | None:
    """Only use the PDF prevalence buckets for an eligible representative frame."""
    if relevant < 0 or eligible < 0 or relevant > eligible:
        raise ValueError("Counts must satisfy 0 <= relevant <= eligible")
    if not representative or not requirement_matched or eligible == 0:
        return None
    share = relevant / eligible
    return 10 if share < .01 else 25 if share < .03 else 45 if share < .07 else 65 if share < .15 else 85 if share <= .30 else 100


def independent_family_score(families: list[str]) -> int | None:
    """A reviewed source-family list; repeated pages in one family count once."""
    count = len({family.strip().casefold() for family in families if family.strip()})
    return None if count == 0 else (30, 55, 75, 90, 100)[min(count, 5) - 1]
