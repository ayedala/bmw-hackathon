from __future__ import annotations

import argparse
import json
from pathlib import Path
from uuid import uuid4

from .contracts import DecisionAction, PolicyVersion
from .intelligence.provider import select_provider
from .pipeline import ingest_supplied_data, load_json, run_candidate_pipeline
from .review import ReviewService
from .storage import Database
from .validation import validate_database


def _json_print(value: object) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False, default=str))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bmw-pm")
    parser.add_argument("--db", default="data/processed/bmw_pm.db")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest = subparsers.add_parser("ingest", help="ingest local supplied workbooks")
    ingest.add_argument("--input", default="data/raw/provided")
    ingest.add_argument("--profile", default="configs/g60.json")

    run = subparsers.add_parser("run", help="derive and score requirement candidates")
    run.add_argument("--profile", default="configs/g60.json")
    run.add_argument("--policy", default="configs/exploratory_equal_v1.json")
    run.add_argument("--taxonomy", default="configs/baseline_taxonomy_v1.json")
    run.add_argument("--provider", choices=("auto", "baseline", "openai"), default="auto")
    run.add_argument("--limit", type=int)
    run.add_argument("--full", action="store_true", help="print complete candidate payloads")

    subparsers.add_parser("list", help="list latest requirement cards")

    review = subparsers.add_parser("review", help="approve, reject, challenge, or defer")
    review.add_argument("requirement_id")
    review.add_argument("--revision", type=int, required=True)
    review.add_argument(
        "--action", choices=("approve", "reject", "challenge", "defer"), required=True
    )
    review.add_argument("--reason", required=True)
    review.add_argument("--actor", default="local-demo-pm")
    review.add_argument("--request-id")

    edit = subparsers.add_parser("edit", help="create a new immutable requirement revision")
    edit.add_argument("requirement_id")
    edit.add_argument("--revision", type=int, required=True)
    edit.add_argument("--title")
    edit.add_argument("--customer-outcome")
    edit.add_argument("--reason", required=True)
    edit.add_argument("--actor", default="local-demo-pm")
    edit.add_argument("--request-id")

    verify = subparsers.add_parser("verify-audit")

    validate = subparsers.add_parser("validate", help="run deterministic database checks")
    validate.add_argument("--expect-supplied-shape", action="store_true")

    replay = subparsers.add_parser("replay")
    replay.add_argument("requirement_id")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    database = Database(Path(args.db))
    database.initialize()
    if args.command == "ingest":
        report = ingest_supplied_data(
            database=database,
            input_dir=args.input,
            profile=load_json(args.profile),
        )
        _json_print(report)
        return 0
    if args.command == "run":
        profile = load_json(args.profile)
        policy = PolicyVersion.model_validate(load_json(args.policy))
        provider = select_provider(args.provider, baseline_config=args.taxonomy)
        result = run_candidate_pipeline(
            database=database,
            profile=profile,
            policy=policy,
            provider=provider,
            limit=args.limit,
        )
        if args.full:
            _json_print(result)
        else:
            _json_print(
                {
                    "run": result["run"],
                    "requirements": [
                        {
                            "requirement_id": item["requirement_id"],
                            "revision": item["revision"],
                            "title": item["title"],
                            "support_count": item["support_count"],
                            "praise_or_preservation_count": item["counter_count"],
                        }
                        for item in result["requirements"]
                    ],
                    "score_intervals": [
                        {
                            "requirement_id": item["requirement_id"],
                            "lower_bound": item["lower_bound"],
                            "upper_bound": item["upper_bound"],
                            "customer": item["dimension_intervals"].get("customer"),
                            "business": item["dimension_intervals"].get("business"),
                            "feasibility": {
                                "status": item["feasibility_status"],
                                "basis": item["feasibility_basis"],
                            },
                        }
                        for item in result["scores"]
                    ],
                    "limitations": result["limitations"],
                    "ranking_assessment": result["ranking_assessment"],
                }
            )
        return 0
    if args.command == "list":
        rows = []
        for item in database.requirement_summaries():
            requirement = item["requirement"]
            score = item["score"]
            decision = item["decision"]
            rows.append(
                {
                    "requirement_id": requirement.requirement_id,
                    "revision": requirement.revision,
                    "title": requirement.title,
                    "score_interval": [score.lower_bound, score.upper_bound] if score else None,
                    "customer_interval": (
                        score.dimension_intervals["customer"].model_dump(mode="json")
                        if score and "customer" in score.dimension_intervals else None
                    ),
                    "business_interval": (
                        score.dimension_intervals["business"].model_dump(mode="json")
                        if score and "business" in score.dimension_intervals else None
                    ),
                    "feasibility": requirement.feasibility,
                    "ordering_note": "Exploratory lower-bound order; overlapping ranges are unresolved.",
                    "decision": decision.action.value if decision else "needs_review",
                }
            )
        _json_print(rows)
        return 0
    if args.command == "review":
        service = ReviewService(database)
        decision = service.decide(
            requirement_id=args.requirement_id,
            expected_revision=args.revision,
            action=DecisionAction(args.action),
            rationale=args.reason,
            actor_id=args.actor,
            request_id=args.request_id or f"cli_{uuid4().hex}",
        )
        _json_print(decision.model_dump(mode="json"))
        return 0
    if args.command == "edit":
        changes = {
            key: value
            for key, value in {
                "title": args.title,
                "customer_outcome": args.customer_outcome,
            }.items()
            if value is not None
        }
        decision, revision = ReviewService(database).edit(
            requirement_id=args.requirement_id,
            expected_revision=args.revision,
            changes=changes,
            rationale=args.reason,
            actor_id=args.actor,
            request_id=args.request_id or f"cli_{uuid4().hex}",
        )
        _json_print(
            {
                "decision": decision.model_dump(mode="json"),
                "new_revision": revision.model_dump(mode="json"),
            }
        )
        return 0
    if args.command == "verify-audit":
        valid, checkpoint = database.verify_audit_chain()
        _json_print({"valid": valid, "checkpoint": checkpoint})
        return 0 if valid else 1
    if args.command == "validate":
        result = validate_database(
            database, expect_supplied_shape=args.expect_supplied_shape
        )
        _json_print(result)
        return 0 if result["passed"] else 1
    if args.command == "replay":
        _json_print(database.replay_requirement(args.requirement_id))
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
