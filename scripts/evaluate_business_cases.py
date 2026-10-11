"""Make blank financial inputs or assess completed, scoped update scenarios.

Run with PYTHONPATH=src. This command reads the canonical database but never
changes requirements, scores, decisions, or audit records.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from bmw_pm.decision.economics import (
    UpdateBusinessCase, compare_business_cases, evaluate_business_case,
)
from bmw_pm.decision.portfolio import PortfolioPlan, evaluate_portfolio
from bmw_pm.storage import Database


ANNUAL_FIELDS = (
    "year", "baseline_units", "incremental_units", "adoption_rate",
    "net_revenue_per_incremental_vehicle", "baseline_vehicle_cost_per_incremental_vehicle",
    "net_revenue_uplift_per_existing_adopter", "variable_cost_per_adopter",
    "annual_fixed_cost",
)


def blank_option(requirement) -> dict:
    return {
        "requirement_id": requirement.requirement_id,
        "requirement_revision": requirement.revision,
        "model": requirement.scope.models[0],
        "market": requirement.scope.countries[0] if requirement.scope.countries else None,
        "powertrains": requirement.scope.powertrains,
        "currency": None,
        "discount_rate": None,
        "market_applicability_status": "unassessed",
        "sales_scope_status": "unassessed",
        "competitor_status": "unassessed",
        "finance_status": "draft",
        "evidence_refs": [],
        "assumptions": [],
        "cases": {
            name: {"upfront_cost": None, "years": [{key: None for key in ANNUAL_FIELDS}]}
            for name in ("downside", "base", "upside")
        },
    }


def missing_fields(value, prefix="") -> list[str]:
    if value is None:
        return [prefix]
    if isinstance(value, dict):
        return [item for key, nested in value.items()
                for item in missing_fields(nested, f"{prefix}/{key}")]
    if isinstance(value, list):
        return [item for index, nested in enumerate(value)
                for item in missing_fields(nested, f"{prefix}/{index}")]
    return []


def imported_context(database: Database, plan: UpdateBusinessCase) -> dict:
    """Show potentially relevant imported rows without treating them as verified inputs."""
    with database.connect() as connection:
        if not connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='imported_evidence'"
        ).fetchone():
            return {"sales_observations": [], "competitor_candidates": []}
        def rows(table: str) -> list[dict]:
            return [json.loads(row[0])["payload"] for row in connection.execute(
                "SELECT payload_json FROM imported_evidence WHERE table_name=?", (table,)
            ).fetchall()]
        sales = [
            {"year": item["calendar_year"], "units": item["units"],
             "model_scope": json.loads(item["model_scope_json"]),
             "combined_scope": bool(item["scope_is_combined"]),
             "observation_status": item["observation_status"],
             "source_version_id": item["source_version_id"],
             "locator_id": item["locator_id"]}
            for item in rows("sales_observation")
            if item["market_code"] == plan.market
            and plan.model in json.loads(item["model_scope_json"])
        ]
        competitors = [
            {"vehicle_id": item["vehicle_id"], "match_class": item["match_class"],
             "reviewed_by": item["reviewed_by"], "reviewed_at": item["reviewed_at"]}
            for item in rows("benchmark_cohort_member")
            if item["target_chassis"] == plan.model and item["market_code"] == plan.market
        ]
    return {"sales_observations": sorted(sales, key=lambda item: item["year"]),
            "competitor_candidates": competitors,
            "interpretation": "Imported context only; scope, ownership and competitive claims need review before use."}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("data/processed/bmw_pm.db"))
    parser.add_argument("--require-model", action="append", default=[], metavar="CODE",
                        help="require a scoped option for this model; repeat for F70, G60, G70")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--template", type=Path, help="write an empty private JSON worksheet")
    action.add_argument("--input", type=Path, help="assess a filled private JSON worksheet")
    args = parser.parse_args(argv)
    if not args.db.is_file():
        parser.error(f"database does not exist: {args.db}")
    database = Database(args.db)
    summaries = database.requirement_summaries()
    requirements = {item["requirement"].requirement_id: item["requirement"]
                    for item in summaries}
    if args.template:
        available = {model for item in summaries for model in item["requirement"].scope.models}
        absent = sorted(set(args.require_model) - available)
        if absent:
            parser.error("no requirement cards for requested model(s): " + ", ".join(absent))
        payload = {"schema_version": "1", "options": [blank_option(item["requirement"])
                   for item in summaries], "portfolio": None}
        args.template.parent.mkdir(parents=True, exist_ok=True)
        with args.template.open("x", encoding="utf-8") as output:
            json.dump(payload, output, indent=2)
        print(json.dumps({"created": str(args.template), "options": len(payload["options"])}))
        return 0

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "1" or not isinstance(payload.get("options"), list):
        parser.error("expected schema_version 1 and an options list")
    missing = missing_fields(payload["options"], "/options")
    if payload.get("portfolio") is not None:
        missing.extend(missing_fields(payload["portfolio"], "/portfolio"))
    if missing:
        print(json.dumps({"status": "needs_inputs", "missing_fields": missing}, indent=2))
        return 2
    plans = [UpdateBusinessCase.model_validate(option) for option in payload["options"]]
    if not plans:
        parser.error("business case input contains no options")
    absent = sorted(set(args.require_model) - {plan.model for plan in plans})
    if absent:
        parser.error("business case input has no option for requested model(s): " + ", ".join(absent))
    identities = [(plan.requirement_id, plan.requirement_revision) for plan in plans]
    if len(identities) != len(set(identities)):
        parser.error("duplicate requirement revision in business case input")
    results = []
    for plan in plans:
        requirement = requirements.get(plan.requirement_id)
        if requirement is None:
            parser.error(f"unknown requirement: {plan.requirement_id}")
        results.append(evaluate_business_case(requirement, plan))
    score_by_id = {item["requirement"].requirement_id: item["score"] for item in summaries}
    report = {"results": [result.model_dump(mode="json") for result in results],
              "imported_context": {plan.requirement_id: imported_context(database, plan)
                                   for plan in plans},
              "existing_customer_value": {
                  plan.requirement_id: {
                      "score_interval": (
                          [score_by_id[plan.requirement_id].lower_bound,
                           score_by_id[plan.requirement_id].upper_bound]
                          if score_by_id[plan.requirement_id] else None
                      ),
                      "note": "Current exploratory customer/business score; policy and evidence are unreviewed.",
                  } for plan in plans},
              "comparison": compare_business_cases(results),
              "portfolio": (
                  evaluate_portfolio(results, PortfolioPlan.model_validate(payload["portfolio"])).model_dump(mode="json")
                  if payload.get("portfolio") is not None else
                  {"status": "not_requested", "note": "Add a reviewed portfolio plan to assess budget and interactions."}
              )}
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
