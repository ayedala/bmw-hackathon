"""Tests for the canonical seven-factor CRPS and Decision Confidence."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from bmw_pm.contracts import CriterionInput
from bmw_pm.decision.crps import (
    DECISION_CONFIDENCE_WEIGHTS,
    DEFAULT_WEIGHTS,
    EVIDENCE_STRENGTH_WEIGHTS,
    FACTOR_ORDER,
    band_for,
    compute_competitive_gap,
    compute_crps,
    compute_decision_confidence,
    compute_evidence_strength,
    compute_frequency,
    compute_future_relevance,
    compute_market_relevance,
    compute_strategic_fit,
    load_policy,
    rank_requirements,
)

CONFIG = Path(__file__).resolve().parents[1] / "configs" / "crps_v1.json"
TODAY = date(2026, 10, 11)


def row(**overrides):
    """One evidence row with sensible defaults."""
    base = {
        "evidence_id": "EXT-aaa", "independence_group": "SRC-a",
        "source_family": "professional_review", "source_quality": 80,
        "market": "DE", "topic": "charging", "subtopic": "charging_speed",
        "published_at": "2026-06-01", "retrieved_at": "2026-10-01",
        "duplicate_of": None, "brand": "BMW",
    }
    base.update(overrides)
    return base


def known(value, basis="test"):
    return CriterionInput(value=value, basis=basis)


def unknown(reason="not available"):
    return CriterionInput(missing_reason=reason)


def all_factors(**overrides):
    """Seven factors, all known at 2.0 unless overridden."""
    factors = {name: known(2.0) for name in FACTOR_ORDER}
    factors.update(overrides)
    return factors


# --------------------------------------------------------------------------- #
# Policy config
# --------------------------------------------------------------------------- #


class TestPolicyConfig:
    def test_config_exists_and_weights_sum_to_one(self):
        payload = json.loads(CONFIG.read_text())
        weights = {name: spec["weight"] for name, spec in payload["factors"].items()}
        assert abs(sum(weights.values()) - 1.0) < 1e-9
        assert set(weights) == set(FACTOR_ORDER)

    def test_config_weights_match_the_specified_framework(self):
        payload = json.loads(CONFIG.read_text())
        weights = {name: spec["weight"] for name, spec in payload["factors"].items()}
        assert weights == {
            "customer_impact": 0.25, "evidence_strength": 0.20, "frequency": 0.15,
            "market_relevance": 0.15, "competitive_gap": 0.10,
            "future_relevance": 0.10, "strategic_fit": 0.05,
        }

    def test_module_literals_match_the_config(self):
        """Guard against the config and the code drifting apart."""
        assert load_policy(CONFIG)["weights"] == DEFAULT_WEIGHTS

    def test_policy_is_not_claimed_as_bmw_approved(self):
        payload = json.loads(CONFIG.read_text())
        assert payload["approved"] is False
        assert "hackathon" in payload["approval_status"]
        assert payload["priority_bands"]["approval_status"].endswith("unapproved")

    def test_subscore_weights_match_the_specification(self):
        assert EVIDENCE_STRENGTH_WEIGHTS == {
            "source_quality": 0.30, "source_diversity": 0.25, "consistency": 0.20,
            "evidence_volume": 0.15, "recency": 0.10,
        }
        assert DECISION_CONFIDENCE_WEIGHTS == {
            "evidence_strength": 0.45, "consistency": 0.25,
            "source_diversity": 0.20, "recency": 0.10,
        }
        assert abs(sum(EVIDENCE_STRENGTH_WEIGHTS.values()) - 1.0) < 1e-9
        assert abs(sum(DECISION_CONFIDENCE_WEIGHTS.values()) - 1.0) < 1e-9


# --------------------------------------------------------------------------- #
# CRPS arithmetic
# --------------------------------------------------------------------------- #


class TestCrpsArithmetic:
    def test_all_factors_at_four_is_one_hundred(self):
        result = compute_crps({name: known(4.0) for name in FACTOR_ORDER})
        assert result.crps_100_lower == pytest.approx(100.0)
        assert result.crps_100_upper == pytest.approx(100.0)
        assert result.is_point

    def test_all_factors_at_zero_is_zero(self):
        result = compute_crps({name: known(0.0) for name in FACTOR_ORDER})
        assert result.crps_100_lower == pytest.approx(0.0)
        assert result.is_point

    def test_contributions_reproduce_the_total(self):
        result = compute_crps(all_factors(customer_impact=known(4.0), frequency=known(1.0)))
        total = sum(f.lower_contribution for f in result.factors.values())
        assert result.lower_0_to_4 == pytest.approx(total)
        assert result.crps_100_lower == pytest.approx(total / 4 * 100)

    def test_each_factor_contributes_its_weight(self):
        for name in FACTOR_ORDER:
            factors = {other: known(0.0) for other in FACTOR_ORDER}
            factors[name] = known(4.0)
            result = compute_crps(factors)
            assert result.crps_100_lower == pytest.approx(DEFAULT_WEIGHTS[name] * 100), name

    def test_crps_100_is_the_0_to_4_score_rescaled(self):
        result = compute_crps(all_factors())
        assert result.crps_100_lower == pytest.approx(result.lower_0_to_4 / 4 * 100)

    def test_a_missing_factor_key_is_an_error(self):
        factors = all_factors()
        del factors["frequency"]
        with pytest.raises(ValueError, match="missing"):
            compute_crps(factors)

    def test_an_unexpected_factor_is_an_error(self):
        factors = all_factors()
        factors["made_up"] = known(4.0)
        with pytest.raises(ValueError, match="unknown CRPS factor"):
            compute_crps(factors)

    def test_weights_that_do_not_sum_to_one_are_rejected(self):
        bad = {"weights": {name: 0.1 for name in FACTOR_ORDER}, "policy_id": "bad", "revision": 1}
        with pytest.raises(ValueError, match="must sum to 1"):
            compute_crps(all_factors(), policy=bad)


# --------------------------------------------------------------------------- #
# Unknown handling - the load-bearing property
# --------------------------------------------------------------------------- #


class TestUnknownIntervals:
    def test_an_unknown_factor_produces_an_interval_not_a_point(self):
        result = compute_crps(all_factors(frequency=unknown()))
        assert not result.is_point
        assert result.crps_100_upper > result.crps_100_lower
        assert "frequency" in result.unknown_factors

    def test_an_unknown_factor_keeps_its_weight(self):
        """The interval width must equal the unknown factor's weight."""
        result = compute_crps(all_factors(frequency=unknown()))
        width = result.crps_100_upper - result.crps_100_lower
        assert width == pytest.approx(DEFAULT_WEIGHTS["frequency"] * 100)

    def test_unknowns_are_not_renormalised_away(self):
        """Known factors must contribute the same with or without an unknown."""
        complete = compute_crps({name: known(2.0) for name in FACTOR_ORDER})
        with_unknown = compute_crps(all_factors(strategic_fit=unknown()))
        expected_lower = complete.lower_0_to_4 - DEFAULT_WEIGHTS["strategic_fit"] * 2.0
        assert with_unknown.lower_0_to_4 == pytest.approx(expected_lower)

    def test_a_midpoint_is_never_substituted(self):
        result = compute_crps(all_factors(frequency=unknown()))
        assert result.factors["frequency"].lower_value == 0.0
        assert result.factors["frequency"].upper_value == 4.0

    def test_every_unknown_carries_a_reason(self):
        result = compute_crps(all_factors(frequency=unknown("no denominator")))
        assert result.factors["frequency"].missing_reason == "no denominator"
        assert not result.factors["frequency"].known

    def test_all_unknown_spans_the_full_range(self):
        result = compute_crps({name: unknown() for name in FACTOR_ORDER})
        assert result.crps_100_lower == pytest.approx(0.0)
        assert result.crps_100_upper == pytest.approx(100.0)

    def test_bounded_factor_narrows_rather_than_widens(self):
        bounded = CriterionInput(lower_value=2.0, upper_value=3.0, basis="bounded")
        result = compute_crps(all_factors(competitive_gap=bounded))
        width = result.crps_100_upper - result.crps_100_lower
        assert width == pytest.approx(DEFAULT_WEIGHTS["competitive_gap"] * 100 * 1 / 4)

    def test_display_shows_a_range_when_incomplete(self):
        assert "-" in compute_crps(all_factors(frequency=unknown())).display
        assert "-" not in compute_crps({n: known(2.0) for n in FACTOR_ORDER}).display


