"""Tests for deterministic requirement quality validation.

The validator exists to catch requirements that are badly formed rather than
badly governed, so the tests are mostly negative controls: each check is given
a requirement that should trip it and one that should not. A check that cannot
fail is worthless, so every check here is exercised in both directions.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bmw_pm.decision.requirement_quality import (
    QualityReport,
    validate_all,
    validate_requirement_quality,
)

PROCESSED = (
    Path(__file__).resolve().parents[1]
    / "src" / "bmw_pm" / "data_pipeline" / "web_research" / "data" / "processed"
)


def _load(name: str) -> list[dict]:
    path = PROCESSED / name
    if not path.exists():  # pragma: no cover - artifacts are tracked
        pytest.skip(f"artifact {name} not present")
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


# --------------------------------------------------------------------------- #
# Builders
# --------------------------------------------------------------------------- #

def make_requirement(**overrides) -> dict:
    """A requirement that passes every check, so one override isolates one check."""
    base = {
        "requirement_id": "REQ-TEST-001",
        "title": "Frequent functions operable without looking away",
        "requirement": (
            "The vehicle shall allow a seated driver to adjust cabin temperature and "
            "audio volume without looking away from the road."
        ),
        "need_ids": ["NEED-TEST-001"],
        "finding_ids": ["FND-TEST-001"],
        "evidence_ids": ["EXT-test0001"],
        "confidence": "high",
        "assumptions": ["Physical control space remains available on the centre console."],
        "missing_evidence": [],
        "validation_method": "Seated reach-and-actuate study with eyes-on-road measurement.",
        "status": "drafted",
    }
    base.update(overrides)
    return base


def make_need(**overrides) -> dict:
    base = {
        "need_id": "NEED-TEST-001",
        "statement": "I want to change temperature without taking my eyes off the road.",
        "target_market": "DE",
        "finding_ids": ["FND-TEST-001"],
        "evidence_ids": ["EXT-test0001"],
    }
    base.update(overrides)
    return base


def make_finding(**overrides) -> dict:
    base = {
        "finding_id": "FND-TEST-001",
        "title": "Touch-only climate control draws attention from the road",
        "markets_covered": ["DE"],
        "vehicles_covered": ["BMW 5 Series G60"],
        "evidence_ids": ["EXT-test0001"],
    }
    base.update(overrides)
    return base


def make_evidence(**overrides) -> dict:
    base = {
        "evidence_id": "EXT-test0001",
        "claim": "Adjusting climate requires two taps through the touchscreen menu.",
        "evidence_text": "Die Klimasteuerung erfordert zwei Antippen im Menu.",
        "numeric_value": None,
    }
    base.update(overrides)
    return base


def validate(requirement, *, needs=None, findings=None, evidence=None, **kwargs) -> QualityReport:
    return validate_requirement_quality(
        requirement,
        make_need() if needs is None else needs,
        [make_finding()] if findings is None else findings,
        [make_evidence()] if evidence is None else evidence,
        **kwargs,
    )


def check(report: QualityReport, check_id: str):
    matches = [c for c in report.checks if c.check_id == check_id]
    assert matches, f"no check {check_id!r} in {[c.check_id for c in report.checks]}"
    return matches[0]


# --------------------------------------------------------------------------- #

class TestBaseline:
    def test_well_formed_requirement_passes_everything(self):
        report = validate(make_requirement())
        assert report.passed
        assert report.blockers == []
        assert report.warnings == []

    def test_every_check_reports_a_detail(self):
        for c in validate(make_requirement()).checks:
            assert c.detail.strip(), f"{c.check_id} gave no reason"

    def test_check_ids_are_unique(self):
        ids = [c.check_id for c in validate(make_requirement()).checks]
        assert len(ids) == len(set(ids))

    def test_passed_is_driven_by_blockers_not_warnings(self):
        report = validate(make_requirement(assumptions=[], missing_evidence=[]))
        assert report.warnings, "expected a warning to fire"
        assert report.passed, "warnings must not block"


class TestTraceability:
    def test_missing_need_blocks(self):
        report = validate(make_requirement(), needs=[])
        assert not report.passed
        assert check(report, "need_linked").is_blocker

    def test_missing_finding_blocks(self):
        report = validate(make_requirement(), findings=[])
        assert check(report, "finding_linked").is_blocker

    def test_missing_evidence_blocks(self):
        report = validate(make_requirement(), evidence=[])
        assert check(report, "evidence_linked").is_blocker

    def test_single_need_mapping_is_accepted(self):
        """A bare mapping is normalised, so callers need not wrap it."""
        report = validate_requirement_quality(
            make_requirement(), make_need(), [make_finding()], [make_evidence()]
        )
        assert check(report, "need_linked").passed

    def test_none_need_is_treated_as_absent(self):
        report = validate_requirement_quality(
            make_requirement(), None, [make_finding()], [make_evidence()]
        )
        assert check(report, "need_linked").is_blocker


class TestCustomerFacing:
    def test_abstract_requirement_blocks(self):
        report = validate(make_requirement(
            title="Platform alignment",
            requirement="The programme shall align with the module strategy.",
        ))
        assert check(report, "customer_facing").is_blocker

    def test_implementation_prescription_warns(self):
        report = validate(make_requirement(
            requirement="The vehicle shall give the driver an 800 V charging architecture.",
        ))
        assert check(report, "no_implementation_prescription").is_warning

    def test_outcome_phrasing_does_not_warn(self):
        report = validate(make_requirement(
            requirement=(
                "The vehicle shall let the driver add enough range in one stop to "
                "continue without planning a second stop."
            ),
        ))
        assert check(report, "no_implementation_prescription").passed


class TestSingleOutcome:
    def test_two_shall_clauses_warn(self):
        report = validate(make_requirement(
            requirement=(
                "The vehicle shall keep audio volume on a physical control. "
                "The vehicle shall also shorten the navigation entry flow."
            ),
        ))
        assert check(report, "single_outcome").is_warning

    def test_one_shall_clause_passes(self):
        assert check(validate(make_requirement()), "single_outcome").passed


class TestRegulationAndBusinessCase:
    def test_bare_compliance_restatement_warns(self):
        report = validate(make_requirement(
            title="Type approval",
            requirement="The programme shall obtain type approval under Regulation (EU) 2019/2144.",
        ))
        assert check(report, "not_regulation_only").is_warning

    def test_compliance_with_a_customer_outcome_passes(self):
        report = validate(make_requirement(
            requirement=(
                "The vehicle shall comply with the applicable lighting regulation while "
                "keeping the driver's forward view unobstructed."
            ),
        ))
        assert check(report, "not_regulation_only").passed

    def test_pure_business_case_warns(self):
        report = validate(make_requirement(
            title="Residual value",
            requirement="The programme shall improve residual value and leasing rate positioning.",
        ))
        assert check(report, "not_business_case_only").is_warning


class TestNumericTargets:
    def test_number_absent_from_evidence_blocks(self):
        report = validate(make_requirement(
            requirement="The vehicle shall complete a charging stop in 17.5 minutes.",
        ))
        assert check(report, "numeric_targets_sourced").is_blocker
        assert "17.5" in check(report, "numeric_targets_sourced").detail

    def test_number_present_in_evidence_claim_passes(self):
        report = validate(
            make_requirement(
                requirement="The vehicle shall complete a charging stop in 17.5 minutes.",
            ),
            evidence=[make_evidence(claim="The stop took 17.5 minutes on a 300 kW charger.")],
        )
        assert check(report, "numeric_targets_sourced").passed

    def test_number_present_only_as_numeric_value_passes(self):
        report = validate(
            make_requirement(requirement="The vehicle shall sustain 270 kW for the driver."),
            evidence=[make_evidence(claim="Peak power held steady.", numeric_value=270.0)],
        )
        assert check(report, "numeric_targets_sourced").passed

    def test_comma_decimal_in_source_matches_point_decimal_in_requirement(self):
        """German sources write 17,5; the requirement writes 17.5. Same number."""
        report = validate(
            make_requirement(
                requirement="The vehicle shall complete the stop in 17.5 minutes for the driver.",
            ),
            evidence=[make_evidence(claim="Der Stopp dauerte 17,5 Minuten.")],
        )
        assert check(report, "numeric_targets_sourced").passed

    def test_state_of_charge_window_is_allowed_and_reported(self):
        report = validate(make_requirement(
            requirement=(
                "The vehicle shall sustain charging power so a 10-80 percent stop is "
                "predictable for the driver."
            ),
        ))
        result = check(report, "numeric_targets_sourced")
        assert result.passed
        assert "convention" in result.detail

    def test_no_numbers_passes_quietly(self):
        result = check(validate(make_requirement()), "numeric_targets_sourced")
        assert result.passed
        assert "convention" not in result.detail


class TestDuplicates:
    def test_near_identical_requirement_warns(self):
        peer = make_requirement(requirement_id="REQ-TEST-002")
        report = validate(make_requirement(), peer_requirements=[make_requirement(), peer])
        result = check(report, "not_duplicate")
        assert result.is_warning
        assert "REQ-TEST-002" in result.detail

    def test_self_is_not_a_duplicate_of_itself(self):
        own = make_requirement()
        assert check(validate(own, peer_requirements=[own]), "not_duplicate").passed

    def test_distinct_requirement_does_not_warn(self):
        peer = make_requirement(
            requirement_id="REQ-TEST-003",
            title="Charging communicated as usable range",
            requirement="The vehicle shall present charging progress as range gained for the stop.",
        )
        report = validate(make_requirement(), peer_requirements=[make_requirement(), peer])
        assert check(report, "not_duplicate").passed


class TestScope:
    def test_vehicle_scope_from_finding_satisfies_the_check(self):
        assert check(validate(make_requirement()), "vehicle_scope_explicit").passed

    def test_no_vehicle_anywhere_warns(self):
        report = validate(make_requirement(), findings=[make_finding(vehicles_covered=[])])
        assert check(report, "vehicle_scope_explicit").is_warning

    def test_unknown_vehicle_does_not_count_as_scope(self):
        report = validate(make_requirement(), findings=[make_finding(vehicles_covered=["unknown"])])
        assert check(report, "vehicle_scope_explicit").is_warning

    def test_explicit_vehicle_scope_field_is_honoured(self):
        report = validate(
            make_requirement(vehicle_scope="BMW 5 Series G60 successor"),
            findings=[make_finding(vehicles_covered=[])],
        )
        assert check(report, "vehicle_scope_explicit").passed

    def test_market_scope_missing_warns(self):
        report = validate(
            make_requirement(),
            needs=[make_need(target_market="")],
            findings=[make_finding(markets_covered=[])],
        )
        assert check(report, "market_scope_explicit").is_warning

    def test_planning_market_absent_warns_even_when_other_markets_known(self):
        report = validate(
            make_requirement(),
            needs=[make_need(target_market="US")],
            findings=[make_finding(markets_covered=["US"])],
            primary_market="DE",
        )
        assert check(report, "market_scope_explicit").passed
        result = check(report, "primary_market_covered")
        assert result.is_warning
        assert "DE" in result.detail

    def test_planning_market_check_follows_the_configured_market(self):
        report = validate(
            make_requirement(),
            needs=[make_need(target_market="US")],
            findings=[make_finding(markets_covered=["US"])],
            primary_market="US",
        )
        assert check(report, "primary_market_covered").passed

    def test_market_matching_is_case_insensitive(self):
        report = validate(
            make_requirement(),
            needs=[make_need(target_market="de")],
            findings=[make_finding(markets_covered=["de"])],
        )
        assert check(report, "primary_market_covered").passed


class TestAssumptionsAndConfidence:
    def test_no_assumptions_or_gaps_warns(self):
        report = validate(make_requirement(assumptions=[], missing_evidence=[]))
        assert check(report, "assumptions_explicit").is_warning

    def test_declared_gap_alone_satisfies_the_check(self):
        report = validate(make_requirement(
            assumptions=[], missing_evidence=["No DE-specific reach study available."],
        ))
        assert check(report, "assumptions_explicit").passed

    def test_missing_confidence_blocks(self):
        report = validate(make_requirement(confidence=""))
        assert check(report, "confidence_assigned").is_blocker


class TestFeasibility:
    def test_inferring_feasibility_from_customer_evidence_blocks(self):
        report = validate(make_requirement(
            requirement=(
                "The vehicle shall give the driver faster charging; this is technically "
                "straightforward."
            ),
        ))
        assert check(report, "feasibility_not_inferred").is_blocker

    def test_absent_feasibility_is_not_a_failure(self):
        """Feasibility is engineering's to record, so silence is correct here."""
        assert check(validate(make_requirement()), "feasibility_not_inferred").passed

    @pytest.mark.parametrize("state", ["unknown", "conditional", "feasible_reviewed"])
    def test_recognised_feasibility_states_pass(self, state):
        report = validate(make_requirement(feasibility=state))
        assert check(report, "feasibility_not_inferred").passed

    def test_unrecognised_feasibility_state_blocks(self):
        report = validate(make_requirement(feasibility="definitely_fine"))
        assert check(report, "feasibility_not_inferred").is_blocker


