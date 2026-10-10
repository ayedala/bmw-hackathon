from __future__ import annotations

from typing import Mapping, Sequence

from ..contracts import (
    CriterionInput,
    DimensionInterval,
    PolicyVersion,
    RequirementRevision,
    ScoreSnapshot,
)
from ..utils import canonical_json, stable_id


def reach_input(
    *,
    support_count: int,
    eligible_count: int,
    processed_count: int,
    saturation_share: float,
) -> CriterionInput:
    if min(support_count, eligible_count, processed_count) < 0:
        raise ValueError("reach counts cannot be negative")
    if support_count > processed_count or processed_count > eligible_count:
        raise ValueError("reach counts must satisfy support <= processed <= eligible")
    if not 0 < saturation_share <= 1:
        raise ValueError("saturation_share must be in (0,1]")
    if eligible_count == 0:
        return CriterionInput(
            missing_reason="No eligible feedback records exist in the selected scope."
        )
    unprocessed = eligible_count - processed_count
    lower_share = support_count / eligible_count
    upper_share = (support_count + unprocessed) / eligible_count
    lower = round(4 * min(lower_share / saturation_share, 1), 12)
    upper = round(4 * min(upper_share / saturation_share, 1), 12)
    basis = (
        f"{support_count} unique supporting feedback IDs / {eligible_count} eligible IDs; "
        f"{processed_count} IDs processed; saturation_share={saturation_share:.6g}. "
        "This is collected-corpus recurrence, not customer prevalence."
    )
    if abs(lower - upper) < 1e-12:
        return CriterionInput(value=lower, basis=basis)
    return CriterionInput(lower_value=lower, upper_value=upper, basis=basis)


def score_requirement(
    *,
    requirement: RequirementRevision,
    policy: PolicyVersion,
    criterion_inputs: Mapping[str, CriterionInput],
    profile_id: str,
    profile_revision: int,
    corpus_manifest_hash: str,
    run_id: str,
    extra_assumptions: Sequence[str] = (),
) -> ScoreSnapshot:
    expected = set(policy.criteria)
    actual = set(criterion_inputs)
    if expected != actual:
        raise ValueError(
            f"criterion inputs must exactly match policy criteria; missing={expected-actual}, extra={actual-expected}"
        )
    contributions: dict[str, tuple[float, float]] = {}
    lower_total = 0.0
    upper_total = 0.0
    for name, definition in policy.criteria.items():
        item = criterion_inputs[name]
        if item.value is not None:
            lower_value = upper_value = item.value
        elif item.lower_value is not None and item.upper_value is not None:
            lower_value, upper_value = item.lower_value, item.upper_value
        else:
            lower_value, upper_value = 0.0, 4.0
        lower_contribution = 100 * definition.weight * lower_value / 4
        upper_contribution = 100 * definition.weight * upper_value / 4
        contributions[name] = (round(lower_contribution, 8), round(upper_contribution, 8))
        lower_total += lower_contribution
        upper_total += upper_contribution
    dimension_intervals: dict[str, DimensionInterval] = {}
    for dimension in ("customer", "business"):
        names = [
            name for name, definition in policy.criteria.items()
            if definition.dimension == dimension
        ]
        dimension_weight = sum(policy.criteria[name].weight for name in names)
        dimension_intervals[dimension] = DimensionInterval(
            lower_bound=round(sum(contributions[name][0] for name in names) / dimension_weight, 8),
            upper_bound=round(sum(contributions[name][1] for name in names) / dimension_weight, 8),
            criteria=names,
            missing_criteria=[
                name for name in names
                if criterion_inputs[name].value is None
                and criterion_inputs[name].lower_value is None
            ],
            interpretation=(
                "Policy-dependent 0–100 scenario bounds within this dimension; "
                "not a probability or measured product outcome."
            ),
        )
    identity_payload = canonical_json(
        {
            "requirement_id": requirement.requirement_id,
            "revision": requirement.revision,
            "policy_id": policy.policy_id,
            "policy_revision": policy.revision,
            "profile_id": profile_id,
            "profile_revision": profile_revision,
            "corpus_manifest_hash": corpus_manifest_hash,
            "run_id": run_id,
            "criterion_inputs": {
                key: value.model_dump(mode="json") for key, value in criterion_inputs.items()
            },
        }
    )
    return ScoreSnapshot(
        score_snapshot_id=stable_id("score", identity_payload),
        requirement_id=requirement.requirement_id,
        requirement_revision=requirement.revision,
        policy_id=policy.policy_id,
        policy_revision=policy.revision,
        profile_id=profile_id,
        profile_revision=profile_revision,
        corpus_manifest_hash=corpus_manifest_hash,
        criterion_inputs=dict(criterion_inputs),
        contributions=contributions,
        dimension_intervals=dimension_intervals,
        lower_bound=round(lower_total, 8),
        upper_bound=round(upper_total, 8),
        scope=requirement.scope,
        coverage={
            "eligible_feedback_records": requirement.denominator_feedback_records,
            "processed_feedback_records": requirement.processed_feedback_records,
            "supporting_unique_feedback_records": requirement.support_count,
            "praise_or_preservation_unique_feedback_records": requirement.counter_count,
            "unit": "unique feedback ID within one supplied source file",
        },
        feasibility_status=requirement.feasibility,
        feasibility_basis=(
            "No reviewed engineering constraints, effort, or cost were supplied. "
            "Customer comments and competitor features cannot certify feasibility."
            if requirement.feasibility == "unknown"
            else "Reviewed feasibility evidence must be inspected on the requirement revision."
        ),
        assumptions=[
            policy.elicitation_record,
            "Additive criterion independence has not been validated.",
            *extra_assumptions,
        ],
        run_id=run_id,
    )


def rank_scores(scores: Sequence[ScoreSnapshot]) -> list[ScoreSnapshot]:
    """Conservative exploratory order; overlapping intervals remain visible."""
    return sorted(scores, key=lambda item: (-item.lower_bound, item.requirement_id))


def assess_ranking(scores: Sequence[ScoreSnapshot]) -> dict[str, object]:
    """Count comparisons resolved by non-overlapping value bounds only."""
    ordered = rank_scores(scores)
    resolved: list[tuple[str, str]] = []
    unresolved: list[tuple[str, str]] = []
    for index, left in enumerate(ordered):
        for right in ordered[index + 1:]:
            if left.lower_bound > right.upper_bound:
                resolved.append((left.requirement_id, right.requirement_id))
            elif right.lower_bound > left.upper_bound:
                resolved.append((right.requirement_id, left.requirement_id))
            else:
                unresolved.append((left.requirement_id, right.requirement_id))
    return {
        "display_order": [score.requirement_id for score in ordered],
        "ordering_rule": "Descending lower bound, then stable requirement ID; exploratory only.",
        "resolved_value_pairs": resolved,
        "unresolved_value_pairs": unresolved,
        "feasibility_gate": "Review required separately; no feasibility value is inferred.",
    }
