"""Replayable, local-corpus challenge/reassessment workflow.

Retrieval is deterministic lexical/concept matching, not an LLM entailment
judgment. Newly retrieved evidence with no explicit stance remains context.
Only evidence-dependent factors are recomputed; a challenge cannot manufacture
a population denominator, a customer-impact rating, or an approved strategy.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ..contracts import Decision, DecisionAction, RequirementRevision, ScoreSnapshot
from ..decision.crps import (
    COMPETITOR_BRANDS, FACTOR_ORDER, FUTURE_SUBTOPICS, compute_competitive_gap, compute_crps,
    compute_decision_confidence, compute_evidence_strength, compute_future_relevance,
    compute_market_relevance,
)
from ..storage import Database
from ..storage.database import RevisionConflict, WorkflowError
from ..utils import canonical_json, content_hash, stable_id, utc_now

ROOT = Path(__file__).resolve().parents[3]
STOPWORDS = frozenset("the a an and or for of to is are be with in on this that should shall can not does evidence requirement germany bmw".split())
CONCEPTS = (
    {"charging", "charger", "charge", "laden", "ladeleistung", "ladestation"},
    {"controls", "control", "buttons", "button", "tactile", "physical", "bedienung"},
    {"range", "reichweite", "battery", "batterie"},
    {"comfort", "komfort", "seats", "seat", "sitz"},
    {"display", "screen", "touchscreen", "infotainment"},
)


def _tokens(value: Any) -> set[str]:
    terms = {word for word in re.findall(r"[\w]+", str(value).lower()) if len(word) > 2} - STOPWORDS
    for group in CONCEPTS:
        if terms & group:
            terms |= group
    return terms


def _identity(row: dict[str, Any]) -> str | None:
    return next((str(row[k]) for k in ("evidence_id", "finding_id", "need_id", "requirement_id", "signal_id", "record_id", "survey_id", "observation_id", "context_id") if row.get(k)), None)


def _stance(value: Any) -> str:
    value = str(value or "").lower()
    if value in {"supports", "support", "supporting", "preserves"}:
        return "supports"
    if value in {"opposes", "opposing", "contradicts", "contradicting", "against"}:
        return "opposes"
    return "context"


def _raw_reference(ref) -> dict[str, Any]:
    row = {**ref.provenance.get("source_record", {}), **ref.model_dump(mode="json")}
    row["evidence_text"] = row.get("exact_text")
    return row


class ChallengeService:
    """Append-only challenge records; only a PM acceptance changes the score."""

    def __init__(self, database: Database, *, root: Path = ROOT) -> None:
        self.database = database
        self.root = Path(root)

    @staticmethod
    def _request(**values) -> dict[str, Any]:
        clean = {key: value.strip() if isinstance(value, str) else value for key, value in values.items()}
        for key in ("actor_id", "request_id", "rationale", "hypothesis"):
            if key in clean and not clean[key]:
                raise ValueError(f"{key} must not be blank")
        if len(clean.get("hypothesis", "")) > 8000:
            raise ValueError("challenge hypothesis is too long")
        return clean

    def _current(self, connection, requirement_id: str, expected_revision: int):
        row = connection.execute(
            "SELECT payload_json FROM requirement_revisions WHERE requirement_id=? ORDER BY revision DESC LIMIT 1",
            (requirement_id,),
        ).fetchone()
        if not row:
            raise KeyError(requirement_id)
        requirement = RequirementRevision.model_validate_json(row["payload_json"])
        if requirement.revision != expected_revision:
            raise RevisionConflict(f"Stale challenge: expected revision {expected_revision}, latest is {requirement.revision}.")
        score_row = connection.execute(
            "SELECT payload_json FROM score_snapshots WHERE requirement_id=? AND requirement_revision=? ORDER BY rowid DESC LIMIT 1",
            (requirement_id, expected_revision),
        ).fetchone()
        if not score_row:
            raise WorkflowError("A recorded canonical CRPS score is required before challenging this requirement.")
        score = ScoreSnapshot.model_validate_json(score_row["payload_json"])
        if set(score.criterion_inputs) != set(FACTOR_ORDER) or "crps" not in score.coverage:
            raise WorkflowError("Challenge requires the seven-factor CRPS, not a legacy four-factor priority score.")
        judgments = self.database._latest_evidence_judgments(connection, requirement_id, expected_revision)
        return requirement, score, judgments

    def _conflict(self, connection, request, message: str) -> None:
        """Rejected stale PM attempts are also visible in the authoritative log."""
        self.database._append_audit(connection, actor_id=request["actor_id"], actor_type="demo_pm",
            action="challenge_revision_conflict", object_type="requirement", object_id=request["requirement_id"],
            object_revision=request["expected_revision"], before_hash=None, after_hash=None,
            reason=message, request_id=request["request_id"], result="failure")
        connection.commit()
        raise RevisionConflict(message)

    def _corpus(self, connection, requirement, score) -> list[dict[str, Any]]:
        """Search an immutable imported corpus plus existing local channels only."""
        docs: dict[str, dict[str, Any]] = {}

        def add(kind: str, payload: dict[str, Any], item_id: str | None = None):
            identity = item_id or _identity(payload)
            if identity:
                docs[identity] = {"item_id": identity, "kind": kind, "payload": payload}

        for row in connection.execute(
            "SELECT artifact_kind,payload_json FROM canonical_artifacts WHERE corpus_hash=? ORDER BY artifact_key",
            (score.corpus_manifest_hash,),
        ).fetchall():
            if row["artifact_kind"] in {"scores", "research_runs"}:
                continue
            payload = json.loads(row["payload_json"])
            if isinstance(payload, dict):
                add(row["artifact_kind"], payload)
        # Legacy channels are genuine persisted records, never fixture imports.
        tables = {row["name"] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        for table, kind in (("signals", "internal_feedback"), ("feedback_records", "internal_feedback"),
                            ("youtube_findings", "youtube"), ("report_context", "planning_context"),
                            ("bmw_context", "planning_context"), ("survey_observations", "study")):
            if table not in tables:
                continue
            for item in connection.execute(f"SELECT payload_json FROM {table}").fetchall():
                payload = json.loads(item["payload_json"])
                if isinstance(payload, dict):
                    if table == "signals":
                        payload = {**payload, "evidence_id": payload.get("signal_id"),
                            "independence_group": payload.get("feedback_record_id"),
                            "source_family": "internal_feedback"}
                    add(kind, payload)
        planning = self.root / "configs/planning_public_context.json"
        if planning.is_file():
            for item in json.loads(planning.read_text(encoding="utf-8")):
                add("planning_context", item, stable_id("planning", content_hash(item)))
        for ref in getattr(requirement, "evidence_references", []):
            if ref.evidence_id not in docs:
                add(ref.evidence_kind, _raw_reference(ref))
        return sorted(docs.values(), key=lambda item: item["item_id"])

    def _retrieve(self, docs, requirement, hypothesis, judgments) -> dict[str, Any]:
        query_terms = _tokens(hypothesis + " " + requirement.title + " " + requirement.customer_outcome)
        hypothesis_terms = _tokens(hypothesis)
        topic = str(getattr(requirement, "topic", "") or "").lower()
        linked = {ref.evidence_id: ref.role for ref in getattr(requirement, "evidence_references", [])}
        linked.update({identity: "supports" for identity in requirement.supporting_signal_ids})
        linked.update({identity: "opposes" for identity in requirement.counter_signal_ids})
        linked.update({identity: "context" for identity in requirement.context_signal_ids})
        linked_findings = set(getattr(requirement, "finding_ids", []))
        opposing_ids: set[str] = set()
        for doc in docs:
            payload = doc["payload"]
            if linked_findings & set(payload.get("contradicts", [])):
                opposing_ids.update(payload.get("evidence_ids", []))
            if doc["item_id"] in linked_findings:
                for other in docs:
                    if other["item_id"] in payload.get("contradicts", []):
                        opposing_ids.update(other["payload"].get("evidence_ids", []))
        ranked = []
        for doc in docs:
            payload, identity = doc["payload"], doc["item_id"]
            text = " ".join(str(payload.get(key) or "") for key in (
                "title", "claim", "evidence_text", "exact_text", "summary", "statement", "rationale",
                "requirement", "atomic_claim", "source_statement", "supporting_excerpt", "observation",
                "text_customer", "text_raw", "topic", "subtopic", "need_domain"))
            terms = _tokens(text)
            overlap = query_terms & terms
            hypothesis_hits = hypothesis_terms & terms
            row_topic = str(payload.get("topic") or payload.get("need_domain") or "").lower()
            topic_match = bool(topic and topic == row_topic)
            is_linked = identity in linked
            if not is_linked and identity not in opposing_ids and not (len(hypothesis_hits) >= 2 or (topic_match and overlap)):
                continue
            market = str(payload.get("market") or payload.get("country") or "unknown").upper()
            direct = market in requirement.scope.countries
            vehicle = str(payload.get("vehicle") or payload.get("model_code") or payload.get("generation") or "")
            vehicle_match = any(model.lower() in vehicle.lower() for model in requirement.scope.models if model)
            relevance = (20 if is_linked else 0) + (8 if topic_match else 0) + min(len(overlap), 12) + len(hypothesis_hits) * 2 + (2 if direct else 0) + (2 if vehicle_match else 0)
            role = linked.get(identity, "opposes" if identity in opposing_ids else _stance(payload.get("stance")))
            # Findings/needs/requirements are navigation context, not independent evidence.
            if not (payload.get("evidence_id") or payload.get("signal_id")):
                role = "context"
            verdict = judgments.get(identity)
            if verdict:
                role = {"supports": "supports", "does_not_support": "context", "context_only": "context"}[verdict.verdict]
            ranked.append({**doc, "role": role, "relevance": relevance,
                "relevance_basis": {"linked": is_linked, "topic_match": topic_match, "terms": sorted(overlap), "hypothesis_terms": sorted(hypothesis_hits), "vehicle_match": vehicle_match},
                "applicability": "direct_market" if direct else "context_market_unconfirmed"})
        ranked.sort(key=lambda item: (-item["relevance"], item["item_id"]))
        # Keep all already-linked evidence, even when a long result set is bounded.
        retained = [item for index, item in enumerate(ranked) if index < 60 or item["item_id"] in linked or item["item_id"] in opposing_ids]
        return {"supporting": [item for item in retained if item["role"] == "supports"],
            "opposing": [item for item in retained if item["role"] == "opposes"],
            "context": [item for item in retained if item["role"] == "context"],
            "excluded_evidence_ids": sorted(key for key, judgment in judgments.items() if judgment.verdict != "supports"),
            "searched_counts": dict(Counter(doc["kind"] for doc in docs)),
            "matched_count": len(ranked), "retained_count": len(retained),
            "method": "Deterministic topic, concept-expanded lexical overlap, market and vehicle ranking; no live search or LLM. Unknown stance stays context; lexical relevance is not proof of entailment."}

    def challenge(self, *, requirement_id: str, expected_revision: int, hypothesis: str,
                  rationale: str, actor_id: str, request_id: str) -> dict[str, Any]:
        request = self._request(requirement_id=requirement_id, expected_revision=expected_revision,
            hypothesis=hypothesis, rationale=rationale, actor_id=actor_id, request_id=request_id)
        self.database.initialize()
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            previous = connection.execute("SELECT payload_json FROM requirement_challenges WHERE request_id=?", (request_id,)).fetchone()
            if previous:
                result = json.loads(previous["payload_json"])
                if result["request_hash"] != content_hash(request):
                    raise WorkflowError("request ID already belongs to a different challenge")
                return result
            if self.database._existing_event(connection, request_id):
                raise WorkflowError("request ID already belongs to another operation")
            try:
                requirement, baseline, judgments = self._current(connection, requirement_id, expected_revision)
            except RevisionConflict as error:
                self._conflict(connection, request, str(error))
            docs = self._corpus(connection, requirement, baseline)
            retrieval = self._retrieve(docs, requirement, request["hypothesis"], judgments)
            support = [item["payload"] for item in retrieval["supporting"]]
            oppose = [item["payload"] for item in retrieval["opposing"]]
            today = utc_now().date()
            strength = compute_evidence_strength(support, oppose, today=today)
            factors = dict(baseline.criterion_inputs)
            ids = sorted({item["item_id"] for item in retrieval["supporting"] + retrieval["opposing"]})
            old_ids = set(baseline.coverage["crps"].get("factor_evidence_ids", {}).get("evidence_strength", []))
            changed_evidence = (set(ids) != old_ids or bool(judgments)
                                or any(row.get("duplicate_of") for row in support + oppose)
                                or baseline.coverage["crps"].get("calculated_at") != today.isoformat())
            gap_detail = baseline.coverage["crps"].get("competitive_gap", {})
            recomputed = []
            if changed_evidence:
                factors["evidence_strength"] = strength.as_criterion()
                factors["market_relevance"] = compute_market_relevance(support + oppose, primary_market="DE")
                bmw = [row for row in support + oppose if str(row.get("brand", "")).lower() == "bmw"]
                competitors = [row for row in support + oppose if str(row.get("brand", "")).lower() in COMPETITOR_BRANDS]
                factors["competitive_gap"], gap_detail = compute_competitive_gap(bmw, competitors)
                factors["future_relevance"] = compute_future_relevance(support)
                recomputed = ["evidence_strength", "market_relevance", "competitive_gap", "future_relevance"]
            result = compute_crps(factors)
            factor_ids = dict(baseline.coverage["crps"].get("factor_evidence_ids", {}))
            for name in recomputed:
                factor_ids[name] = ids
            if changed_evidence:
                factor_ids["competitive_gap"] = list(dict.fromkeys(row["evidence_id"] for row in bmw + competitors))
                factor_ids["future_relevance"] = [row["evidence_id"] for row in support
                    if not row.get("duplicate_of") and (row.get("topic") == "market_trend"
                        or row.get("subtopic") in FUTURE_SUBTOPICS)]
            after = {"result": asdict(result), "confidence": asdict(compute_decision_confidence(strength)),
                "evidence_strength": asdict(strength), "competitive_gap": gap_detail,
                "factor_evidence_ids": factor_ids, "calculated_at": today.isoformat()}
            after["result"]["dimension_intervals"] = {name: interval.model_dump(mode="json")
                for name, interval in result.dimension_intervals.items()}
            changes = [{"factor": name, "before": baseline.criterion_inputs[name].model_dump(mode="json"),
                "after": factors[name].model_dump(mode="json"), "evidence_ids": factor_ids[name],
                "reason": "Recomputed from the retrieved evidence roles, immutable source metadata and current PM link judgments."}
                for name in recomputed if baseline.criterion_inputs[name] != factors[name]]
            gaps = list(requirement.missing_evidence)
            gaps.extend(f"{name}: {item.missing_reason}" for name, item in factors.items() if item.missing_reason)
            if not any(str(row.get("market", "")).upper() == "DE" for row in support):
                gaps.append("No direct Germany supporting evidence; contextual market evidence does not establish DE demand.")
            gaps.append("Retrieval relevance is deterministic lexical/concept matching; PM must review semantic entailment and unclassified context.")
            challenge_id = stable_id("challenge", request_id, requirement_id)
            snapshot_id = stable_id("score", challenge_id, content_hash(after))
            coverage = {**baseline.coverage, "crps": after, "challenge_id": challenge_id,
                "evidence_ids": ids, "judgment_ids": sorted(j.judgment_id for j in judgments.values())}
            proposed = baseline.model_copy(update={"score_snapshot_id": snapshot_id,
                "criterion_inputs": factors, "contributions": {name: (factor.lower_contribution, factor.upper_contribution) for name, factor in result.factors.items()},
                "lower_bound": result.crps_100_lower, "upper_bound": result.crps_100_upper,
                "dimension_intervals": result.dimension_intervals, "coverage": coverage,
                "run_id": challenge_id, "assumptions": [*baseline.assumptions,
                    "Challenge retrieval used only existing local artifacts; no new research or LLM scoring."]})
            record = {"challenge_id": challenge_id, "requirement_id": requirement_id,
                "requirement_revision": expected_revision, **{k: request[k] for k in ("hypothesis", "rationale", "actor_id", "request_id")},
                "created_at": utc_now().isoformat(), "request_hash": content_hash(request),
                "baseline_score_id": baseline.score_snapshot_id, "baseline_score_hash": content_hash(baseline),
                "judgment_hash": content_hash({key: value.model_dump(mode="json") for key, value in judgments.items()}),
                "corpus_hash": content_hash(docs), "corpus_manifest": {doc["item_id"]: content_hash(doc["payload"]) for doc in docs},
                "before": baseline.coverage["crps"], "after": after, "factor_changes": changes,
                "retrieval": retrieval, "gaps": list(dict.fromkeys(gaps)), "evidence_ids": ids,
                "explanation": [f"{strength.duplicate_rows_excluded} duplicate rows excluded from independent confirmation.",
                    f"{len(retrieval['excluded_evidence_ids'])} links excluded from support by PM judgment.",
                    f"{strength.contradicting_groups} independent opposing source groups retained.",
                    "Customer Impact, Frequency and Strategic Fit were preserved; retrieval supplies no new approved inputs for them.",
                    f"Recomputed evidence-dependent factors: {', '.join(recomputed) or 'none (evidence unchanged)'}."],
                "proposed_score": proposed.model_dump(mode="json")}
            connection.execute("INSERT INTO requirement_challenges VALUES (?,?,?,?,?,?)",
                (challenge_id, requirement_id, expected_revision, request_id, canonical_json(record), content_hash(record)))
            decision = Decision(decision_id=stable_id("decision", challenge_id), requirement_id=requirement_id,
                requirement_revision=expected_revision, action=DecisionAction.CHALLENGE,
                rationale=request["rationale"], actor_id=request["actor_id"], role="demo_pm", recorded_at=utc_now(),
                score_snapshot_id=baseline.score_snapshot_id, expected_revision=expected_revision, request_id=request_id)
            connection.execute("INSERT INTO decisions (decision_id,requirement_id,requirement_revision,action,request_id,recorded_at,payload_json,payload_hash) VALUES (?,?,?,?,?,?,?,?)",
                (decision.decision_id, requirement_id, expected_revision, decision.action.value, request_id,
                 decision.recorded_at.isoformat(), decision.model_dump_json(), content_hash(decision)))
            self.database._append_audit(connection, actor_id=request["actor_id"], actor_type="demo_pm",
                action="challenge_requirement", object_type="requirement", object_id=requirement_id,
                object_revision=expected_revision, before_hash=content_hash(baseline), after_hash=content_hash(record),
                reason=f"{request['hypothesis']} — {request['rationale']}; challenge {challenge_id}; exact evidence IDs: {', '.join(ids)}",
                request_id=request_id, result="success", run_id=challenge_id)
            connection.commit()
            return record

    def reassess(self, *, challenge_id: str, requirement_id: str, expected_revision: int,
                 accept: bool, rationale: str, actor_id: str, request_id: str) -> dict[str, Any]:
        if not isinstance(accept, bool):
            raise ValueError("accept must be a boolean PM decision")
        request = self._request(challenge_id=challenge_id, requirement_id=requirement_id,
            expected_revision=expected_revision, accept=accept, rationale=rationale, actor_id=actor_id, request_id=request_id)
        self.database.initialize()
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute("SELECT payload_json FROM challenge_resolutions WHERE request_id=?", (request_id,)).fetchone()
            if existing:
                resolution = json.loads(existing["payload_json"])
                if resolution["request_hash"] != content_hash(request):
                    raise WorkflowError("request ID already belongs to a different reassessment")
                return resolution
            if self.database._existing_event(connection, request_id):
                raise WorkflowError("request ID already belongs to another operation")
            row = connection.execute("SELECT payload_json FROM requirement_challenges WHERE challenge_id=?", (challenge_id,)).fetchone()
            if not row:
                raise ValueError("Challenge does not exist")
            challenge = json.loads(row["payload_json"])
            if challenge["requirement_id"] != requirement_id or challenge["requirement_revision"] != expected_revision:
                raise WorkflowError("Challenge belongs to a different requirement revision")
            if connection.execute("SELECT 1 FROM challenge_resolutions WHERE challenge_id=?", (challenge_id,)).fetchone():
                raise WorkflowError("Challenge has already been resolved")
            try:
                _, current_score, judgments = self._current(connection, requirement_id, expected_revision)
            except RevisionConflict as error:
                self._conflict(connection, request, str(error))
            judgment_hash = content_hash({key: value.model_dump(mode="json") for key, value in judgments.items()})
            if content_hash(current_score) != challenge["baseline_score_hash"] or judgment_hash != challenge["judgment_hash"]:
                self._conflict(connection, request, "Score or evidence judgments changed after retrieval. Run a new challenge before reassessing.")
            score = ScoreSnapshot.model_validate(challenge["proposed_score"])
            if accept:
                connection.execute("INSERT INTO score_snapshots (score_snapshot_id,requirement_id,requirement_revision,lower_bound,upper_bound,run_id,payload_json,payload_hash) VALUES (?,?,?,?,?,?,?,?)",
                    (score.score_snapshot_id, requirement_id, expected_revision, score.lower_bound,
                     score.upper_bound, score.run_id, score.model_dump_json(), content_hash(score)))
            resolution = {"resolution_id": stable_id("reassessment", request_id), "challenge_id": challenge_id,
                "requirement_id": requirement_id, "requirement_revision": expected_revision,
                "accepted": accept, "actor_id": request["actor_id"], "rationale": request["rationale"],
                "request_id": request_id, "request_hash": content_hash(request), "recorded_at": utc_now().isoformat(),
                "score_snapshot_id": score.score_snapshot_id if accept else current_score.score_snapshot_id,
                "before": challenge["before"], "after": challenge["after"] if accept else challenge["before"],
                "evidence_ids": challenge["evidence_ids"]}
            connection.execute("INSERT INTO challenge_resolutions VALUES (?,?,?,?,?)",
                (resolution["resolution_id"], challenge_id, request_id, canonical_json(resolution), content_hash(resolution)))
            self.database._append_audit(connection, actor_id=request["actor_id"], actor_type="demo_pm",
                action="accept_reassessment" if accept else "reject_reassessment", object_type="requirement", object_id=requirement_id,
                object_revision=expected_revision, before_hash=content_hash(current_score),
                after_hash=content_hash(score) if accept else content_hash(current_score),
                reason=f"{request['rationale']}; challenge {challenge_id}; exact evidence IDs: {', '.join(challenge['evidence_ids'])}",
                request_id=request_id, result="success", run_id=challenge_id)
            connection.commit()
            return resolution

    def history(self, requirement_id: str) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT c.payload_json,r.payload_json AS resolution_json FROM requirement_challenges c LEFT JOIN challenge_resolutions r ON r.challenge_id=c.challenge_id WHERE c.requirement_id=? ORDER BY c.challenge_id",
                (requirement_id,),
            ).fetchall()
        records = []
        for row in rows:
            record = json.loads(row["payload_json"])
            record["resolution"] = json.loads(row["resolution_json"]) if row["resolution_json"] else None
            records.append(record)
        return sorted(records, key=lambda record: record["created_at"])
