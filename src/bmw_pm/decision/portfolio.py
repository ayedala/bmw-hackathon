"""Optional, reviewed capital-budget scenarios for combinations of updates."""
from __future__ import annotations

from decimal import Decimal
from itertools import combinations
from typing import Literal

from pydantic import Field, model_validator

from ..contracts import Contract
from ..utils import content_hash
from .economics import BusinessCaseResult, CaseName, Money, _money


class RequirementPair(Contract):
    first: str
    second: str

    @model_validator(mode="after")
    def distinct(self) -> "RequirementPair":
        if not self.first or not self.second or self.first == self.second:
            raise ValueError("a requirement pair needs two distinct IDs")
        return self

    def key(self) -> frozenset[str]:
        return frozenset((self.first, self.second))


class RequirementDependency(Contract):
    selected: str
    requires: str

    @model_validator(mode="after")
    def distinct(self) -> "RequirementDependency":
        if not self.selected or not self.requires or self.selected == self.requires:
            raise ValueError("a dependency needs two distinct IDs")
        return self


class PortfolioInteraction(Contract):
    pair: RequirementPair
    additional_upfront_cost: Money = Decimal(0)
    operating_npv_adjustment: dict[CaseName, Money]
    review_status: Literal["reviewed", "draft"] = "draft"
    evidence_refs: list[str] = Field(default_factory=list)
    rationale: str

    @model_validator(mode="after")
    def complete(self) -> "PortfolioInteraction":
        if set(self.operating_npv_adjustment) != {"downside", "base", "upside"}:
            raise ValueError("interaction needs downside, base and upside operating NPV adjustments")
        if not (self.operating_npv_adjustment["downside"] <=
                self.operating_npv_adjustment["base"] <=
                self.operating_npv_adjustment["upside"]):
            raise ValueError("interaction adjustments must preserve downside <= base <= upside")
        if not self.rationale.strip():
            raise ValueError("interaction rationale is required")
        return self


class PortfolioPlan(Contract):
    schema_version: Literal["1"] = "1"
    capital_budget: Money = Field(ge=0)
    budget_review_status: Literal["reviewed", "draft"] = "draft"
    interaction_review_status: Literal["reviewed_none", "reviewed_adjustments", "unassessed"] = "unassessed"
    evidence_refs: list[str] = Field(default_factory=list)
    dependencies: list[RequirementDependency] = Field(default_factory=list)
    mutually_exclusive: list[RequirementPair] = Field(default_factory=list)
    interactions: list[PortfolioInteraction] = Field(default_factory=list)

    @model_validator(mode="after")
    def no_duplicate_relations(self) -> "PortfolioPlan":
        if len({(item.selected, item.requires) for item in self.dependencies}) != len(self.dependencies):
            raise ValueError("duplicate portfolio dependency")
        for name, pairs in (("mutually exclusive", self.mutually_exclusive),
                            ("interaction", [item.pair for item in self.interactions])):
            if len({pair.key() for pair in pairs}) != len(pairs):
                raise ValueError(f"duplicate {name} pair")
        if self.interaction_review_status == "reviewed_none" and self.interactions:
            raise ValueError("reviewed_none cannot contain interaction adjustments")
        if self.interaction_review_status == "reviewed_adjustments" and not self.interactions:
            raise ValueError("reviewed_adjustments needs at least one interaction")
        return self


class PortfolioCandidate(Contract):
    requirement_ids: list[str]
    upfront_capital: Money
    scenario_npv: dict[CaseName, Money]


class PortfolioAssessment(Contract):
    status: Literal["assessed", "needs_review", "no_eligible_options"]
    input_hash: str
    capital_budget: Money
    eligible_options: list[str]
    excluded_options: list[str]
    blockers: list[str]
    feasible_subsets: int
    selected_base: PortfolioCandidate | None
    scenario_best: dict[CaseName, PortfolioCandidate]
    top_base_candidates: list[PortfolioCandidate]
    interpretation: str = (
        "Conditional budget comparison among reviewed, eligible options only. "
        "Scenario labels are simultaneous stress views, not probabilities. "
        "Pairwise adjustments capture only declared interactions; no decision is approved automatically."
    )