# --------------------------------------------------------------------------- #
# Priority bands
# --------------------------------------------------------------------------- #


class TestPriorityBands:
    @pytest.mark.parametrize("lower,expected", [
        (100.0, "P1"), (80.0, "P1"), (79.9, "P2"), (65.0, "P2"),
        (64.9, "P3"), (50.0, "P3"), (49.9, "P4"), (0.0, "P4"),
    ])
    def test_band_thresholds(self, lower, expected):
        assert band_for(lower)[0] == expected

    def test_band_uses_the_lower_bound_so_unknowns_cannot_promote(self):
        """A mostly-unknown score must not be promoted by its optimistic end."""
        result = compute_crps({name: unknown() for name in FACTOR_ORDER})
        assert result.crps_100_upper == pytest.approx(100.0)
        assert result.band == "P4", "an all-unknown score must not be Critical"


# --------------------------------------------------------------------------- #
# Evidence strength
# --------------------------------------------------------------------------- #


class TestEvidenceStrength:
    def test_no_evidence_scores_zero(self):
        strength = compute_evidence_strength([], today=TODAY)
        assert strength.value == 0.0
        assert strength.independent_groups == 0

    def test_duplicates_are_not_independent_confirmation(self):
        """The rule that stops ten rows from one page counting as ten sources."""
        rows = [row(evidence_id=f"EXT-{i}", duplicate_of="EXT-aaa") for i in range(9)]
        rows.append(row(evidence_id="EXT-aaa"))
        strength = compute_evidence_strength(rows, today=TODAY)
        assert strength.independent_groups == 1
        assert strength.duplicate_rows_excluded == 9

    def test_same_source_rows_count_once(self):
        same = [row(evidence_id=f"EXT-{i}", independence_group="SRC-same") for i in range(20)]
        spread = [row(evidence_id=f"EXT-{i}", independence_group=f"SRC-{i}") for i in range(4)]
        assert compute_evidence_strength(same, today=TODAY).independent_groups == 1
        assert compute_evidence_strength(spread, today=TODAY).independent_groups == 4

    def test_volume_saturates_so_duplicates_cannot_overwhelm(self):
        """Twenty same-source rows must not beat four independent sources."""
        many_same = [row(evidence_id=f"EXT-{i}", independence_group="SRC-one") for i in range(20)]
        few_independent = [
            row(evidence_id=f"EXT-{i}", independence_group=f"SRC-{i}",
                source_family=family)
            for i, family in enumerate(
                ["independent_test_org", "professional_review", "customer_forum", "youtube_review"]
            )
        ]
        assert (compute_evidence_strength(few_independent, today=TODAY).value
                > compute_evidence_strength(many_same, today=TODAY).value)

    def test_higher_source_quality_scores_higher(self):
        low = [row(source_quality=40, independence_group=f"SRC-{i}") for i in range(3)]
        high = [row(source_quality=95, independence_group=f"SRC-{i}") for i in range(3)]
        assert (compute_evidence_strength(high, today=TODAY).components["source_quality"]
                > compute_evidence_strength(low, today=TODAY).components["source_quality"])

    def test_diversity_rewards_distinct_groups_and_families(self):
        one_family = [row(independence_group=f"SRC-{i}", source_family="customer_forum")
                      for i in range(4)]
        many_families = [
            row(independence_group=f"SRC-{i}", source_family=family)
            for i, family in enumerate(
                ["independent_test_org", "professional_review", "customer_forum", "youtube_review"]
            )
        ]
        assert (compute_evidence_strength(many_families, today=TODAY).components["source_diversity"]
                > compute_evidence_strength(one_family, today=TODAY).components["source_diversity"])

    def test_contradiction_reduces_consistency(self):
        support = [row(independence_group=f"SRC-{i}") for i in range(4)]
        contra = [row(evidence_id="EXT-x", independence_group="SRC-contra")]
        clean = compute_evidence_strength(support, today=TODAY)
        disputed = compute_evidence_strength(support, contra, today=TODAY)
        assert disputed.components["consistency"] < clean.components["consistency"]
        assert disputed.contradicting_groups == 1

    def test_contradiction_does_not_touch_customer_impact(self):
        """Contradiction lowers consistency only - impact is a separate factor."""
        support = [row(independence_group=f"SRC-{i}") for i in range(4)]
        contra = [row(evidence_id="EXT-x", independence_group="SRC-contra")]
        disputed = compute_evidence_strength(support, contra, today=TODAY)
        result = compute_crps(all_factors(
            customer_impact=known(4.0, "unchanged by contradiction"),
            evidence_strength=disputed.as_criterion(),
        ))
        assert result.factors["customer_impact"].lower_value == 4.0

    def test_recency_bands(self):
        recent = [row(published_at="2026-06-01", independence_group="SRC-a")]
        old = [row(published_at="2019-01-01", independence_group="SRC-a")]
        assert compute_evidence_strength(recent, today=TODAY).components["recency"] == 4.0
        assert compute_evidence_strength(old, today=TODAY).components["recency"] == 0.0

    def test_recency_falls_back_to_retrieved_at(self):
        rows = [row(published_at=None, retrieved_at="2026-09-01", independence_group="SRC-a")]
        assert compute_evidence_strength(rows, today=TODAY).components["recency"] == 4.0

    def test_missing_dates_score_zero_recency_not_an_error(self):
        rows = [row(published_at=None, retrieved_at=None, independence_group="SRC-a")]
        strength = compute_evidence_strength(rows, today=TODAY)
        assert strength.components["recency"] == 0.0
        assert strength.newest_evidence_date is None

    def test_components_reproduce_the_value(self):
        rows = [row(independence_group=f"SRC-{i}") for i in range(3)]
        strength = compute_evidence_strength(rows, today=TODAY)
        expected = sum(
            strength.components[name] * weight
            for name, weight in EVIDENCE_STRENGTH_WEIGHTS.items()
        )
        assert strength.value == pytest.approx(expected, abs=1e-4)

    def test_basis_is_always_populated(self):
        rows = [row(independence_group="SRC-a")]
        assert compute_evidence_strength(rows, today=TODAY).basis
        assert compute_evidence_strength([], today=TODAY).basis


