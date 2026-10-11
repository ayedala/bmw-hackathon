"""Editable, source-labelled feature cost scenarios for the review workbench."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import json

import pandas as pd
import streamlit as st

from bmw_pm.decision.feature_cost import FeatureCostPlan, estimate_feature_cost


_CATEGORY_OPTIONS = [
    "mechanical_parts", "electrical_parts", "battery_capacity", "assembly",
    "engineering", "tooling", "prototype_and_validation", "homologation",
    "software_and_cloud", "warranty_and_service", "other",
]


def _blank(value):
    if value is None or isinstance(value, str) and not value.strip():
        return True
    return bool(pd.isna(value))


def render_feature_cost(requirement, root: Path) -> None:
    scope = requirement.scope
    _render(requirement.title, scope.models[0], scope.countries[0] if scope.countries else "",
            scope.powertrains, root, requirement.requirement_id)


def render_feature_cost_for_idea(feature_name: str, model: str, market: str,
                                 powertrain: str, root: Path, key: str) -> None:
    _render(feature_name, model, market, [powertrain], root, key)


def _render(feature_name: str, model: str, market_default: str, powertrains: list[str],
            root: Path, key: str) -> None:
    with st.expander("Estimate feature implementation cost", expanded=False):
        st.caption(
            "Build a scoped low/base/high estimate from quoted parts, engineering hours, "
            "tooling, assembly, validation and service costs. Values stay in this browser "
            "session until downloaded; this does not change a requirement or priority."
        )
        refs = json.loads((root / "configs/feature_cost_references_v1.json").read_text(encoding="utf-8"))["references"]
        with st.expander(f"Public reference points and their limits ({len(refs)})"):
            st.caption("Vehicle components, labor and charging-site infrastructure are different cost scopes. These figures are references for your own assumptions, not automatic estimates.")
            for item in sorted(refs, key=lambda row: (row["category"], row["label"])):
                value = (f"{item['value_low']}–{item['value_high']}" if "value_low" in item
                         else str(item["value"]))
                year = f"{item['price_year']} prices" if item["price_year"] is not None else "price year not stated"
                market = ", ".join(item["markets"])
                st.markdown(f"**[{item['label']}]({item['source_url']})**: {value} {item['unit']} ({market}; {year}; {item['category'].replace('_', ' ')})")
                st.caption(item["limit"])

        with st.form(f"feature-cost-{key}"):
            left, middle, right = st.columns(3)
            feature = left.text_input("Feature or system", value=feature_name)
            market = middle.text_input("Market", value=market_default)
            powertrain = right.selectbox("Powertrain", powertrains)
            feature_type = st.selectbox("Main system type", ["mechanical", "electrical", "software", "battery", "mixed"])
            left, middle, right = st.columns(3)
            currency = left.text_input("Currency", value="USD")
            price_year = middle.number_input("Price year", min_value=2000, max_value=2100, value=None, step=1)
            planned = right.number_input("Vehicles in program", min_value=1, value=None, step=1000,
                                         help="Expected vehicles in this exact model/market/powertrain scope.")
            fitment = st.number_input("Share receiving the feature, %", min_value=0.1, max_value=100.0,
                                      value=None, step=1.0)
            st.caption("Enter each cost as a quantity × cost per unit. Program lines are paid once; equipped-vehicle lines repeat for each fitted vehicle. Add rows as needed.")
            rows = st.data_editor(pd.DataFrame([
                {"name": "Mechanical parts", "category": "mechanical_parts", "basis": "equipped_vehicle",
                 "quantity": None, "unit": "part", "low_unit_cost": None, "base_unit_cost": None,
                 "high_unit_cost": None, "source": "", "note": ""},
                {"name": "Electrical parts", "category": "electrical_parts", "basis": "equipped_vehicle",
                 "quantity": None, "unit": "part", "low_unit_cost": None, "base_unit_cost": None,
                 "high_unit_cost": None, "source": "", "note": ""},
                {"name": "Engineering", "category": "engineering", "basis": "program",
                 "quantity": None, "unit": "hour", "low_unit_cost": None, "base_unit_cost": None,
                 "high_unit_cost": None, "source": "", "note": ""},
                {"name": "Tooling and validation", "category": "tooling", "basis": "program",
                 "quantity": None, "unit": "program", "low_unit_cost": None, "base_unit_cost": None,
                 "high_unit_cost": None, "source": "", "note": ""},
            ]), num_rows="dynamic", width="stretch", hide_index=True,
                column_config={
                    "category": st.column_config.SelectboxColumn(options=_CATEGORY_OPTIONS),
                    "basis": st.column_config.SelectboxColumn(options=["program", "equipped_vehicle"]),
                    "quantity": st.column_config.NumberColumn(min_value=0.001),
                    "low_unit_cost": st.column_config.NumberColumn(min_value=0),
                    "base_unit_cost": st.column_config.NumberColumn(min_value=0),
                    "high_unit_cost": st.column_config.NumberColumn(min_value=0),
                }, key=f"feature-cost-lines-{key}")
            scope_note = st.text_input("Scope and assumptions", placeholder="e.g., US G60 BEV, 2029 launch, supplier quotes pending")
            submitted = st.form_submit_button("Calculate cost range")
        if not submitted:
            return
        try:
            if planned is None or fitment is None:
                raise ValueError("Enter the program vehicle count and feature fitment rate.")
            if price_year is None:
                raise ValueError("Enter the price year after aligning all line-item costs to it.")
            active = []
            for row in rows.to_dict("records"):
                fields = ("quantity", "low_unit_cost", "base_unit_cost", "high_unit_cost")
                if all(_blank(row.get(field)) for field in fields):
                    continue
                if any(_blank(row.get(field)) for field in fields):
                    raise ValueError(f"Complete all quantity and cost cells for {row.get('name') or 'the new line'}.")
                active.append(row)
            plan = FeatureCostPlan.model_validate({
                "feature_name": feature, "feature_type": feature_type,
                "model": model, "market": market,
                "powertrain": powertrain, "currency": currency.upper(), "price_year": int(price_year),
                "planned_vehicles": int(planned), "fitment_rate": Decimal(str(fitment)) / 100,
                "lines": active, "scope_note": scope_note,
            })
            report = estimate_feature_cost(plan)
        except (ValueError, TypeError) as error:
            st.error(str(error))
            return
        st.caption(f"Expected equipped vehicles: {report['expected_equipped_vehicles']} · draft requiring engineering and finance review")
        if report["missing_cost_categories"]:
            st.warning("Partial cost subtotal. Check: " + ", ".join(name.replace("_", " ") for name in report["missing_cost_categories"]))
        columns = st.columns(3)
        for column, case in zip(columns, ("low", "base", "high"), strict=True):
            result = report["scenarios"][case]
            column.metric(case.title() + " costed subtotal", f"{currency.upper()} {result['total_program_cost']}")
            column.caption(f"{currency.upper()} {result['fully_loaded_cost_per_equipped_vehicle']} per equipped vehicle for entered lines, including allocated program cost")
        with st.expander("Cost breakdown"):
            st.dataframe(report["scenarios"]["base"]["breakdown"], hide_index=True, width="stretch")
        st.download_button("Download cost assumptions and results", json.dumps({"plan": plan.model_dump(mode="json"), "result": report}, indent=2),
                           file_name="feature-cost-scenario.json", mime="application/json")
