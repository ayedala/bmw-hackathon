from __future__ import annotations

import pytest

from bmw_pm.contracts import (
    AcceptanceProposal,
    CriterionDefinition,
    CriterionInput,
    EvidenceSpan,
    FeedbackRecord,
    PolicyVersion,
    Polarity,
    RequirementRevision,
    RequirementScope,
    Signal,
    SourceLocator,
)
from bmw_pm.decision import assess_ranking, rank_scores, reach_input, score_requirement
from bmw_pm.intelligence.requirements import build_requirement_candidates
from bmw_pm.utils import utc_now


def _policy(weights=(0.25, 0.25, 0.25, 0.25)) -> PolicyVersion:
    names = (
        "customer_impact",
        "evidence_backed_reach",
        "strategic_contribution",
        "competitive_outlook_need",
    )
    return PolicyVersion(
        policy_id="test",
        revision=1,
        name="Synthetic test policy",
        criteria={
            name: CriterionDefinition(
                dimension="customer" if index < 2 else "business",
                weight=weight, anchor_0="zero", anchor_4="four",
            )
            for index, (name, weight) in enumerate(zip(names, weights))
        },
        saturation_share=0.05,
        unknown_rule="synthetic test rule",
        approved=False,
        elicitation_record="Synthetic fixture; not a BMW policy.",
    )


def _requirement(requirement_id: str = "req-a") -> RequirementRevision:
    return RequirementRevision(
        requirement_id=requirement_id,
        revision=1,
        title="Synthetic candidate",
        customer_outcome="Complete a synthetic task.",
        scope=RequirementScope(models=["X99"], countries=["ZZ"], powertrains=["ICE"]),
        use_conditions=[],
        acceptance_proposal=AcceptanceProposal(method="Synthetic fixture"),
        target_status="pending_engineering_review",
        supporting_signal_ids=["signal-a"],
        counter_signal_ids=[],
        alternatives=[],
        assumptions=["Synthetic fixture"],
        missing_evidence=[],
        feasibility="unknown",
        lifecycle_status="needs_review",
        created_by="test",
        created_at=utc_now(),
        denominator_feedback_records=10,
        processed_feedback_records=10,
        support_count=1,
        counter_count=0,
    )


def _score(values: tuple[float, float, float, float], requirement_id="req-a"):
    names = list(_policy().criteria)
    return score_requirement(
        requirement=_requirement(requirement_id),
        policy=_policy(),
        criterion_inputs={
            name: CriterionInput(value=value, basis="Synthetic reviewed value")
            for name, value in zip(names, values)
        },
        profile_id="synthetic",
        profile_revision=1,
        corpus_manifest_hash="abc",
        run_id="run-test",
    )


def test_documented_score_arithmetic_and_policy_reversal() -> None:
    score_a = _score((3, 2, 3, 1), "a")
    score_b = _score((2, 3, 2, 3), "b")
    assert score_a.lower_bound == score_a.upper_bound == 56.25
    assert score_b.lower_bound == score_b.upper_bound == 62.5
    assert [item.requirement_id for item in rank_scores([score_a, score_b])] == ["b", "a"]
    assert assess_ranking([score_a, score_b])["resolved_value_pairs"] == [("b", "a")]

    weighted = _policy((0.4, 0.1, 0.4, 0.1))
    names = list(weighted.criteria)
    weighted_a = score_requirement(
        requirement=_requirement("a"),
        policy=weighted,
        criterion_inputs={
            name: CriterionInput(value=value, basis="Synthetic reviewed value")
            for name, value in zip(names, (3, 2, 3, 1))
        },
        profile_id="synthetic",
        profile_revision=1,
        corpus_manifest_hash="abc",
        run_id="run-test",
    )
    assert weighted_a.lower_bound == 67.5


def test_readiness_does_not_promote_complete_arithmetic_to_approved_evidence():
    from bmw_pm.decision.readiness import assess_readiness
    result = assess_readiness(_requirement(), _score((3, 2, 3, 1)), _policy())
    assert not result.ready_for_commitment
    assert any("entailment" in reason for reason in result.blockers)
    assert any("policy" in reason for reason in result.blockers)
    assert any("Feasibility" in reason for reason in result.blockers)