# --------------------------------------------------------------------------- #
# Decision confidence
# --------------------------------------------------------------------------- #


class TestDecisionConfidence:
    def test_formula_matches_the_specification(self):
        rows = [row(independence_group=f"SRC-{i}") for i in range(6)]
        strength = compute_evidence_strength(rows, today=TODAY)
        confidence = compute_decision_confidence(strength)
        expected = sum(
            confidence.components[name] * weight
            for name, weight in DECISION_CONFIDENCE_WEIGHTS.items()
        )
        assert confidence.value_0_to_4 == pytest.approx(expected, abs=1e-4)
        assert confidence.value_0_to_100 == pytest.approx(expected / 4 * 100, abs=1e-2)

    def test_confidence_is_separate_from_priority(self):
        """High priority on thin evidence must show high CRPS and low confidence."""
        thin = compute_evidence_strength([row(independence_group="SRC-a", source_quality=50)],
                                         today=TODAY)
        result = compute_crps(all_factors(
            customer_impact=known(4.0), evidence_strength=thin.as_criterion(),
            frequency=known(4.0), market_relevance=known(4.0),
            competitive_gap=known(4.0), future_relevance=known(4.0),
            strategic_fit=known(4.0),
        ))
        confidence = compute_decision_confidence(thin)
        assert result.crps_100_lower > 80, "priority stays high"
        # A single recent uncontradicted source is perfectly "consistent" and
        # recent, so confidence is not near zero - but diversity and volume keep
        # it far below priority, which is the separation that matters.
        assert result.crps_100_lower - confidence.value_0_to_100 > 20
        assert confidence.components["source_diversity"] < 1.0
        assert confidence.components["evidence_strength"] < 2.0

    def test_no_evidence_gives_zero_confidence(self):
        confidence = compute_decision_confidence(compute_evidence_strength([], today=TODAY))
        assert confidence.value_0_to_100 == 0.0


