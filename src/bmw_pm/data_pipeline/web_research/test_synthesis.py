"""Tests for the evidence -> finding -> need -> requirement artifacts.

Read-only against the committed artifacts, plus unit tests for the derivation
helpers. Makes no network call and never writes to the data directory.
"""

from __future__ import annotations

import json
import pathlib
import unittest

import config
from build_synthesis import FINDINGS, NEEDS, REQUIREMENTS, Selector, confidence_for

PROCESSED = config.PROCESSED_DIR
FINDINGS_PATH = PROCESSED / "findings.jsonl"
NEEDS_PATH = PROCESSED / "customer_needs.jsonl"
REQUIREMENTS_PATH = PROCESSED / "requirements.jsonl"
SCORES_PATH = PROCESSED / "requirement_scores.jsonl"


def rows(path: pathlib.Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


class TestArtifactsExist(unittest.TestCase):
    def test_all_four_artifacts_are_present_and_non_empty(self):
        for path in (FINDINGS_PATH, NEEDS_PATH, REQUIREMENTS_PATH, SCORES_PATH):
            self.assertTrue(path.is_file(), f"missing {path.name}")
            self.assertTrue(rows(path), f"empty {path.name}")

    def test_canonical_evidence_is_not_one_of_our_outputs(self):
        """Guard: synthesis must never write the canonical store."""
        from build_synthesis import FINDINGS_PATH as f, NEEDS_PATH as n
        from build_synthesis import REQUIREMENTS_PATH as r, SCORES_PATH as s
        for path in (f, n, r, s):
            self.assertNotEqual(path, config.PROCESSED_EVIDENCE_PATH)

    def test_replay_file_is_never_read(self):
        """Cache replay is QA only; the generator must never open that store.

        Checks for the config path constant rather than the filename, because
        the module docstring legitimately mentions the file to say it is *not*
        read.
        """
        source = (config.BASE_DIR / "build_synthesis.py").read_text()
        self.assertNotIn("CACHE_REPROCESS_EVIDENCE_PATH", source)
        self.assertIn("PROCESSED_EVIDENCE_PATH", source)


class TestTraceability(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence_ids = {r["evidence_id"] for r in rows(config.PROCESSED_EVIDENCE_PATH)}
        cls.findings = rows(FINDINGS_PATH)
        cls.needs = rows(NEEDS_PATH)
        cls.requirements = rows(REQUIREMENTS_PATH)
        cls.scores = rows(SCORES_PATH)

    def test_every_finding_evidence_id_exists(self):
        for finding in self.findings:
            unknown = [e for e in finding["evidence_ids"] if e not in self.evidence_ids]
            self.assertFalse(unknown, f"{finding['finding_id']} -> {unknown[:3]}")

    def test_every_need_references_known_findings(self):
        known = {f["finding_id"] for f in self.findings}
        for need in self.needs:
            self.assertTrue(need["finding_ids"])
            for fid in need["finding_ids"]:
                self.assertIn(fid, known)

    def test_every_requirement_traces_to_need_finding_evidence(self):
        need_ids = {n["need_id"] for n in self.needs}
        finding_ids = {f["finding_id"] for f in self.findings}
        for req in self.requirements:
            self.assertTrue(req["need_ids"], req["requirement_id"])
            self.assertTrue(req["finding_ids"], req["requirement_id"])
            self.assertTrue(req["evidence_ids"], req["requirement_id"])
            for nid in req["need_ids"]:
                self.assertIn(nid, need_ids)
            for fid in req["finding_ids"]:
                self.assertIn(fid, finding_ids)
            for eid in req["evidence_ids"]:
                self.assertIn(eid, self.evidence_ids)

    def test_no_orphans(self):
        used_findings = {f for n in self.needs for f in n["finding_ids"]}
        self.assertEqual({f["finding_id"] for f in self.findings} - used_findings, set())
        used_needs = {n for r in self.requirements for n in r["need_ids"]}
        self.assertEqual({n["need_id"] for n in self.needs} - used_needs, set())

    def test_ids_are_unique_and_prefixed(self):
        for collection, field, prefix in (
            (self.findings, "finding_id", "FND-"),
            (self.needs, "need_id", "NEED-"),
            (self.requirements, "requirement_id", "REQ-"),
        ):
            ids = [row[field] for row in collection]
            self.assertEqual(len(ids), len(set(ids)))
            for value in ids:
                self.assertTrue(value.startswith(prefix), value)


class TestEvidenceDiscipline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.findings = rows(FINDINGS_PATH)
        cls.requirements = rows(REQUIREMENTS_PATH)

    def test_single_source_findings_are_not_high_confidence(self):
        for finding in self.findings:
            if finding["independent_source_count"] <= 1:
                self.assertEqual(finding["confidence"], "low_single_source",
                                 finding["finding_id"])

    def test_source_count_matches_evidence_ids(self):
        for finding in self.findings:
            self.assertEqual(finding["source_count"], len(finding["evidence_ids"]))

    def test_contradictions_are_preserved_and_resolve(self):
        known = {f["finding_id"] for f in self.findings}
        contradicting = [f for f in self.findings if f["contradicts"]]
        self.assertTrue(contradicting, "contradictions must be preserved, not hidden")
        for finding in contradicting:
            for other in finding["contradicts"]:
                self.assertIn(other, known)

    def test_requirements_are_unapproved_drafts(self):
        for req in self.requirements:
            self.assertEqual(req["status"], "draft_unapproved")
            self.assertTrue(req["validation_method"])

    def test_requirements_avoid_engineering_prescription(self):
        """Requirements must state customer outcomes, not implementations."""
        banned = ("800v", "use an ", "shall use a ", "lidar", "snapdragon")
        for req in self.requirements:
            text = req["requirement"].lower()
            for token in banned:
                self.assertNotIn(token, text, f"{req['requirement_id']} prescribes: {token}")

    def test_topic_coverage(self):
        topics = {f["topic"] for f in self.findings}
        for expected in ("infotainment", "charging", "range", "comfort",
                         "driving_experience", "market_trend"):
            self.assertIn(expected, topics)


class TestScoring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scores = rows(SCORES_PATH)

    def test_weights_match_the_reused_policy(self):
        for score in self.scores:
            self.assertEqual(
                score["weights"],
                {"customer_impact": 0.25, "evidence_backed_reach": 0.25,
                 "strategic_contribution": 0.25, "competitive_outlook_need": 0.25},
            )
            self.assertAlmostEqual(sum(score["weights"].values()), 1.0)

    def test_every_score_declares_its_deviation_and_is_unapproved(self):
        for score in self.scores:
            self.assertFalse(score["approved"])
            self.assertIn("evidence_backed_reach", score["deviation"])
            self.assertIn("exploratory_equal", score["derived_from"])

    def test_scores_are_reproducible_from_published_components(self):
        """No hidden arithmetic: components x weights must equal the total."""
        for score in self.scores:
            expected = sum(
                score["components_0_to_4"][name] * weight
                for name, weight in score["weights"].items()
            )
            self.assertAlmostEqual(score["weighted_score_0_to_4"], round(expected, 3), places=3)

    def test_scores_stay_in_range(self):
        for score in self.scores:
            self.assertGreaterEqual(score["weighted_score_0_to_4"], 0.0)
            self.assertLessEqual(score["weighted_score_0_to_4"], 4.0)


class TestDerivationHelpers(unittest.TestCase):
    def test_confidence_requires_independence(self):
        self.assertEqual(confidence_for(1, 95.0, 50), "low_single_source")
        self.assertEqual(confidence_for(5, 90.0, 10), "high")
        self.assertEqual(confidence_for(2, 75.0, 3), "medium")
        self.assertEqual(confidence_for(2, 50.0, 3), "low")

    def test_selector_caps_rows_per_independence_group(self):
        made = [
            {"subtopic": "charging_speed", "claim": "kw peak", "evidence_text": "",
             "source_quality": 95, "evidence_id": f"EXT-{i:03d}",
             "independence_group": "SRC-same", "numeric_value": 1.0}
            for i in range(10)
        ]
        kept = Selector(("charging_speed",), any_keywords=("kw",)).select(made)
        self.assertEqual(len(kept), 3, "no more than 3 rows from one source")

    def test_selector_respects_keyword_filters(self):
        made = [
            {"subtopic": "charging_speed", "claim": "peak kw", "evidence_text": "",
             "source_quality": 95, "evidence_id": "EXT-a", "independence_group": "SRC-a",
             "numeric_value": None},
            {"subtopic": "charging_speed", "claim": "unrelated", "evidence_text": "",
             "source_quality": 95, "evidence_id": "EXT-b", "independence_group": "SRC-b",
             "numeric_value": None},
        ]
        kept = Selector(("charging_speed",), any_keywords=("kw",)).select(made)
        self.assertEqual([r["evidence_id"] for r in kept], ["EXT-a"])

    def test_every_authored_spec_is_wired(self):
        """Authored specs must not silently drop out of the chain."""
        finding_keys = {f.key for f in FINDINGS}
        for need in NEEDS:
            for key in need.finding_keys:
                self.assertIn(key, finding_keys, f"{need.key} cites unknown finding {key}")
        need_keys = {n.key for n in NEEDS}
        for req in REQUIREMENTS:
            for key in req.need_keys:
                self.assertIn(key, need_keys, f"{req.key} cites unknown need {key}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
