from __future__ import annotations

import pytest
from pydantic import ValidationError

from bmw_pm.mocktest import MockTestInput, run_mocktest


def _input(text: str, *, model: str = "G60", country: str = "US", powertrain: str = "ICE") -> MockTestInput:
    return MockTestInput(
        model_code=model, country=country, powertrain=powertrain, feedback_text=text
    )


def test_complaint_makes_review_candidate_with_exact_mock_evidence() -> None:
    text = "The climate control menu is hard to use while driving."
    result = run_mocktest(_input(text))

    assert result.status == "candidate_for_review"
    assert result.provider_mode == "baseline_no_ai"
    assert len(result.signals) == len(result.candidates) == 1
    signal = result.signals[0]
    span = signal.evidence_spans[0]
    assert text[span.start:span.end] == span.text
    assert span.locator.exact_quote == span.text
    assert signal.provider_mode == "baseline_no_ai"
    candidate = result.candidates[0]
    assert candidate.support_count == 1
    assert candidate.evidence_links[0].exact_span_checked
    assert candidate.feasibility == "unknown"


@pytest.mark.parametrize(
    ("text", "expected_status", "expected_signals"),
    [
        ("The seats are comfortable and the cabin is quiet.", "no_update_proposed", 2),
        ("I collected my car on Tuesday.", "no_keyword_match", 0),
        ("Charging is slow on cold journeys.", "no_keyword_match", 0),
    ],
)
def test_non_supporting_statement_does_not_create_update(
    text: str, expected_status: str, expected_signals: int
) -> None:
    result = run_mocktest(_input(text))
    assert result.status == expected_status
    assert len(result.signals) == expected_signals
    assert result.candidates == []


def test_scope_and_input_validation() -> None:
    with pytest.raises(ValueError, match="outside the G60 profile"):
        run_mocktest(_input("The climate control menu is hard.", country="GB"))
    with pytest.raises(ValueError, match="outside the F70 profile"):
        run_mocktest(_input("The climate control menu is hard.", model="F70", powertrain="BEV"))
    with pytest.raises(ValidationError):
        _input("  ")