# --------------------------------------------------------------------------- #
# Frequency
# --------------------------------------------------------------------------- #


class TestFrequency:
    def test_unknown_without_a_denominator(self):
        item = compute_frequency()
        assert item.value is None
        assert "denominator" in item.missing_reason

    def test_page_counts_are_not_a_proxy(self):
        """Web evidence volume must never become a frequency number."""
        item = compute_frequency(unique_affected_records=500, unique_eligible_records=None)
        assert item.value is None

    def test_known_with_a_valid_denominator(self):
        item = compute_frequency(unique_affected_records=250, unique_eligible_records=1000,
                                 saturation_share=0.25)
        assert item.value == pytest.approx(4.0)
        assert "1000" in item.basis

    def test_scales_below_saturation(self):
        item = compute_frequency(unique_affected_records=125, unique_eligible_records=1000,
                                 saturation_share=0.25)
        assert item.value == pytest.approx(2.0)

    def test_zero_denominator_is_unknown_not_a_crash(self):
        assert compute_frequency(unique_affected_records=5,
                                 unique_eligible_records=0).value is None

    def test_unknown_frequency_widens_crps(self):
        result = compute_crps(all_factors(frequency=compute_frequency()))
        assert not result.is_point


# --------------------------------------------------------------------------- #
# Market relevance - Germany
# --------------------------------------------------------------------------- #


