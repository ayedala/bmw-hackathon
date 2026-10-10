from decimal import Decimal

import pytest

from bmw_pm.contracts import AcceptanceProposal, RequirementRevision, RequirementScope
from bmw_pm.decision.economics import (
    FinancialCase, UpdateBusinessCase, compare_business_cases, evaluate_business_case,
)
from bmw_pm.decision.portfolio import PortfolioPlan, evaluate_portfolio
from bmw_pm.utils import utc_now


def requirement(requirement_id="req-a", feasibility="unknown"):
    return RequirementRevision(
        requirement_id=requirement_id, revision=1, title="Synthetic update",
        customer_outcome="Complete a synthetic vehicle task.",
        scope=RequirementScope(models=["X99"], countries=["ZZ"], powertrains=["ICE"]),
        use_conditions=[], acceptance_proposal=AcceptanceProposal(method="Synthetic review"),
        target_status="pending_engineering_review", supporting_signal_ids=[],
        counter_signal_ids=[], alternatives=[], assumptions=[], missing_evidence=[],
        feasibility=feasibility, lifecycle_status="needs_review", created_by="test",
        created_at=utc_now(), denominator_feedback_records=0,
        processed_feedback_records=0, support_count=0, counter_count=0,
    )


def plan(requirement_id="req-a", *, upfront="100", increment=2,
         sales="matched", competitor="matched_reviewed", finance="reviewed"):
    year = dict(year=2027, baseline_units=10, incremental_units=increment,
                adoption_rate="1", net_revenue_per_incremental_vehicle="150",
                baseline_vehicle_cost_per_incremental_vehicle="50",
                net_revenue_uplift_per_existing_adopter="20",
                variable_cost_per_adopter="5", annual_fixed_cost="10")
    case = dict(upfront_cost=upfront, years=[year])
    return UpdateBusinessCase(
        requirement_id=requirement_id, requirement_revision=1, model="X99", market="ZZ",
        powertrains=["ICE"], currency="EUR", discount_rate="0",
        cases={name: case for name in ("downside", "base", "upside")},
        sales_scope_status=sales, competitor_status=competitor,
        finance_status=finance, evidence_refs=["synthetic:test-input"],
    )


def test_cash_flow_npv_and_break_even_are_reproducible():
    result = evaluate_business_case(requirement(feasibility="conditional"), plan())
    base = result.scenarios["base"]
    # 2*100 + 10*20 - 12*5 - 10 - 100 = 230.
    assert base.net_present_value == Decimal("230.00")
    assert base.annual[0].net_cash_flow == Decimal("330.00")
    assert result.break_even_flat_incremental_units_per_year == 0
    assert result.ready_for_comparison
    assert result.ready_for_commitment


def test_scope_and_review_gates_prevent_false_recommendations():
    result = evaluate_business_case(requirement(), plan(sales="combined_proxy",
                                                         competitor="candidate_only", finance="draft"))
    assert not result.ready_for_comparison
    assert len(result.blockers) == 3
    assert len(result.commitment_blockers) == 4
    assert compare_business_cases([result])["excluded_unreviewed"] == ["req-a"]
    with pytest.raises(ValueError, match="powertrains exceed"):
        evaluate_business_case(requirement(), plan().model_copy(update={"powertrains": ["BEV"]}))


def test_break_even_when_fixed_cost_needs_sales_lift():
    result = evaluate_business_case(requirement(feasibility="conditional"),
                                    plan(upfront="300", increment=0))
    # Without new sales: 10*(20-5)-10-300=-160. Each extra unit adds 100-5=95.
    assert result.scenarios["base"].net_present_value == Decimal("-160.00")
    assert result.break_even_flat_incremental_units_per_year == 2


def test_financial_comparison_does_not_claim_engineering_feasibility():
    result = evaluate_business_case(requirement(), plan())
    assert result.ready_for_comparison
    assert not result.ready_for_commitment
    assert result.commitment_blockers == ["Engineering feasibility has not been reviewed."]


def test_comparison_keeps_overlapping_scenarios_unresolved():
    a = evaluate_business_case(requirement("a", "conditional"), plan("a"))
    b_plan = plan("b", upfront="150")
    b_plan = b_plan.model_copy(update={"cases": {
        "downside": b_plan.cases["base"].model_copy(update={"upfront_cost": Decimal("250")}),
        "base": b_plan.cases["base"],
        "upside": b_plan.cases["base"].model_copy(update={"upfront_cost": Decimal("50")}),
    }})
    b = evaluate_business_case(requirement("b", "conditional"), b_plan)
    report = compare_business_cases([a, b])
    assert report["base_npv_order"] == ["a", "b"]
    assert report["unresolved_pairs"] == [("a", "b")]


def test_discounting_and_horizon_alignment():
    original = plan()
    first = original.cases["base"].years[0].model_copy(update={
        "baseline_units": 0, "incremental_units": 1, "adoption_rate": Decimal("0"),
        "net_revenue_uplift_per_existing_adopter": Decimal("0"),
        "annual_fixed_cost": Decimal("0"),
    })
    second = first.model_copy(update={"year": 2028})
    two_years = FinancialCase(upfront_cost=0, years=[first, second])
    discounted = original.model_copy(update={"discount_rate": Decimal("0.1"),
                                           "cases": {name: two_years for name in original.cases}})
    result = evaluate_business_case(requirement(feasibility="conditional"), discounted)
    assert result.scenarios["base"].net_present_value == Decimal("173.55")
    with pytest.raises(ValueError, match="same years"):
        UpdateBusinessCase.model_validate({**original.model_dump(mode="json"),
            "cases": {"downside": two_years.model_dump(mode="json"),
                      "base": original.cases["base"].model_dump(mode="json"),
                      "upside": original.cases["upside"].model_dump(mode="json")}})


