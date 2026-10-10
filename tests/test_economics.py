from decimal import Decimal

import pytest

from bmw_pm.contracts import AcceptanceProposal, RequirementRevision, RequirementScope
from bmw_pm.decision.economics import (
    FinancialCase, UpdateBusinessCase, compare_business_cases, evaluate_business_case,
)
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
