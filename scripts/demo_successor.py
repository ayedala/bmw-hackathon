"""Copy real evidence and generate drafts. Decisions require explicit reviewer flags."""
import argparse
from pathlib import Path
import sqlite3
from uuid import uuid4
from bmw_pm.storage import Database
from bmw_pm.contracts import DecisionAction
from bmw_pm.decision.planning import load_proposals, priority_score, PriorityService, decision_brief
from bmw_pm.decision.drafts import ROOT, generate_draft, adopt_draft
from bmw_pm.review import ReviewService
from bmw_pm.validation import validate_database


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",default="data/processed/bmw_pm.db")
    parser.add_argument("--output",default="data/processed/draft-demo.db")
    parser.add_argument("--decision",choices=["approve","reject","defer"])
    parser.add_argument("--reviewer")
    parser.add_argument("--rationale")
    parser.add_argument("--domain",default="controls_usability")
    parser.add_argument("--confirm-priority",action="store_true")
    parser.add_argument("--acknowledge-uncertainty",action="store_true")
    args=parser.parse_args()
    if args.decision == "approve" and not args.acknowledge_uncertainty:
        parser.error("Approval requires --acknowledge-uncertainty after reviewing unresolved evidence and policy limits.")
    if args.decision and (not args.reviewer or not args.rationale or not args.reviewer.strip() or not args.rationale.strip()):
        parser.error("A decision requires explicit --reviewer and --rationale; there is no automatic approval.")
    if args.confirm_priority and not args.decision:
        parser.error("--confirm-priority requires an explicit reviewer decision in this demo.")
    source,output=Path(args.source),Path(args.output)
    if not source.is_file():
        parser.error("Source database is missing; supply authorized real data.")
    if output.exists():
        parser.error("Output already exists; choose a new path. Existing decisions are never overwritten.")
    output.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(source) as src,sqlite3.connect(output) as dst:
        src.backup(dst)
    db=Database(output)
    db.initialize()
    proposals=load_proposals(ROOT / "configs/successor_proposals_v1.json")
    drafts=[draft for item in db.requirement_summaries() if (draft:=generate_draft(db,item["requirement"],proposals))]
    if not drafts:
        raise ValueError("No matching real source anchors: no unsupported demonstration is generated.")
    if args.decision:
        draft=next(d for d in drafts if d.proposal.domain==args.domain)
        token=uuid4().hex
        _,revision=adopt_draft(db,draft,actor_id=args.reviewer,rationale=args.rationale,request_id=f"demo-adopt:{token}")
        PriorityService(db).save(requirement_id=revision.requirement_id,expected_revision=revision.revision,
            expected_sequence=0,factors=draft.proposal.factors,policy=draft.priority_policy,
            actor_id=args.reviewer,rationale="Reviewer explicitly accepted AI-suggested inputs for this demo: " + args.rationale,
            priority_confirmed=args.confirm_priority,request_id=f"demo-priority:{token}")
        ReviewService(db).decide(requirement_id=revision.requirement_id,expected_revision=revision.revision,
            action=DecisionAction(args.decision),actor_id=args.reviewer,rationale=args.rationale,request_id=f"demo-decision:{token}",uncertainty_acknowledged=args.acknowledge_uncertainty)
    summaries=[x for x in db.requirement_summaries() if x["requirement"].scope.models==["G60"] and x["requirement"].scope.countries==["US"]]
    brief=decision_brief(db,summaries,proposals,None)
    report=output.with_suffix(".md")
    report.write_text(brief,encoding="utf-8")
    validation=validate_database(db,expect_supplied_shape=True)
    if not validation["passed"]:
        raise ValueError(validation)
    for draft in sorted(drafts,key=lambda d:(-priority_score(d.proposal.factors,d.priority_policy),d.proposal.domain)):
        print(f"AI DRAFT {priority_score(draft.proposal.factors,draft.priority_policy):.2f}: {draft.proposal.title}")
    print(f"Private database: {output}; private report: {report}; data validation passed.")
    print("No new decisions generated." if not args.decision else "Recorded only the explicit CLI reviewer decision. Declared identity is not authentication or BMW sign-off.")


if __name__ == "__main__":
    main()
