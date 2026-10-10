"""Auditable, standalone financial scenarios for proposed vehicle updates.

These calculations use supplied assumptions; they do not infer sales lift from
feedback counts or turn an imported competitor claim into a verified benchmark.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
from typing import Literal

from pydantic import Field, model_validator

from ..contracts import Contract, RequirementRevision
from ..utils import content_hash


Money = Decimal
CaseName = Literal["downside", "base", "upside"]
_CENT = Decimal("0.01")


class AnnualEconomics(Contract):
    year: int = Field(ge=2020, le=2100)
    baseline_units: int = Field(ge=0)
    incremental_units: int = Field(ge=0)
    adoption_rate: Decimal = Field(ge=0, le=1)
    net_revenue_per_incremental_vehicle: Money = Field(ge=0)
    baseline_vehicle_cost_per_incremental_vehicle: Money = Field(ge=0)
    net_revenue_uplift_per_existing_adopter: Money = Field(ge=0)
    variable_cost_per_adopter: Money = Field(ge=0)
    annual_fixed_cost: Money = Field(ge=0)


class FinancialCase(Contract):
    upfront_cost: Money = Field(ge=0)
    years: list[AnnualEconomics] = Field(min_length=1)

    @model_validator(mode="after")
    def distinct_ordered_years(self) -> "FinancialCase":
        values = [year.year for year in self.years]
        if values != sorted(set(values)):
            raise ValueError("case years must be unique and ascending")
        return self


class UpdateBusinessCase(Contract):
    schema_version: str = "1"
    requirement_id: str
    requirement_revision: int = Field(ge=1)
    model: str
    market: str
    powertrains: list[str] = Field(min_length=1)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    discount_rate: Decimal = Field(ge=0, lt=1)
    cases: dict[CaseName, FinancialCase]
    sales_scope_status: Literal["matched", "combined_proxy", "unassessed"] = "unassessed"
    competitor_status: Literal["matched_reviewed", "candidate_only", "unassessed"] = "unassessed"
    finance_status: Literal["reviewed", "draft"] = "draft"
    evidence_refs: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def aligned_cases(self) -> "UpdateBusinessCase":
        if set(self.cases) != {"downside", "base", "upside"}:
            raise ValueError("provide downside, base, and upside cases")
        years = [[year.year for year in case.years] for case in self.cases.values()]
        if any(item != years[0] for item in years[1:]):
            raise ValueError("all cases must cover the same years")
        if len(self.powertrains) != len(set(self.powertrains)):
            raise ValueError("powertrains must be unique")
        return self


class AnnualResult(Contract):
    year: int
    incremental_vehicle_revenue: Money
    existing_vehicle_revenue_uplift: Money
    baseline_vehicle_variable_cost: Money
    update_variable_cost: Money
    annual_fixed_cost: Money
    net_cash_flow: Money
    discounted_cash_flow: Money


class FinancialResult(Contract):
    upfront_cost: Money
    net_present_value: Money
    annual: list[AnnualResult]


class BusinessCaseResult(Contract):
    requirement_id: str
    requirement_revision: int
    input_hash: str
    currency: str
    discount_rate: Decimal
    sales_scope_status: str
    competitor_status: str
    finance_status: str
    evidence_refs: list[str]
    assumptions: list[str]
    scenarios: dict[CaseName, FinancialResult]
    break_even_flat_incremental_units_per_year: int | None
    ready_for_comparison: bool
    blockers: list[str]
    ready_for_commitment: bool
    commitment_blockers: list[str]
    interpretation: str = (
        "Standalone conditional scenarios, not a forecast or portfolio optimum. "
        "Feedback frequency is not a sales-lift estimate."
    )


def _money(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def evaluate_case(case: FinancialCase, discount_rate: Decimal) -> FinancialResult:
    first_year = case.years[0].year
    annual = []
    present_value = -case.upfront_cost
    for item in case.years:
        # Baseline units exclude incremental units. Existing-unit revenue uplift
        # is counted once; update-specific cost applies to all adopters.
        incremental = item.incremental_units * item.net_revenue_per_incremental_vehicle
        uplift = item.baseline_units * item.adoption_rate * item.net_revenue_uplift_per_existing_adopter
        baseline_cost = item.incremental_units * item.baseline_vehicle_cost_per_incremental_vehicle
        variable = (item.baseline_units + item.incremental_units) * item.adoption_rate * item.variable_cost_per_adopter
        cash = incremental + uplift - baseline_cost - variable - item.annual_fixed_cost
        discounted = cash / (Decimal(1) + discount_rate) ** (item.year - first_year + 1)
        present_value += discounted
        annual.append(AnnualResult(
            year=item.year,
            incremental_vehicle_revenue=_money(incremental),
            existing_vehicle_revenue_uplift=_money(uplift),
            baseline_vehicle_variable_cost=_money(baseline_cost),
            update_variable_cost=_money(variable),
            annual_fixed_cost=_money(item.annual_fixed_cost),
            net_cash_flow=_money(cash),
            discounted_cash_flow=_money(discounted),
        ))
    return FinancialResult(upfront_cost=_money(case.upfront_cost),
                           net_present_value=_money(present_value), annual=annual)


def _break_even_flat_units(case: FinancialCase, discount_rate: Decimal) -> int | None:
    """Minimum equal incremental units in every year, starting from zero."""
    first_year = case.years[0].year
    without_incremental = -case.upfront_cost
    contribution_per_extra_unit = Decimal(0)
    for item in case.years:
        factor = (Decimal(1) + discount_rate) ** (item.year - first_year + 1)
        without_incremental += (
            item.baseline_units * item.adoption_rate
            * (item.net_revenue_uplift_per_existing_adopter - item.variable_cost_per_adopter)
            - item.annual_fixed_cost
        ) / factor
        contribution_per_extra_unit += (
            item.net_revenue_per_incremental_vehicle
            - item.baseline_vehicle_cost_per_incremental_vehicle
            - item.adoption_rate * item.variable_cost_per_adopter
        ) / factor
    if without_incremental >= 0:
        return 0
    if contribution_per_extra_unit <= 0:
        return None
    return int((-without_incremental / contribution_per_extra_unit).to_integral_value(rounding=ROUND_CEILING))


def evaluate_business_case(requirement: RequirementRevision,
                           plan: UpdateBusinessCase) -> BusinessCaseResult:
    if (requirement.requirement_id, requirement.revision) != (plan.requirement_id, plan.requirement_revision):
        raise ValueError("business case must reference this exact requirement revision")
    if plan.model not in requirement.scope.models or plan.market not in requirement.scope.countries:
        raise ValueError("business case model and market must match requirement scope")
    if not set(plan.powertrains) <= set(requirement.scope.powertrains):
        raise ValueError("business case powertrains exceed requirement scope")

    scenarios = {name: evaluate_case(plan.cases[name], plan.discount_rate)
                 for name in ("downside", "base", "upside")}
    blockers = []
    if plan.sales_scope_status != "matched":
        blockers.append("Sales exposure is not verified for this model, market, and powertrain scope.")
    if plan.competitor_status != "matched_reviewed":
        blockers.append("A relevant competitor gap has not been reviewed under matched conditions.")
    if plan.finance_status != "reviewed":
        blockers.append("Cost, margin, adoption, and sales-lift assumptions need finance review.")
    if not plan.evidence_refs:
        blockers.append("No source references were supplied for the business assumptions.")
    if not (scenarios["downside"].net_present_value <= scenarios["base"].net_present_value
            <= scenarios["upside"].net_present_value):
        blockers.append("Scenario NPVs are not ordered downside <= base <= upside; inspect assumptions.")
    commitment_blockers = list(blockers)
    if requirement.feasibility not in {"conditional", "feasible_reviewed"}:
        commitment_blockers.append("Engineering feasibility has not been reviewed.")
    return BusinessCaseResult(
        requirement_id=plan.requirement_id,
        requirement_revision=plan.requirement_revision,
        input_hash=content_hash(plan),
        currency=plan.currency,
        discount_rate=plan.discount_rate,
        sales_scope_status=plan.sales_scope_status,
        competitor_status=plan.competitor_status,
        finance_status=plan.finance_status,
        evidence_refs=plan.evidence_refs,
        assumptions=plan.assumptions,
        scenarios=scenarios,
        break_even_flat_incremental_units_per_year=_break_even_flat_units(
            plan.cases["base"], plan.discount_rate),
        ready_for_comparison=not blockers,
        blockers=blockers,
        ready_for_commitment=not commitment_blockers,
        commitment_blockers=commitment_blockers,
    )


def compare_business_cases(results: list[BusinessCaseResult]) -> dict[str, object]:
    """Only compare fully reviewed cases in the same currency and planning years."""
    ready = [result for result in results if result.ready_for_comparison]
    currencies = {result.currency for result in ready}
    if len(currencies) > 1:
        raise ValueError("currency conversion requires a sourced exchange-rate scenario")
    discount_rates = {result.discount_rate for result in ready}
    if len(discount_rates) > 1:
        raise ValueError("financial comparisons require the same discount-rate policy")
    horizons = {tuple(row.year for row in result.scenarios["base"].annual) for result in ready}
    if len(horizons) > 1:
        raise ValueError("financial comparisons require the same planning years")
    ordered = sorted(ready, key=lambda item: (-item.scenarios["base"].net_present_value,
                                            item.requirement_id))
    resolved, unresolved = [], []
    for index, left in enumerate(ordered):
        for right in ordered[index + 1:]:
            if left.scenarios["downside"].net_present_value > right.scenarios["upside"].net_present_value:
                resolved.append((left.requirement_id, right.requirement_id))
            elif right.scenarios["downside"].net_present_value > left.scenarios["upside"].net_present_value:
                resolved.append((right.requirement_id, left.requirement_id))
            else:
                unresolved.append((left.requirement_id, right.requirement_id))
    return {"base_npv_order": [item.requirement_id for item in ordered],
            "excluded_unreviewed": [item.requirement_id for item in results if not item.ready_for_comparison],
            "resolved_pairs": resolved, "unresolved_pairs": unresolved,
            "interpretation": "Standalone reviewed scenarios; shared customers, dependencies and budget constraints are not modeled."}
