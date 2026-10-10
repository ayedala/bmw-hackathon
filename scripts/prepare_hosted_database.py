"""Create a private WAL-consistent canonical snapshot; never commit the output."""
import argparse
import json
from pathlib import Path

from bmw_pm.hosting import prepare_snapshot

parser = argparse.ArgumentParser()
parser.add_argument("--source", type=Path, default=Path("data/processed/bmw_pm.db"))
parser.add_argument("--output", type=Path, default=Path("exports/hosted/bmw_pm.db"))
args = parser.parse_args()
report = prepare_snapshot(args.source, args.output)
args.output.with_suffix(".manifest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
