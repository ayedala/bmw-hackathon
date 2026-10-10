"""Validate human labels and compare extraction on private frozen packets.

Run from the repository root with PYTHONPATH=src. Outputs stay under ignored runs/.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from bmw_pm.evaluation_workflow import (
    SPLITS, load_frozen, load_labels, run_extraction, score_extraction,
)
from bmw_pm.intelligence.provider import select_provider


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("runs/evaluation-v1"))
    commands = parser.add_subparsers(dest="command", required=True)
    labels = commands.add_parser("validate-labels")
    labels.add_argument("--second-review", type=Path)
    run = commands.add_parser("run-extraction")
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--split", choices=SPLITS, default="development")
    run.add_argument("--provider", choices=("baseline", "openai"), default="baseline")
    run.add_argument("--taxonomy", default="configs/baseline_taxonomy_v1.json")
    run.add_argument("--retry-failures", action="store_true")
    score = commands.add_parser("score-extraction")
    score.add_argument("--run", type=Path, required=True)
    score.add_argument("--second-review", type=Path)
    compare = commands.add_parser("compare-extraction")
    compare.add_argument("--first", type=Path, required=True)
    compare.add_argument("--second", type=Path, required=True)
    compare.add_argument("--second-review", type=Path)
    args = parser.parse_args()
    if args.command == "validate-labels":
        manifest, packets = load_frozen(args.root)
        _, _, result = load_labels(args.root, manifest, packets,
                                   second_review=args.second_review)
    elif args.command == "run-extraction":
        provider = select_provider(args.provider, baseline_config=args.taxonomy)
        result = run_extraction(args.root, args.output, provider, split=args.split,
                                retry_failures=args.retry_failures)
    elif args.command == "score-extraction":
        result = score_extraction(args.root, args.run, second_review=args.second_review)
    else:
        first = score_extraction(args.root, args.first, second_review=args.second_review)
        second = score_extraction(args.root, args.second, second_review=args.second_review)
        if first["split"] != second["split"] or first["records"] != second["records"]:
            raise ValueError("comparison requires the same frozen split")
        result = {"first": first, "second": second,
                  "interpretation": "Topic/polarity/span metrics are proxies; citation entailment and requirement quality need human review."}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
