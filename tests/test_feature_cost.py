from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from bmw_pm.decision.feature_cost import FeatureCostPlan, estimate_feature_cost
from bmw_pm.advisor.evidence import _add_feature_cost_references


def plan_data():
    return {
        "feature_name": "Rear climate controls", "feature_type": "electrical",
        "model": "G60", "market": "US",
        "powertrain": "BEV", "currency": "USD", "price_year": 2026,
        "planned_vehicles": 10000, "fitment_rate": "0.5",
        "scope_note": "Synthetic example; no BMW costs supplied.",
        "lines": [
            {"name": "Incremental parts", "category": "electrical_parts", "basis": "equipped_vehicle",
             "quantity": "2", "unit": "part", "low_unit_cost": "10", "base_unit_cost": "15",
             "high_unit_cost": "20", "source": "synthetic:test", "note": "Fixture only"},
            {"name": "Validation", "category": "prototype_and_validation", "basis": "program",
             "quantity": "1", "unit": "program", "low_unit_cost": "50000", "base_unit_cost": "100000",
             "high_unit_cost": "150000", "source": "synthetic:test", "note": "Fixture only"},
        ],
    }


def test_cost_separates_unit_and_upfront_and_amortizes_on_fitted_volume():
    result = estimate_feature_cost(FeatureCostPlan.model_validate(plan_data()))
    assert result["expected_equipped_vehicles"] == "5000.0"
    assert result["scenarios"]["base"]["upfront_program_cost"] == "100000.00"
    assert result["scenarios"]["base"]["cost_per_equipped_vehicle"] == "30.00"
    assert result["scenarios"]["base"]["fully_loaded_cost_per_equipped_vehicle"] == "50.00"
    assert result["scenarios"]["base"]["total_program_cost"] == "250000.00"
    assert result["status"] == "partial_cost_subtotal"
    assert "assembly" in result["missing_cost_categories"]
    assert [Decimal(result["scenarios"][name]["total_program_cost"]) for name in ("low", "base", "high")] == [Decimal("150000"), Decimal("250000"), Decimal("350000")]


def test_cost_rejects_inverted_range():
    data = plan_data()
    data["lines"][0]["low_unit_cost"] = "40"
    with pytest.raises(ValidationError, match="low <= base <= high"):
        FeatureCostPlan.model_validate(data)


def test_cost_requires_repeating_cost_line():
    data = plan_data()
    data["lines"] = data["lines"][1:]
    with pytest.raises(ValidationError, match="per-equipped-vehicle"):
        FeatureCostPlan.model_validate(data)


def test_advisor_uses_scoped_cost_reference_only_for_matching_us_request():
    us_evidence = []
    _add_feature_cost_references(SimpleNamespace(market="US"), {"battery", "range"}, us_evidence)
    assert [item.evidence_id for item in us_evidence] == ["cost-reference:doe_2025_light_vehicle_battery"]
    assert us_evidence[0].locator["url"].startswith("https://www.energy.gov/")
    eu_evidence = []
    _add_feature_cost_references(SimpleNamespace(market="DE"), {"battery"}, eu_evidence)
    assert eu_evidence == []


def test_advisor_keeps_german_labor_and_charging_site_costs_in_their_scopes():
    german = []
    _add_feature_cost_references(SimpleNamespace(market="DE"), {"assembly"}, german)
    assert [item.evidence_id for item in german] == [
        "cost-reference:destatis_2025_germany_manufacturing_labor"
    ]
    assert german[0].scope["market"] == "DE"

    us = []
    _add_feature_cost_references(SimpleNamespace(market="US"), {"charger", "charging"}, us)
    ids = {item.evidence_id for item in us}
    assert "cost-reference:nhtsa_2025_draft_onboard_charger" in ids
    assert not any("afdc_" in item_id for item_id in ids)


def test_cost_catalog_has_unique_scoped_sourced_records():
    import json
    from bmw_pm.advisor.evidence import ROOT

    records = json.loads((ROOT / "configs/feature_cost_references_v1.json").read_text())["references"]
    assert len(records) == 19
    assert len({item["id"] for item in records}) == len(records)
    for item in records:
        assert item["source_url"].startswith("https://")
        assert item["locator"] and item["unit"] and item["currency"]
        assert item["markets"] and item["category"] and item["evidence_type"]
        assert item["limit"]
        if item["advisor_eligible"]:
            assert item["price_year"] is not None
            assert item["category"] != "external_charging_infrastructure"