def evaluate_portfolio(results: list[BusinessCaseResult], plan: PortfolioPlan) -> PortfolioAssessment:
    """Enumerate at most 15 options; select the highest base NPV feasible subset."""
    by_id = {result.requirement_id: result for result in results}
    if len(by_id) != len(results):
        raise ValueError("portfolio option IDs must be unique")
    referenced = set().union(
        *(pair.key() for pair in plan.mutually_exclusive),
        *(item.pair.key() for item in plan.interactions),
        *((item.selected, item.requires) for item in plan.dependencies),
    )
    unknown = referenced - by_id.keys()
    if unknown:
        raise ValueError(f"portfolio references unknown options: {', '.join(sorted(unknown))}")

    eligible = sorted((result for result in results if result.ready_for_commitment),
                      key=lambda item: item.requirement_id)
    if len(eligible) > 15:
        raise ValueError("portfolio enumeration supports at most 15 eligible options")
    for attribute in ("currency", "discount_rate"):
        if len({getattr(result, attribute) for result in eligible}) > 1:
            raise ValueError(f"portfolio options need one {attribute} policy")
    if len({tuple(row.year for row in result.scenarios["base"].annual)
            for result in eligible}) > 1:
        raise ValueError("portfolio options need the same planning years")

    blockers = []
    if plan.budget_review_status != "reviewed" or not plan.evidence_refs:
        blockers.append("Capital budget needs finance review and a source reference.")
    if plan.interaction_review_status == "unassessed":
        blockers.append("Dependencies, exclusions, shared sales and cost interactions need review.")
    if any(item.review_status != "reviewed" or not item.evidence_refs for item in plan.interactions):
        blockers.append("Every interaction adjustment needs review and a source reference.")
    excluded = sorted(by_id.keys() - {item.requirement_id for item in eligible})
    common = dict(input_hash=content_hash({"plan": plan.model_dump(mode="json"),
                                           "cases": {key: value.input_hash for key, value in sorted(by_id.items())}}),
                  capital_budget=plan.capital_budget,
                  eligible_options=[item.requirement_id for item in eligible],
                  excluded_options=excluded, blockers=blockers,
                  feasible_subsets=0, selected_base=None, scenario_best={}, top_base_candidates=[])
    if blockers:
        return PortfolioAssessment(status="needs_review", **common)
    if not eligible:
        return PortfolioAssessment(status="no_eligible_options", **common)

    candidates = []
    for size in range(len(eligible) + 1):
        for subset in combinations(eligible, size):
            ids = {item.requirement_id for item in subset}
            if any(item.selected in ids and item.requires not in ids for item in plan.dependencies):
                continue
            if any(pair.key() <= ids for pair in plan.mutually_exclusive):
                continue
            active_interactions = [item for item in plan.interactions if item.pair.key() <= ids]
            capital = sum((max(item.scenarios[name].upfront_cost
                               for name in ("downside", "base", "upside")) for item in subset), Decimal(0))
            capital += sum((item.additional_upfront_cost for item in active_interactions), Decimal(0))
            if capital < 0:
                raise ValueError("interaction adjustments produce negative upfront capital")
            if capital > plan.capital_budget:
                continue
            npvs = {}
            for name in ("downside", "base", "upside"):
                value = sum((item.scenarios[name].net_present_value for item in subset), Decimal(0))
                value += sum((item.operating_npv_adjustment[name] - item.additional_upfront_cost
                              for item in active_interactions), Decimal(0))
                npvs[name] = _money(value)
            candidates.append(PortfolioCandidate(requirement_ids=sorted(ids),
                                                 upfront_capital=_money(capital), scenario_npv=npvs))
    ordered = sorted(candidates, key=lambda item: (-item.scenario_npv["base"],
                                                   item.upfront_capital, item.requirement_ids))
    scenario_best = {
        name: min(candidates, key=lambda item: (-item.scenario_npv[name],
                                               item.upfront_capital, item.requirement_ids))
        for name in ("downside", "base", "upside")
    }
    return PortfolioAssessment(status="assessed", **{**common,
        "feasible_subsets": len(candidates), "selected_base": ordered[0],
        "scenario_best": scenario_best, "top_base_candidates": ordered[:5]})
