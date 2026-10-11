"""Framework arithmetic and missingness checks from the supplied worked example."""
import pytest

from bmw_pm.decision.crps_legacy import (CrpsInputs, EvidenceInputs, RatedInput,
                                  evaluate_crps, frequency_from_sample,
                                  independent_family_score)


def rating(value):
    return RatedInput(value=value, basis="reviewer_judgment", explanation="Synthetic reviewed input")


def source_rating(value):
    return RatedInput(value=value, basis="source_review", explanation="Representative eligible-population fixture", evidence_ids=["survey-1"])


def test_pdf_worked_example_and_separate_feasibility():
    # E = .30Q + .25D + .20K + .15N + .10T = 88 in this fixture.
    inputs = CrpsInputs(customer_impact=rating(92),
        evidence=EvidenceInputs(source_quality=rating(88), source_diversity=rating(88),
                                consistency=rating(88), volume=rating(88), recency=rating(88)),
        frequency=source_rating(82), market_relevance=rating(91), competitive_gap=rating(85),
        future_relevance=rating(93), strategic_fit=rating(80),
        feasibility="medium", feasibility_explanation="Engineering review fixture")
    result = evaluate_crps(inputs)
    assert result.evidence_strength.value == 88
    assert result.customer_priority.value == 88.35
    assert result.priority_band == "P1 Critical"
    assert sum(x.value for x in result.contributions.values()) == pytest.approx(88.35)
    assert result.feasibility == "medium"
    assert evaluate_crps(inputs.model_copy(update={"feasibility": "low"})).customer_priority.value == 88.35


def test_missing_values_keep_weight_and_do_not_claim_a_band():
    result = evaluate_crps(CrpsInputs(customer_impact=rating(80)))
    assert result.customer_priority.lower == 20
    assert result.customer_priority.upper == 95
    assert result.customer_priority.value is None
    assert result.priority_band is None
    assert "evidence.recency" in result.missing_inputs
    assert len(result.missing_inputs) == 10


def test_source_ratings_require_provenance_and_sample_recurrence_is_not_prevalence():
    with pytest.raises(ValueError):
        RatedInput(value=90, basis="source_review", explanation="No source")
    with pytest.raises(ValueError):
        RatedInput(value=90, basis="missing")
    with pytest.raises(ValueError):
        CrpsInputs(frequency=rating(82))
    assert frequency_from_sample(20, 100, representative=False, requirement_matched=True) is None
    assert frequency_from_sample(20, 100, representative=True, requirement_matched=False) is None
    assert frequency_from_sample(20, 100, representative=True, requirement_matched=True) == 85
    assert independent_family_score(["study", "study", "feedback"]) == 55
    with pytest.raises(ValueError):
        frequency_from_sample(101, 100, representative=True, requirement_matched=True)
