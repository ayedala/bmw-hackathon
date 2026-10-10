from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from ..contracts import Contract


class AdvisorRequest(Contract):
    journey: Literal["idea", "improve", "compare"]
    model_code: Literal["F70", "G60", "G70"]
    market: str = Field(pattern=r"^[A-Z]{2}$")
    powertrain: Literal["ALL", "ICE", "PHEV", "BEV"] = "ALL"
    model_year: int = Field(default=2026, ge=2020, le=2040)
    question: str = Field(default="", max_length=4000)
    ideas: list[str] = Field(default_factory=list, max_length=5)
    objective: str = Field(default="Customer value and profitable growth", max_length=1000)
    planning_years: int = Field(default=3, ge=1, le=10)
    currency: str = Field(default="EUR", pattern=r"^[A-Z]{3}$")
    budget: float | None = Field(default=None, gt=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def valid_scope(self) -> "AdvisorRequest":
        if self.journey == "idea" and len(self.question.strip()) < 10:
            raise ValueError("Describe your idea in at least 10 characters.")
        if self.journey == "compare":
            if len(self.ideas) < 2 or any(not 10 <= len(idea.strip()) <= 1000 for idea in self.ideas):
                raise ValueError("Enter two to five ideas, each between 10 and 1,000 characters.")
            if len({idea.strip().casefold() for idea in self.ideas}) != len(self.ideas):
                raise ValueError("Enter distinct ideas to compare.")
        if self.model_code == "F70" and self.powertrain not in {"ALL", "ICE"}:
            raise ValueError("The current 1 Series dataset covers ICE vehicles only.")
        return self


class EvidenceItem(Contract):
    evidence_id: str
    channel: str
    title: str
    text: str
    selection_reason: str
    scope: dict[str, Any] = Field(default_factory=dict)
    locator: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)


class TopicSummary(Contract):
    domain: str
    outcome: str
    eligible_records: int
    supporting_records: int
    praise_records: int
    context_records: int


class EvidencePacket(Contract):
    request: AdvisorRequest
    feedback_records: int
    topics: list[TopicSummary]
    evidence: list[EvidenceItem]
    limitations: list[str]
    fingerprint: str


class ResearchPlan(Contract):
    focus_domains: list[str]
    search_terms: list[str]
    research_questions: list[str]
    rationale: str


class Claim(Contract):
    text: str
    basis: Literal["evidence", "inference", "assumption", "unknown"]
    evidence_ids: list[str]
    explanation: str


class Option(Contract):
    option_id: str
    title: str
    proposal: str
    customer_case: list[Claim]
    competitors: list[Claim]
    feasibility: Claim
    cost_outlook: Claim
    revenue_outlook: Claim
    delivery_steps: list[str]
    risks: list[str]
    validation_needed: list[str]


class DecisionReport(Contract):
    headline: str
    summary: str
    options: list[Option]
    preferred_option_id: str | None
    recommendation: Claim
    comparison: list[Claim]
    follow_up_questions: list[str]


class ResearchBundle(Contract):
    text: str
    sources: list[EvidenceItem]
    search_actions: list[str]
    response_id: str
    model_id: str


class AdvisorResult(Contract):
    run_id: str
    created_at: str
    mode: Literal["live_ai"] = "live_ai"
    model_id: str
    prompt_version: str
    packet: EvidencePacket
    plan: ResearchPlan
    research: ResearchBundle
    report: DecisionReport
    steps: list[str]
    usage: list[dict[str, Any]]
