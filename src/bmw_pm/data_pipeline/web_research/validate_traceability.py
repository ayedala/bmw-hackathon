"""Validate the evidence -> finding -> need -> requirement chain.

Read-only. Exits non-zero on any violation, so it can gate a commit.

Checks:
  * every file is valid JSONL
  * ids are unique within each layer and carry the expected prefix
  * every finding's evidence_ids exist in canonical evidence
  * every need's finding_ids exist, and its evidence_ids exist
  * every requirement's need_ids, finding_ids and evidence_ids exist
  * no orphans: every finding feeds a need, every need feeds a requirement
  * a need's evidence is covered by its findings' evidence
  * a requirement's evidence is covered by its needs' evidence
  * single-source findings are not marked high confidence
  * contradiction references resolve
  * every score points at a real requirement

Usage::

    python validate_traceability.py          # validate
    python validate_traceability.py --quiet  # only report failures
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from collections import Counter

import config

LAYERS = {
    "evidence": (config.PROCESSED_EVIDENCE_PATH, "evidence_id", "EXT-"),
    "findings": (config.PROCESSED_DIR / "findings.jsonl", "finding_id", "FND-"),
    "needs": (config.PROCESSED_DIR / "customer_needs.jsonl", "need_id", "NEED-"),
    "requirements": (config.PROCESSED_DIR / "requirements.jsonl", "requirement_id", "REQ-"),
    "scores": (config.PROCESSED_DIR / "requirement_scores.jsonl", "requirement_id", "REQ-"),
}


class Report:
    """Collects failures so every problem is reported, not just the first."""

    def __init__(self, quiet: bool = False) -> None:
        self.failures: list[str] = []
        self.quiet = quiet

    def ok(self, message: str) -> None:
        if not self.quiet:
            print(f"  PASS  {message}")

    def fail(self, message: str) -> None:
        print(f"  FAIL  {message}")
        self.failures.append(message)

    def check(self, condition: bool, message: str, detail: str = "") -> bool:
        if condition:
            self.ok(message)
        else:
            self.fail(f"{message}{f' - {detail}' if detail else ''}")
        return condition


def load_jsonl(path: pathlib.Path, report: Report, label: str) -> list[dict]:
    """Load a JSONL file, reporting any unparsable line."""
    if not path.is_file():
        report.fail(f"{label}: missing file {path}")
        return []
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            report.fail(f"{label}: invalid JSON at line {number}: {exc}")
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate downstream traceability.")
    parser.add_argument("--quiet", action="store_true", help="only print failures")
    args = parser.parse_args(argv)
    report = Report(quiet=args.quiet)

    print("=" * 76)
    print("TRACEABILITY VALIDATION")
    print("=" * 76)

    data: dict[str, list[dict]] = {}
    for label, (path, id_field, prefix) in LAYERS.items():
        rows = load_jsonl(path, report, label)
        data[label] = rows
        if not rows:
            continue
        ids = [row.get(id_field) for row in rows]
        dupes = {k: v for k, v in Counter(ids).items() if v > 1}
        report.check(not dupes, f"{label}: ids unique ({len(ids)} rows)", str(dupes))
        bad = [i for i in ids if not str(i).startswith(prefix)]
        report.check(not bad, f"{label}: ids use the {prefix}* prefix", str(bad[:3]))

    if report.failures:
        print("\n  structural problems found; stopping before reference checks")
        print("=" * 76)
        return 1

    evidence_ids = {row["evidence_id"] for row in data["evidence"]}
    findings = data["findings"]
    needs = data["needs"]
    requirements = data["requirements"]
    finding_ids = {f["finding_id"] for f in findings}
    need_ids = {n["need_id"] for n in needs}

    # -- findings -> evidence -------------------------------------------- #
    unknown = {f["finding_id"]: [e for e in f["evidence_ids"] if e not in evidence_ids]
               for f in findings}
    unknown = {k: v for k, v in unknown.items() if v}
    report.check(not unknown, "findings reference only known evidence_ids",
                 str({k: v[:2] for k, v in list(unknown.items())[:2]}))
    report.check(all(f["evidence_ids"] for f in findings),
                 "every finding has at least one evidence_id")
    report.check(all(f["source_count"] == len(f["evidence_ids"]) for f in findings),
                 "finding source_count matches its evidence_ids")

    weak = [f["finding_id"] for f in findings
            if f["independent_source_count"] <= 1 and f["confidence"] == "high"]
    report.check(not weak, "no single-source finding claims high confidence", str(weak))

    bad_contra = [c for f in findings for c in f.get("contradicts", []) if c not in finding_ids]
    report.check(not bad_contra, "contradiction references resolve", str(bad_contra[:3]))

    # -- needs -> findings / evidence ------------------------------------ #
    bad = {n["need_id"]: [f for f in n["finding_ids"] if f not in finding_ids] for n in needs}
    bad = {k: v for k, v in bad.items() if v}
    report.check(not bad, "needs reference only known finding_ids", str(bad))
    bad = {n["need_id"]: [e for e in n["evidence_ids"] if e not in evidence_ids] for n in needs}
    bad = {k: v for k, v in bad.items() if v}
    report.check(not bad, "needs reference only known evidence_ids", str(bad))
    report.check(all(n["finding_ids"] for n in needs), "every need cites at least one finding")

    by_finding = {f["finding_id"]: set(f["evidence_ids"]) for f in findings}
    leaks = []
    for need in needs:
        covered = set().union(*(by_finding[f] for f in need["finding_ids"]))
        extra = set(need["evidence_ids"]) - covered
        if extra:
            leaks.append((need["need_id"], sorted(extra)[:2]))
    report.check(not leaks, "need evidence is covered by its findings", str(leaks[:2]))

    # -- requirements -> needs / findings / evidence --------------------- #
    for field, universe, label in (("need_ids", need_ids, "need_ids"),
                                   ("finding_ids", finding_ids, "finding_ids"),
                                   ("evidence_ids", evidence_ids, "evidence_ids")):
        bad = {r["requirement_id"]: [x for x in r[field] if x not in universe]
               for r in requirements}
        bad = {k: v for k, v in bad.items() if v}
        report.check(not bad, f"requirements reference only known {label}", str(bad))

    report.check(all(r["need_ids"] for r in requirements),
                 "every requirement cites at least one need")

    by_need = {n["need_id"]: set(n["evidence_ids"]) for n in needs}
    leaks = []
    for requirement in requirements:
        covered = set().union(*(by_need[n] for n in requirement["need_ids"]))
        extra = set(requirement["evidence_ids"]) - covered
        if extra:
            leaks.append((requirement["requirement_id"], sorted(extra)[:2]))
    report.check(not leaks, "requirement evidence is covered by its needs", str(leaks[:2]))

    # -- orphans --------------------------------------------------------- #
    used_findings = {f for n in needs for f in n["finding_ids"]}
    orphan_findings = sorted(finding_ids - used_findings)
    report.check(not orphan_findings, "no orphan findings (each feeds a need)",
                 str(orphan_findings))

    used_needs = {n for r in requirements for n in r["need_ids"]}
    orphan_needs = sorted(need_ids - used_needs)
    report.check(not orphan_needs, "no orphan needs (each feeds a requirement)",
                 str(orphan_needs))

    # -- scores ---------------------------------------------------------- #
    requirement_ids = {r["requirement_id"] for r in requirements}
    scored = {s["requirement_id"] for s in data["scores"]}
    report.check(scored <= requirement_ids, "scores reference only known requirements",
                 str(sorted(scored - requirement_ids)[:3]))
    report.check(requirement_ids <= scored, "every requirement has a score",
                 str(sorted(requirement_ids - scored)[:3]))
    unapproved = [s["requirement_id"] for s in data["scores"] if s.get("approved") is not False]
    report.check(not unapproved, "scores are marked unapproved", str(unapproved[:3]))

    # -- canonical evidence untouched ------------------------------------ #
    report.check(len(evidence_ids) == len(data["evidence"]),
                 f"canonical evidence ids unique ({len(data['evidence'])} rows)")

    print()
    print("=" * 76)
    if report.failures:
        print(f"VALIDATION FAILED - {len(report.failures)} problem(s)")
        print("=" * 76)
        return 1
    print(f"VALIDATION PASSED - {len(findings)} findings, {len(needs)} needs, "
          f"{len(requirements)} requirements, {len(data['evidence'])} evidence rows")
    print("=" * 76)
    return 0


if __name__ == "__main__":
    sys.exit(main())