class TestAcceptanceHonesty:
    def test_claiming_validation_already_happened_blocks(self):
        report = validate(make_requirement(
            validation_method="Approved target, signed off by engineering.",
        ))
        assert check(report, "acceptance_not_overclaimed").is_blocker

    def test_proposed_validation_passes(self):
        assert check(validate(make_requirement()), "acceptance_not_overclaimed").passed

    def test_absent_validation_method_warns(self):
        report = validate(make_requirement(validation_method=""))
        assert check(report, "validation_method_present").is_warning


class TestSerialisation:
    def test_as_dict_round_trips_the_shape_the_ui_needs(self):
        payload = validate(make_requirement(confidence="", assumptions=[])).as_dict()
        assert payload["requirement_id"] == "REQ-TEST-001"
        assert payload["passed"] is False
        assert any(b["check_id"] == "confidence_assigned" for b in payload["blockers"])
        assert any(w["check_id"] == "assumptions_explicit" for w in payload["warnings"])
        assert len(payload["checks"]) == len(validate(make_requirement()).checks)

    def test_as_dict_is_json_serialisable(self):
        json.dumps(validate(make_requirement()).as_dict())


class TestValidateAll:
    def test_resolves_chains_from_id_maps(self):
        reports = validate_all(
            [make_requirement()],
            {"NEED-TEST-001": make_need()},
            {"FND-TEST-001": make_finding()},
            {"EXT-test0001": make_evidence()},
        )
        assert len(reports) == 1
        assert reports[0].passed

    def test_dangling_ids_are_dropped_not_invented(self):
        """A missing id must surface as absent traceability, never be fabricated."""
        reports = validate_all([make_requirement()], {}, {}, {})
        assert not reports[0].passed
        assert {c.check_id for c in reports[0].blockers} >= {
            "need_linked", "finding_linked", "evidence_linked",
        }

    def test_peer_requirements_are_passed_through_for_duplicate_detection(self):
        requirements = [make_requirement(), make_requirement(requirement_id="REQ-TEST-002")]
        reports = validate_all(
            requirements,
            {"NEED-TEST-001": make_need()},
            {"FND-TEST-001": make_finding()},
            {"EXT-test0001": make_evidence()},
        )
        assert all(check(r, "not_duplicate").is_warning for r in reports)


class TestRealArtifacts:
    """The validator must hold against the actual canonical chain, not only fixtures."""

    def test_every_shipped_requirement_passes_validation(self):
        requirements = _load("requirements.jsonl")
        reports = validate_all(
            requirements,
            {r["need_id"]: r for r in _load("customer_needs.jsonl")},
            {r["finding_id"]: r for r in _load("findings.jsonl")},
            {r["evidence_id"]: r for r in _load("external_evidence.jsonl")},
            primary_market="DE",
        )
        assert len(reports) == len(requirements)
        failures = {r.requirement_id: [b.detail for b in r.blockers] for r in reports if not r.passed}
        assert not failures, f"shipped requirements have quality blockers: {failures}"

    def test_shipped_requirements_all_reach_german_evidence(self):
        reports = validate_all(
            _load("requirements.jsonl"),
            {r["need_id"]: r for r in _load("customer_needs.jsonl")},
            {r["finding_id"]: r for r in _load("findings.jsonl")},
            {r["evidence_id"]: r for r in _load("external_evidence.jsonl")},
            primary_market="DE",
        )
        missing = [r.requirement_id for r in reports
                   if not check(r, "primary_market_covered").passed]
        assert not missing, f"no DE evidence reaches: {missing}"