def test_unknowns_are_intervals_and_known_weights_are_not_renormalized() -> None:
    inputs = {
        "customer_impact": CriterionInput(value=3, basis="Synthetic reviewed value"),
        "evidence_backed_reach": CriterionInput(value=2, basis="Synthetic reviewed value"),
        "strategic_contribution": CriterionInput(value=3, basis="Synthetic reviewed value"),
        "competitive_outlook_need": CriterionInput(missing_reason="Not supplied"),
    }
    score = score_requirement(
        requirement=_requirement(),
        policy=_policy(),
        criterion_inputs=inputs,
        profile_id="synthetic",
        profile_revision=1,
        corpus_manifest_hash="abc",
        run_id="run-test",
    )
    assert (score.lower_bound, score.upper_bound) == (50.0, 75.0)
    assert score.contributions["competitive_outlook_need"] == (0.0, 25.0)
    assert (score.dimension_intervals["customer"].lower_bound,
            score.dimension_intervals["customer"].upper_bound) == (62.5, 62.5)
    assert (score.dimension_intervals["business"].lower_bound,
            score.dimension_intervals["business"].upper_bound) == (37.5, 87.5)
    assert score.dimension_intervals["business"].missing_criteria == ["competitive_outlook_need"]
    assert score.feasibility_status == "unknown"
    assert assess_ranking([score, _score((3, 2, 3, 1), "other")])["unresolved_value_pairs"]


def test_partial_processing_expands_reach_and_zero_scope_stays_unknown() -> None:
    partial = reach_input(
        support_count=2, eligible_count=100, processed_count=20, saturation_share=0.1
    )
    assert partial.value is None
    assert partial.lower_value == 0.8
    assert partial.upper_value == 4.0
    empty = reach_input(
        support_count=0, eligible_count=0, processed_count=0, saturation_share=0.1
    )
    assert empty.value is None
    assert empty.missing_reason


def test_duplicate_signals_do_not_inflate_unique_record_recurrence() -> None:
    locator = SourceLocator(
        source_id="source",
        source_hash="0" * 64,
        locator_type="sheet_range",
        sheet="Synthetic",
        cell_range="A2:L2",
        exact_quote="Synthetic complaint.",
    )
    record = FeedbackRecord(
        record_id="record-1",
        source_id="source",
        source_record_id="X-1",
        raw_text_ref="source#Synthetic!I2",
        cleaned_text="Synthetic complaint.",
        redacted_text="Synthetic complaint.",
        raw_country="ZZ",
        country="ZZ",
        raw_model="X99",
        model_code="X99",
        raw_brand="BMW",
        raw_sales_description="X99",
        raw_derivative="X99",
        powertrain_raw="ICE",
        powertrain="ICE",
        powertrain_mapping_status="exact",
        source_label="A",
        row_locators=[locator],
        transformation_ids=[],
    )
    signals = [
        Signal(
            signal_id=f"signal-{index}",
            feedback_record_id=record.record_id,
            need_domain="synthetic_need",
            atomic_claim="Synthetic complaint.",
            customer_outcome="Complete a synthetic task.",
            polarity=Polarity.COMPLAINT,
            vehicle_scope={"model": "X99"},
            evidence_spans=[
                EvidenceSpan(
                    record_id=record.record_id,
                    locator=locator,
                    text="Synthetic complaint.",
                    start=0,
                    end=20,
                )
            ],
            run_id="run-test",
            provider_mode="baseline_no_ai",
        )
        for index in range(2)
    ]
    candidates = build_requirement_candidates(
        signals=signals,
        eligible_records=[record],
        processed_record_ids={record.record_id},
        profile={
            "profile_id": "synthetic",
            "model_family": "X99",
            "countries": ["ZZ"],
            "powertrains": ["ICE"],
        },
        created_by="test",
    )
    assert len(candidates) == 1
    assert candidates[0].support_count == 1
    assert len(candidates[0].supporting_signal_ids) == 2
    assert len(candidates[0].evidence_links) == 2
    assert all(link.semantic_entailment == "unreviewed" for link in candidates[0].evidence_links)
    assert all(link.author_expertise == "unknown" for link in candidates[0].evidence_links)


