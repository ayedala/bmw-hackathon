"""Rehearse an explicitly illustrative PM decision in an isolated database copy.

No API calls, gold labels or real BMW approvals are generated.
"""
from pathlib import Path
import argparse
import sqlite3

from bmw_pm.contracts import DecisionAction, PriorityPolicy
from bmw_pm.decision.planning import PriorityService, decision_brief, load_proposals, proposal_for
from bmw_pm.review import ReviewService
from bmw_pm.storage import Database


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="data/processed/bmw_pm.db")
    parser.add_argument("--output", default="data/processed/successor-demo.db")
    args = parser.parse_args()
    source, output = Path(args.source).resolve(), Path(args.output).resolve()
    if not source.is_file():
        parser.error("Source database is absent. Ingest the authorized files first.")
    if output.exists() or output == source:
        parser.error("Choose a new output path; the demonstration never overwrites a database.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as original:
        with sqlite3.connect(output) as copied:
            original.backup(copied)
    database = Database(output)
    database.initialize()
    proposals = load_proposals("configs/successor_proposals_v1.json")
    selected = next((item for item in database.requirement_summaries()
        if (proposal := proposal_for(database, item["requirement"], proposals)) and proposal.domain == "controls_usability"), None)
    if not selected:
        parser.error("The demonstration needs a US G60 controls card.")
    requirement = selected["requirement"]
    proposal = proposal_for(database, requirement, proposals)
    review = ReviewService(database)
    actor = "illustrative-scripted-pm-not-bmw-approval"
    _, revised = review.edit(requirement_id=requirement.requirement_id, expected_revision=requirement.revision,
        changes={"title":proposal.title, "customer_outcome":proposal.outcome,
            "assumptions":[*requirement.assumptions, proposal.future_assumption, "Illustrative scripted PM walkthrough, not an actual BMW approval."],
            "acceptance_proposal":{"method":proposal.validation}, "target_status":"proposed_target"},
        rationale="Illustrative PM challenge: distinguish difficult access from missing functionality. Compare persistent controls and voice discoverability before choosing hardware.",
        actor_id=actor, request_id="successor-demo-edit")
    priorities = PriorityService(database)
    first = priorities.save(requirement_id=revised.requirement_id, expected_revision=revised.revision,
        expected_sequence=0, factors=proposal.factors, policy=PriorityPolicy(), actor_id=actor,
        rationale="Illustrative starting judgement: high everyday impact, traceable but unreviewed evidence, material usability gaps.", request_id="successor-demo-priority-1")
    second = priorities.save(requirement_id=revised.requirement_id, expected_revision=revised.revision,
        expected_sequence=1, factors=proposal.factors.model_copy(update={"uncertainty":3}), policy=PriorityPolicy(), actor_id=actor,
        rationale="Illustrative PM challenge: existing voice capability may address part of the issue, so increase uncertainty until first-time-user testing.", request_id="successor-demo-priority-2")
    decision = review.decide(requirement_id=revised.requirement_id, expected_revision=revised.revision,
        action=DecisionAction.APPROVE, rationale="ILLUSTRATIVE SCRIPTED APPROVAL: approve the customer outcome for concept testing only, conditional on a US task baseline; no hardware commitment or BMW sign-off.",
        actor_id=actor, request_id="successor-demo-approve")
    assert decision.priority_assessment_id == second.assessment_id
    assert database.replay_requirement(revised.requirement_id)["audit_valid"]
    report = output.with_suffix(".md")
    report.write_text("# Illustrative scripted PM walkthrough — not BMW approval\n\n"
        f"Original database preserved. Controls priority changed {first.score} → {second.score} after a declared uncertainty challenge.\n\n"
        + decision_brief(database, [next(i for i in database.requirement_summaries() if i["requirement"].requirement_id == revised.requirement_id)], proposals, PriorityPolicy()), encoding="utf-8")
    print(f"Illustrative demo database: {output}\nPrivate walkthrough report: {report}\nAudit chain valid; original database untouched.")


if __name__ == "__main__":
    main()