class TestMarketRelevance:
    def test_direct_germany_evidence_scores_four(self):
        assert compute_market_relevance([row(market="DE")]).value == 4.0

    def test_eu_evidence_scores_three(self):
        assert compute_market_relevance([row(market="EU")]).value == 3.0

    def test_us_evidence_is_not_treated_as_german(self):
        item = compute_market_relevance([row(market="US")])
        assert item.value == 2.0, "US evidence must not score as direct DE evidence"
        assert "not direct" in item.basis

    def test_germany_wins_when_mixed(self):
        assert compute_market_relevance([row(market="US"), row(market="DE")]).value == 4.0

    def test_unknown_market_is_bounded_not_assumed(self):
        item = compute_market_relevance([row(market="unknown")])
        assert item.value is None
        assert (item.lower_value, item.upper_value) == (0.0, 2.0)

    def test_no_evidence_is_unknown(self):
        assert compute_market_relevance([]).value is None

    def test_duplicates_do_not_establish_market(self):
        item = compute_market_relevance([row(market="DE", duplicate_of="EXT-x")])
        assert item.value is None


# --------------------------------------------------------------------------- #
# Competitive gap
# --------------------------------------------------------------------------- #


class TestCompetitiveGap:
    def test_unmatched_dimensions_are_unknown_not_parity(self):
        item, detail = compute_competitive_gap([row(subtopic="charging_speed")], [])
        assert item.value is None
        assert "parity must not be assumed" in item.missing_reason
        assert detail["matched_dimensions"] == []

    def test_matched_dimension_produces_a_bounded_factor(self):
        bmw = [row(subtopic="charging_speed", brand="BMW")]
        competitor = [row(subtopic="charging_speed", brand="Porsche",
                          independence_group="SRC-p", evidence_id="EXT-p")]
        item, detail = compute_competitive_gap(bmw, competitor)
        assert item.value is None, "direction needs human reading, so bounded"
        assert item.lower_value is not None and item.upper_value is not None
        assert detail["matched_dimensions"] == ["charging_speed"]
        assert "porsche" in detail["competitor_brands"]

    def test_detail_reports_missing_coverage(self):
        bmw = [row(subtopic="charging_speed"), row(subtopic="cabin_noise")]
        competitor = [row(subtopic="charging_speed", brand="Tesla",
                          independence_group="SRC-t", evidence_id="EXT-t")]
        _, detail = compute_competitive_gap(bmw, competitor)
        assert "cabin_noise" in detail["bmw_only_dimensions"]
        assert detail["missing"], "a single competitor brand should be flagged"

    def test_conclusions_are_not_hardcoded(self):
        """No competitor verdict appears without matched evidence."""
        item, _ = compute_competitive_gap([], [])
        assert item.value is None


# --------------------------------------------------------------------------- #
# Future relevance and strategic fit
# --------------------------------------------------------------------------- #


class TestFutureRelevance:
    def test_no_trend_evidence_is_unknown(self):
        item = compute_future_relevance([row(topic="charging", subtopic="charging_speed")])
        assert item.value is None
        assert "not inferred" in item.missing_reason

    def test_trend_evidence_scores(self):
        rows = [
            row(topic="market_trend", subtopic="infrastructure_growth",
                independence_group=f"SRC-{i}", evidence_id=f"EXT-{i}")
            for i in range(4)
        ]
        assert compute_future_relevance(rows).value == pytest.approx(4.0)

    def test_duplicates_do_not_inflate_future_relevance(self):
        rows = [
            row(topic="market_trend", independence_group="SRC-same",
                evidence_id=f"EXT-{i}", duplicate_of="EXT-0" if i else None)
            for i in range(8)
        ]
        assert compute_future_relevance(rows).value == pytest.approx(1.0)


