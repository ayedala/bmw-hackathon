"""Transparent manufacturing and development cost scenarios for a proposed feature.

Public benchmarks can inform a line item, but the estimator only calculates from
explicit quantities and prices supplied for the selected vehicle/program scope.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from pydantic import Field, model_validator

from ..contracts import Contract
from ..utils import content_hash


CostCategory = Literal[
    "mechanical_parts", "electrical_parts", "battery_capacity", "assembly",
    "engineering", "tooling", "prototype_and_validation", "homologation",
    "software_and_cloud", "warranty_and_service", "other",
]
CostBasis = Literal["program", "equipped_vehicle"]
FeatureType = Literal["mechanical", "electrical", "software", "battery", "mixed"]
_CENT = Decimal("0.01")
_COST_PROMPTS: dict[str, tuple[str, ...]] = {
    "mechanical": ("mechanical_parts", "assembly", "engineering", "tooling",
                   "prototype_and_validation", "warranty_and_service"),
    "electrical": ("electrical_parts", "assembly", "engineering",
                   "prototype_and_validation", "homologation", "warranty_and_service"),
    "software": ("engineering", "prototype_and_validation", "software_and_cloud",
                 "warranty_and_service"),
    "battery": ("battery_capacity", "electrical_parts", "assembly", "engineering",
                "tooling", "prototype_and_validation", "homologation",
                "warranty_and_service"),
    "mixed": (),
}


class FeatureCostLine(Contract):
    name: str = Field(min_length=2)
    category: CostCategory
    basis: CostBasis
    quantity: Decimal = Field(gt=0)
    unit: str = Field(min_length=1)
    low_unit_cost: Decimal = Field(ge=0)
    base_unit_cost: Decimal = Field(ge=0)
    high_unit_cost: Decimal = Field(ge=0)
    source: str = Field(min_length=3)
    note: str = Field(min_length=3)

    @model_validator(mode="after")
    def ordered_costs(self) -> "FeatureCostLine":
        if not self.low_unit_cost <= self.base_unit_cost <= self.high_unit_cost:
            raise ValueError("line costs must satisfy low <= base <= high")
        return self


class FeatureCostPlan(Contract):
    schema_version: str = "1"
    feature_name: str = Field(min_length=3)
    feature_type: FeatureType
    model: str = Field(min_length=2)
    market: str = Field(min_length=2)
    powertrain: str = Field(min_length=2)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    price_year: int = Field(ge=2000, le=2100)
    planned_vehicles: int = Field(gt=0)
    fitment_rate: Decimal = Field(gt=0, le=1)
    lines: list[FeatureCostLine] = Field(min_length=1)
    scope_note: str = Field(min_length=3)

    @model_validator(mode="after")
    def require_cost_drivers(self) -> "FeatureCostPlan":
        if not any(line.basis == "equipped_vehicle" for line in self.lines):
            raise ValueError("include at least one per-equipped-vehicle cost line")
        return self


def estimate_feature_cost(plan: FeatureCostPlan) -> dict:
    """Return three deterministic scenarios; no supplier prices are inferred."""
    equipped = Decimal(plan.planned_vehicles) * plan.fitment_rate
    included = {line.category for line in plan.lines}
    missing_categories = [name for name in _COST_PROMPTS[plan.feature_type] if name not in included]
    scenarios = {}
    for case, field in (("low", "low_unit_cost"), ("base", "base_unit_cost"),
                        ("high", "high_unit_cost")):
        program = Decimal(0)
        per_equipped = Decimal(0)
        breakdown = []
        for line in plan.lines:
            amount = line.quantity * getattr(line, field)
            if line.basis == "program":
                program += amount
                program_total = amount
            else:
                per_equipped += amount
                program_total = amount * equipped
            breakdown.append({
                "name": line.name, "category": line.category, "basis": line.basis,
                "amount_on_basis": str(amount.quantize(_CENT, rounding=ROUND_HALF_UP)),
                "program_total": str(program_total.quantize(_CENT, rounding=ROUND_HALF_UP)),
                "source": line.source,
            })
        total = program + per_equipped * equipped
        scenarios[case] = {
            "upfront_program_cost": str(program.quantize(_CENT, rounding=ROUND_HALF_UP)),
            "cost_per_equipped_vehicle": str(per_equipped.quantize(_CENT, rounding=ROUND_HALF_UP)),
            "amortized_program_cost_per_equipped_vehicle": str((program / equipped).quantize(_CENT, rounding=ROUND_HALF_UP)),
            "fully_loaded_cost_per_equipped_vehicle": str((total / equipped).quantize(_CENT, rounding=ROUND_HALF_UP)),
            "total_program_cost": str(total.quantize(_CENT, rounding=ROUND_HALF_UP)),
            "breakdown": breakdown,
        }
    return {
        "feature_name": plan.feature_name, "model": plan.model,
        "market": plan.market, "powertrain": plan.powertrain,
        "currency": plan.currency, "price_year": plan.price_year,
        "planned_vehicles": plan.planned_vehicles,
        "expected_equipped_vehicles": str(equipped),
        "fitment_rate": str(plan.fitment_rate),
        "input_hash": content_hash(plan), "scenarios": scenarios,
        "missing_cost_categories": missing_categories,
        "status": ("partial_cost_subtotal" if missing_categories else
                   "draft_estimate_requires_engineering_and_finance_review"),
        "interpretation": (
            "Feature-specific subtotal from supplied quantities and costs. Public references "
            "are market benchmarks, not BMW supplier quotes. Omitted categories remain "
            "cost gaps. Excludes revenue, sales lift and feasibility."
        ),
    }