def varied_plan(requirement_id="a"):
    original = plan(requirement_id)
    base = original.cases["base"]
    downside = base.model_copy(update={"years": [base.years[0].model_copy(
        update={"incremental_units": 0})]})
    upside = base.model_copy(update={"years": [base.years[0].model_copy(
        update={"incremental_units": 4})]})
    return original.model_copy(update={"cases": {
        "downside": downside, "base": base, "upside": upside}})


def reviewed_portfolio(budget="300", **changes):
    payload = {
        "capital_budget": budget,
        "budget_review_status": "reviewed",
        "interaction_review_status": "reviewed_none",
        "evidence_refs": ["synthetic:budget-review"],
    }
    payload.update(changes)
    return PortfolioPlan.model_validate(payload)


def test_sensitivity_uses_supplied_driver_range_and_shows_order_changes():
    a = evaluate_business_case(requirement("a", "conditional"), varied_plan())
    b = evaluate_business_case(requirement("b", "conditional"), plan("b", upfront="150"))
    driver = a.driver_sensitivity[0]
    assert driver.driver == "incremental_units"
    assert (driver.downside_input_npv, driver.base_npv, driver.upside_input_npv) == (
        Decimal("40.00"), Decimal("230.00"), Decimal("420.00"))
    orders = compare_business_cases([a, b])["scenario_npv_orders"]
    assert orders["downside"] == ["b", "a"]
    assert orders["base"] == ["a", "b"]


def test_portfolio_budget_dependency_and_exclusion_are_explicit():
    results = [evaluate_business_case(requirement(key, "conditional"), case)
               for key, case in (("a", plan("a")), ("b", plan("b", upfront="150")))]
    assert evaluate_portfolio(results, reviewed_portfolio("300")).selected_base.requirement_ids == ["a", "b"]
    budgeted = evaluate_portfolio(results, reviewed_portfolio("200"))
    assert budgeted.selected_base.requirement_ids == ["a"]
    assert budgeted.selected_base.upfront_capital == Decimal("100.00")
    dependent = evaluate_portfolio(results, reviewed_portfolio("200", dependencies=[
        {"selected": "a", "requires": "b"}]))
    assert dependent.selected_base.requirement_ids == ["b"]
    excluded = evaluate_portfolio(results, reviewed_portfolio("300", mutually_exclusive=[
        {"first": "a", "second": "b"}]))
    assert excluded.selected_base.requirement_ids == ["a"]


def test_sourced_interaction_changes_portfolio_without_changing_standalone_order():
    results = [evaluate_business_case(requirement(key, "conditional"), case)
               for key, case in (("a", plan("a")), ("b", plan("b", upfront="150")))]
    interaction = {"pair": {"first": "a", "second": "b"},
                   "additional_upfront_cost": "20",
                   "operating_npv_adjustment": {name: "-280" for name in
                                                ("downside", "base", "upside")},
                   "review_status": "reviewed", "evidence_refs": ["synthetic:overlap"],
                   "rationale": "Shared customers reduce combined incremental sales."}
    assessed = evaluate_portfolio(results, reviewed_portfolio("300",
        interaction_review_status="reviewed_adjustments", interactions=[interaction]))
    assert assessed.status == "assessed"
    assert assessed.selected_base.requirement_ids == ["a"]
    assert compare_business_cases(results)["base_npv_order"] == ["a", "b"]


def test_unreviewed_budget_or_interactions_block_portfolio_selection():
    result = evaluate_business_case(requirement("a", "conditional"), plan("a"))
    draft = PortfolioPlan(capital_budget="100")
    assessment = evaluate_portfolio([result], draft)
    assert assessment.status == "needs_review"
    assert assessment.selected_base is None
    assert len(assessment.blockers) == 2
    unknown_engineering = evaluate_business_case(requirement("a"), plan("a"))
    empty = evaluate_portfolio([unknown_engineering], reviewed_portfolio("100"))
    assert empty.status == "no_eligible_options"
    assert empty.excluded_options == ["a"]


def test_three_series_use_separate_scopes_and_one_reviewed_budget():
    specs = (("one", "F70", "GB", [], "100"),
             ("five", "G60", "US", ["US"], "150"),
             ("seven", "G70", "US", ["US"], "200"))
    results = []
    for key, model, market, countries, upfront in specs:
        scoped_requirement = requirement(key, "conditional").model_copy(update={
            "scope": RequirementScope(models=[model], countries=countries, powertrains=["ICE"])})
        scoped_plan = plan(key, upfront=upfront).model_copy(update={
            "model": model, "market": market,
            "market_applicability_status": "matched_reviewed" if not countries else "unassessed"})
        results.append(evaluate_business_case(scoped_requirement, scoped_plan))
    assert {item.model for item in results} == {"F70", "G60", "G70"}
    assessed = evaluate_portfolio(results, reviewed_portfolio("500"))
    assert assessed.selected_base.requirement_ids == ["five", "one", "seven"]
    f70_unreviewed = evaluate_business_case(
        requirement("one", "conditional").model_copy(update={
            "scope": RequirementScope(models=["F70"], countries=[], powertrains=["ICE"])}),
        plan("one").model_copy(update={"model": "F70", "market": "GB"}))
    assert not f70_unreviewed.ready_for_comparison
    assert "Market applicability" in f70_unreviewed.blockers[0]
    with pytest.raises(ValueError, match="market must match"):
        evaluate_business_case(requirement("five").model_copy(update={
            "scope": RequirementScope(models=["G60"], countries=["US"], powertrains=["ICE"])}),
            plan("five").model_copy(update={"model": "G60", "market": "GB"}))
