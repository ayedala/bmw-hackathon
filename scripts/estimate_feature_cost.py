"""Calculate a reviewable feature cost scenario from a private JSON worksheet."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from bmw_pm.decision.feature_cost import FeatureCostPlan, estimate_feature_cost


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="JSON file matching FeatureCostPlan")
    args = parser.parse_args()
    plan = FeatureCostPlan.model_validate(json.loads(args.input.read_text(encoding="utf-8")))
    print(json.dumps(estimate_feature_cost(plan), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
