"""Deterministic checks before treating exploratory cards as commitments."""
from ..contracts import DecisionReadiness, PolicyVersion, RequirementRevision, ScoreSnapshot


def assess_readiness(requirement: RequirementRevision, score: ScoreSnapshot | None,
                     policy: PolicyVersion) -> DecisionReadiness:
    blockers = []
    if not policy.approved:
        blockers.append("Prioritization policy has not been approved by the PM.")
    support = [link for link in requirement.evidence_links if link.role == "supports"]
    if not support or any(link.semantic_entailment != "reviewed_supports" for link in support):
        blockers.append("Supporting claims need human entailment review.")
    if requirement.processed_feedback_records < requirement.denominator_feedback_records:
        blockers.append("Feedback processing is incomplete in the selected scope.")
    if requirement.feasibility not in {"conditional", "feasible_reviewed"}:
        blockers.append("Feasibility needs a documented review or conditional acceptance.")
    if score is None or score.requirement_revision != requirement.revision:
        blockers.append("Current revision has no matching score; reassess edited content.")
    else:
        if (score.policy_id, score.policy_revision) != (policy.policy_id, policy.revision):
            blockers.append("Score belongs to a different policy version.")
        missing = [key for key, value in score.criterion_inputs.items()
                   if value.value is None and value.lower_value is None]
        if missing:
            blockers.append("Missing value criteria: " + ", ".join(sorted(missing)))
    return DecisionReadiness(requirement_id=requirement.requirement_id,
                             ready_for_commitment=not blockers, blockers=blockers)