class TestStrategicFit:
    def test_unknown_without_objectives_or_pm_input(self):
        item = compute_strategic_fit()
        assert item.value is None
        assert "not inferred" in item.missing_reason

    def test_pm_input_requires_a_basis(self):
        with pytest.raises(ValueError, match="explicit basis"):
            compute_strategic_fit(pm_value=3.0)

    def test_pm_input_with_basis_is_accepted(self):
        item = compute_strategic_fit(pm_value=3.0, pm_basis="aligned with 2030 EV objective")
        assert item.value == 3.0
        assert "PM input" in item.basis

    def test_approved_objectives_give_a_bounded_value(self):
        item = compute_strategic_fit(approved_objectives=["Electrify the core range"])
        assert item.value is None
        assert (item.lower_value, item.upper_value) == (1.0, 3.0)


# --------------------------------------------------------------------------- #
# Conservative ranking
# --------------------------------------------------------------------------- #


class TestRanking:
    def test_non_overlapping_intervals_are_ordered(self):
        high = compute_crps({n: known(4.0) for n in FACTOR_ORDER})
        low = compute_crps({n: known(0.0) for n in FACTOR_ORDER})
        ranked, summary = rank_requirements({"REQ-high": high, "REQ-low": low})
        assert [item.requirement_id for item in ranked] == ["REQ-high", "REQ-low"]
        assert all(item.rank is not None for item in ranked)
        assert summary["unresolved"] == 0

    def test_overlapping_intervals_are_unresolved(self):
        a = compute_crps(all_factors(frequency=unknown()))
        b = compute_crps(all_factors(strategic_fit=unknown()))
        ranked, summary = rank_requirements({"REQ-a": a, "REQ-b": b})
        assert all(item.rank is None for item in ranked)
        assert summary["unresolved"] == 2
        # REQ-b loses only the 0.05 strategic-fit weight to its unknown, so it
        # sorts first on lower bound; each is unresolved against the other.
        assert [item.requirement_id for item in ranked] == ["REQ-b", "REQ-a"]
        assert ranked[0].unresolved_against == ["REQ-a"]
        assert ranked[1].unresolved_against == ["REQ-b"]

    def test_no_false_ordinal_certainty(self):
        wide = compute_crps({n: unknown() for n in FACTOR_ORDER})
        narrow = compute_crps({n: known(2.0) for n in FACTOR_ORDER})
        ranked, _ = rank_requirements({"REQ-wide": wide, "REQ-narrow": narrow})
        assert all(item.rank is None for item in ranked)

    def test_ranking_is_deterministic(self):
        scored = {
            "REQ-b": compute_crps({n: known(4.0) for n in FACTOR_ORDER}),
            "REQ-a": compute_crps({n: known(4.0) for n in FACTOR_ORDER}),
        }
        first = [i.requirement_id for i in rank_requirements(scored)[0]]
        second = [i.requirement_id for i in rank_requirements(scored)[0]]
        assert first == second == ["REQ-a", "REQ-b"]


# --------------------------------------------------------------------------- #
# Dimension intervals
# --------------------------------------------------------------------------- #


class TestDimensionIntervals:
    def test_customer_and_business_dimensions_are_reported(self):
        result = compute_crps(all_factors())
        assert set(result.dimension_intervals) == {"customer", "business"}

    def test_missing_criteria_are_named_per_dimension(self):
        result = compute_crps(all_factors(strategic_fit=unknown()))
        assert "strategic_fit" in result.dimension_intervals["business"].missing_criteria
        assert result.dimension_intervals["customer"].missing_criteria == []

    def test_dimension_bounds_stay_in_range(self):
        result = compute_crps({n: unknown() for n in FACTOR_ORDER})
        for interval in result.dimension_intervals.values():
            assert 0.0 <= interval.lower_bound <= 100.0
            assert 0.0 <= interval.upper_bound <= 100.0
