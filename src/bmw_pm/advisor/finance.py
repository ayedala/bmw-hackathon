"""Conditional economics from explicit user assumptions, using the core calculator."""
from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import Field

from ..contracts import Contract
from ..decision.economics import AnnualEconomics, FinancialCase, evaluate_case


class ScenarioInput(Contract):
    scenario: Literal["Downside", "Base", "Upside"]
    upfront_cost: Decimal = Field(ge=0, allow_inf_nan=False)
    annual_fixed_cost: Decimal = Field(ge=0, allow_inf_nan=False)
    baseline_units: int = Field(ge=0)
    incremental_units: int = Field(ge=0)
    adoption_rate: Decimal = Field(ge=0, le=1, allow_inf_nan=False)
    revenue_per_extra_vehicle: Decimal = Field(ge=0, allow_inf_nan=False)
    cost_per_extra_vehicle: Decimal = Field(ge=0, allow_inf_nan=False)
    revenue_uplift_per_adopter: Decimal = Field(ge=0, allow_inf_nan=False)
    feature_cost_per_adopter: Decimal = Field(ge=0, allow_inf_nan=False)


def scenario_results(rows: list[dict], *, years: int, discount_rate: Decimal, source: str) -> list[dict]:
    if not source.strip():
        raise ValueError("Name the estimate source/owner or label the values as hypothetical assumptions.")
    if not 1 <= years <= 10 or not Decimal(0) <= discount_rate < Decimal(1):
        raise ValueError("Choose 1–10 years and a discount rate between 0 and 1.")
    scenarios = [ScenarioInput.model_validate(row) for row in rows]
    if len(scenarios) != 3 or {row.scenario for row in scenarios} != {"Downside", "Base", "Upside"}:
        raise ValueError("Provide one downside, base and upside scenario.")
    output = []
    for row in scenarios:
        case = FinancialCase(upfront_cost=row.upfront_cost, years=[AnnualEconomics(
            year=2026 + i, baseline_units=row.baseline_units, incremental_units=row.incremental_units,
            adoption_rate=row.adoption_rate, net_revenue_per_incremental_vehicle=row.revenue_per_extra_vehicle,
            baseline_vehicle_cost_per_incremental_vehicle=row.cost_per_extra_vehicle,
            net_revenue_uplift_per_existing_adopter=row.revenue_uplift_per_adopter,
            variable_cost_per_adopter=row.feature_cost_per_adopter, annual_fixed_cost=row.annual_fixed_cost,
        ) for i in range(years)])
        calculated = evaluate_case(case, discount_rate)
        annual = calculated.annual[0]
        output.append({"Scenario": row.scenario, "Upfront cost": float(row.upfront_cost),
                       "Annual added revenue": float(annual.incremental_vehicle_revenue + annual.existing_vehicle_revenue_uplift),
                       "Annual net cash flow": float(annual.net_cash_flow), "NPV": float(calculated.net_present_value),
                       "Assumption source": source, "Status": "Conditional scenario — not a forecast or approval"})
    return output