def test_mixed_and_neutral_signals_are_context_not_numeric_support() -> None:
    base = _requirement()
    locator = SourceLocator(
        source_id="source", source_hash="0" * 64,
        locator_type="sheet_range", sheet="Synthetic", cell_range="A2:L2",
        exact_quote="Synthetic complaint.",
    )
    record = FeedbackRecord(
        record_id="record-1", source_id="source", source_record_id="X-1",
        raw_text_ref="source#Synthetic!I2", cleaned_text="Synthetic complaint.",
        redacted_text="Synthetic complaint.", raw_country="ZZ", country="ZZ",
        raw_model="X99", model_code="X99", raw_brand="BMW",
        raw_sales_description="X99", raw_derivative="X99",
        powertrain_raw="ICE", powertrain="ICE", powertrain_mapping_status="exact",
        source_label="A", row_locators=[locator], transformation_ids=[],
    )
    signals = [
        Signal(
            signal_id=f"signal-{polarity.value}", feedback_record_id=record.record_id,
            need_domain="synthetic_need", atomic_claim=record.redacted_text,
            customer_outcome=base.customer_outcome, polarity=polarity,
            vehicle_scope={"model": "X99"},
            evidence_spans=[EvidenceSpan(
                record_id=record.record_id, locator=locator,
                text=record.redacted_text, start=0, end=len(record.redacted_text),
            )], run_id="run-test", provider_mode="baseline_no_ai",
        )
        for polarity in (Polarity.COMPLAINT, Polarity.MIXED, Polarity.OBSERVATION)
    ]
    candidates = build_requirement_candidates(
        signals=signals, eligible_records=[record], processed_record_ids={record.record_id},
        profile={"profile_id": "synthetic", "model_family": "X99",
                 "countries": ["ZZ"], "powertrains": ["ICE"]}, created_by="test",
    )
    assert len(candidates) == 1
    assert candidates[0].support_count == 1
    assert len(candidates[0].context_signal_ids) == 2

    wrong_quote = signals[0].model_copy(update={
        "evidence_spans": [signals[0].evidence_spans[0].model_copy(update={
            "text": "Unsupported statement"
        })]
    })
    with pytest.raises(ValueError, match="unresolved evidence"):
        build_requirement_candidates(
            signals=[wrong_quote], eligible_records=[record],
            processed_record_ids={record.record_id},
            profile={"profile_id": "synthetic", "model_family": "X99",
                     "countries": ["ZZ"], "powertrains": ["ICE"]}, created_by="test",
        )


def test_requirement_reach_uses_configured_applicable_powertrain_scope() -> None:
    locator = SourceLocator(
        source_id="source", source_hash="0" * 64, locator_type="sheet_range",
        sheet="Synthetic", cell_range="A2:L2", exact_quote="Charging is slow.",
    )
    bev = FeedbackRecord(
        record_id="bev", source_id="source", source_record_id="X-1",
        raw_text_ref="source#Synthetic!I2", cleaned_text="Charging is slow.",
        redacted_text="Charging is slow.", raw_country="ZZ", country="ZZ",
        raw_model="X99", model_code="X99", raw_brand="BMW",
        raw_sales_description="X99", raw_derivative="X99",
        powertrain_raw="BEV", powertrain="BEV", powertrain_mapping_status="exact",
        source_label="A", row_locators=[locator], transformation_ids=[],
    )
    ice = bev.model_copy(update={"record_id": "ice", "source_record_id": "X-2",
                                 "powertrain_raw": "ICE", "powertrain": "ICE"})
    signal = Signal(
        signal_id="charging-signal", feedback_record_id="bev",
        need_domain="charging", atomic_claim="Charging is slow.",
        customer_outcome="Charge without avoidable delays.", polarity=Polarity.COMPLAINT,
        vehicle_scope={"model": "X99", "powertrain": "BEV"},
        evidence_spans=[EvidenceSpan(
            record_id="bev", locator=locator, text="Charging is slow.", start=0, end=17,
        )], run_id="run-test", provider_mode="baseline_no_ai",
    )
    candidates = build_requirement_candidates(
        signals=[signal], eligible_records=[bev, ice],
        processed_record_ids={"bev", "ice"},
        profile={"profile_id": "synthetic", "model_family": "X99",
                 "countries": ["ZZ"], "powertrains": ["ICE", "BEV"],
                 "domain_applicability": {"charging": ["BEV"]}}, created_by="test",
    )
    assert len(candidates) == 1
    assert candidates[0].scope.powertrains == ["BEV"]
    assert candidates[0].denominator_feedback_records == 1
    assert candidates[0].processed_feedback_records == 1
