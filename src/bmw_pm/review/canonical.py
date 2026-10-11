"""Explicit, reproducible adapter from canonical research to PM review objects.

Reading the canonical view never writes to a database. Importing freezes the
source artifacts, links, initial revision and Python CRPS in one transaction.
It never overwrites an existing PM revision or silently substitutes demo data.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

from ..contracts import (
    AcceptanceProposal, CriterionInput, EvidenceReference, RequirementRevision,
    RequirementScope, ScoreSnapshot,
)
from ..decision.crps import (
    COMPETITOR_BRANDS, FUTURE_SUBTOPICS, compute_competitive_gap, compute_crps,
    compute_decision_confidence, compute_evidence_strength, compute_frequency,
    compute_future_relevance, compute_market_relevance, compute_strategic_fit, load_policy,
)
from ..decision.requirement_quality import validate_requirement_quality
from ..storage import Database
from ..storage.database import WorkflowError
from ..utils import canonical_json, content_hash, sha256_bytes, stable_id

ROOT = Path(__file__).resolve().parents[3]
PROCESSED_PATH = Path("src/bmw_pm/data_pipeline/web_research/data/processed")
ARTIFACT_FILES = {
    "evidence": ("external_evidence.jsonl", "evidence_id"),
    "findings": ("findings.jsonl", "finding_id"),
    "needs": ("customer_needs.jsonl", "need_id"),
    "requirements": ("requirements.jsonl", "requirement_id"),
    "scores": ("requirement_scores.jsonl", "requirement_id"),
}


def load_corpus(root: Path = ROOT) -> dict[str, Any]:
    """Load and validate all links; malformed or incomplete real data is an error."""
    root = Path(root)
    corpus: dict[str, Any] = {}
    hashes: dict[str, str] = {}
    for kind, (filename, identity) in ARTIFACT_FILES.items():
        path = root / PROCESSED_PATH / filename
        raw = path.read_bytes()
        hashes[filename] = sha256_bytes(raw)
        rows = []
        seen: set[str] = set()
        for line_number, line in enumerate(raw.decode("utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                if not isinstance(row, dict) or not isinstance(row.get(identity), str):
                    raise ValueError("missing artifact identity")
            except (json.JSONDecodeError, ValueError) as exc:
                raise ValueError(f"{filename}:{line_number}: invalid canonical artifact") from exc
            if row[identity] in seen:
                raise ValueError(f"{filename}: duplicate identity {row[identity]}")
            seen.add(row[identity])
            rows.append(row)
        if not rows:
            raise ValueError(f"{filename}: canonical artifact is empty")
        corpus[kind] = rows
    runs_path = root / PROCESSED_PATH.parent / "metadata/research_runs.jsonl"
    corpus["research_runs"] = []
    if runs_path.is_file():
        raw = runs_path.read_bytes()
        hashes["metadata/research_runs.jsonl"] = sha256_bytes(raw)
        for line in raw.decode("utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if not isinstance(row, dict) or not row.get("run_id"):
                    raise ValueError("research run is missing its identity")
                corpus["research_runs"].append(row)
    indexes = {
        kind: {row[identity]: row for row in corpus[kind]}
        for kind, (_, identity) in ARTIFACT_FILES.items()
    }
    for kind, links in {
        "findings": {"evidence_ids": "evidence", "contradicts": "findings"},
        "needs": {"finding_ids": "findings", "evidence_ids": "evidence"},
        "requirements": {"need_ids": "needs", "finding_ids": "findings", "evidence_ids": "evidence"},
    }.items():
        for row in corpus[kind]:
            for field, target in links.items():
                missing = set(row.get(field, [])) - indexes[target].keys()
                if missing:
                    raise ValueError(f"Dangling canonical {kind}.{field}: {sorted(missing)}")
    if indexes["scores"].keys() != indexes["requirements"].keys():
        raise ValueError("Canonical score and requirement identities do not match")
    for requirement in corpus["requirements"]:
        if not requirement.get("need_ids") or not requirement.get("evidence_ids"):
            raise ValueError("Canonical requirement must link needs and evidence")
    corpus["indexes"] = indexes
    corpus["file_hashes"] = hashes
    corpus["corpus_hash"] = content_hash(hashes)
    corpus["as_of"] = max(date.fromisoformat(row["created_at"][:10]) for row in corpus["requirements"])
    return corpus


def evidence_reference(row: dict[str, Any], role: str, corpus_hash: str) -> EvidenceReference:
    """Retain raw lineage, including unknowns, rather than inventing provenance."""
    return EvidenceReference(
        evidence_id=row["evidence_id"], evidence_kind="external_web", role=role,
        source_url=row.get("source_url"), source_title=row.get("source_title"),
        source_family=row.get("source_family"), market=row.get("market"),
        vehicle=row.get("vehicle"), topic=row.get("topic"), subtopic=row.get("subtopic"),
        published_at=row.get("published_at"), retrieved_at=row.get("retrieved_at"),
        stance=row.get("stance"), source_quality=row.get("source_quality"),
        confidence=row.get("confidence"), independence_group=row.get("independence_group"),
        duplicate_of=row.get("duplicate_of"), claim=row.get("claim", ""),
        exact_text=row["evidence_text"], source_start_char=row.get("source_start_char"),
        source_end_char=row.get("source_end_char"),
        source_locator={"type": "url_span", "source_url": row.get("source_url"),
                        "start": row.get("source_start_char"), "end": row.get("source_end_char")},
        provenance={
            "origin": "canonical_web_research", "corpus_hash": corpus_hash,
            "artifact": str(PROCESSED_PATH / "external_evidence.jsonl"),
            "payload_hash": content_hash(row), "run_id": row.get("run_id"),
            "run_provenance": row.get("run_provenance"), "source_record": row,
            "span_status": "captured_span_preserved_not_refetched",
            "limitations": [] if row.get("run_id") else [
                "Extraction run ID was not retained by this artifact; import identity is not an extraction run."
            ],
        },
    )


def build_score(
    requirement: RequirementRevision,
    supporting: list[dict[str, Any]],
    contradicting: list[dict[str, Any]],
    *, run_id: str, corpus_hash: str, today: date,
    customer_impact: CriterionInput | None = None,
) -> ScoreSnapshot:
    """Calculate the seven-factor score with explicit, conservative unknowns."""
    strength = compute_evidence_strength(supporting, contradicting, today=today)
    rows = supporting + contradicting
    bmw = [row for row in rows if str(row.get("brand", "")).lower() == "bmw"]
    competitors = [row for row in rows if str(row.get("brand", "")).lower() in COMPETITOR_BRANDS]
    gap, detail = compute_competitive_gap(bmw, competitors)
    factors = {
        "customer_impact": customer_impact or CriterionInput(missing_reason="No reviewed customer impact input."),
        "evidence_strength": strength.as_criterion(),
        "frequency": compute_frequency(),
        "market_relevance": compute_market_relevance(rows),
        "competitive_gap": gap,
        "future_relevance": compute_future_relevance(supporting),
        "strategic_fit": compute_strategic_fit(),
    }
    result = compute_crps(factors)
    ids = list(dict.fromkeys(row["evidence_id"] for row in rows))
    factor_ids = {
        "customer_impact": [],  # authored judgment, not a fabricated evidence-derived effect
        "evidence_strength": ids, "frequency": [], "market_relevance": ids,
        "competitive_gap": list(dict.fromkeys(row["evidence_id"] for row in bmw + competitors)),
        "future_relevance": [row["evidence_id"] for row in supporting
                             if not row.get("duplicate_of") and (row.get("topic") == "market_trend"
                                 or row.get("subtopic") in FUTURE_SUBTOPICS)],
        "strategic_fit": [],
    }
    payload = {
        "result": asdict(result), "confidence": asdict(compute_decision_confidence(strength)),
        "evidence_strength": asdict(strength), "competitive_gap": detail,
        "factor_evidence_ids": factor_ids, "calculated_at": today.isoformat(),
    }
    # DimensionInterval is a Pydantic model nested inside the dataclass.
    payload["result"]["dimension_intervals"] = {
        name: interval.model_dump(mode="json") for name, interval in result.dimension_intervals.items()
    }
    return ScoreSnapshot(
        score_snapshot_id=stable_id("crps", requirement.requirement_id, str(requirement.revision),
                                    corpus_hash, content_hash(payload)),
        requirement_id=requirement.requirement_id, requirement_revision=requirement.revision,
        policy_id=result.policy_id, policy_revision=result.policy_revision,
        profile_id="g60_de_2030", profile_revision=1, corpus_manifest_hash=corpus_hash,
        criterion_inputs=factors,
        contributions={name: (factor.lower_contribution, factor.upper_contribution)
                       for name, factor in result.factors.items()},
        dimension_intervals=result.dimension_intervals,
        lower_bound=result.crps_100_lower, upper_bound=result.crps_100_upper,
        scope=requirement.scope,
        coverage={"crps": payload, "evidence_ids": ids, "source": "canonical_research",
                  "population_denominator": None},
        feasibility_status=requirement.feasibility, assumptions=requirement.assumptions,
        run_id=run_id,
    )


def _candidates(corpus: dict[str, Any]) -> list[dict[str, Any]]:
    index = corpus["indexes"]
    candidates = []
    run_id = f"canonical-import-{corpus['corpus_hash'][:20]}"
    for artifact in corpus["requirements"]:
        needs = [index["needs"][identity] for identity in artifact["need_ids"]]
        finding_ids = list(dict.fromkeys(artifact["finding_ids"] + [
            identity for need in needs for identity in need["finding_ids"]
        ]))
        findings = [index["findings"][identity] for identity in finding_ids]
        evidence_ids = list(dict.fromkeys(artifact["evidence_ids"] + [
            identity for finding in findings for identity in finding["evidence_ids"]
        ]))
        opposing_ids = {identity for finding in findings for opposing in finding.get("contradicts", [])
                        for identity in index["findings"][opposing]["evidence_ids"]}
        ambiguous = set(evidence_ids) & opposing_ids
        roles = {identity: "context" if identity in ambiguous else "supports" for identity in evidence_ids}
        roles.update({identity: "opposes" for identity in opposing_ids - set(evidence_ids)})
        refs = [evidence_reference(index["evidence"][identity], role, corpus["corpus_hash"])
                for identity, role in sorted(roles.items())]
        missing = list(artifact.get("missing_evidence", []))
        if ambiguous:
            missing.append(f"{len(ambiguous)} evidence rows reached through both supporting and contradictory findings; "
                           "kept as context pending requirement-relative human judgment.")
        requirement = RequirementRevision(
            requirement_id=artifact["requirement_id"], revision=1,
            title=artifact["title"], customer_outcome=artifact["requirement"],
            scope=RequirementScope(models=["BMW 5 Series successor"], countries=["DE"], powertrains=[],
                                   use_cases=[need["customer_context"] for need in needs]),
            use_conditions=[need["customer_context"] for need in needs],
            acceptance_proposal=AcceptanceProposal(method=artifact["validation_method"]),
            target_status="pending_engineering_review", supporting_signal_ids=[], counter_signal_ids=[],
            evidence_references=refs, topic=artifact["topic"], planning_horizon="2030",
            need_ids=artifact["need_ids"], finding_ids=finding_ids,
            canonical_provenance={"corpus_hash": corpus["corpus_hash"], "artifact": artifact,
                                  "need_artifacts": needs, "finding_artifacts": findings,
                                  "legacy_score_artifact": index["scores"][artifact["requirement_id"]],
                                  "import_run_id": run_id},
            alternatives=[], assumptions=list(artifact.get("assumptions", [])), missing_evidence=missing,
            feasibility="unknown", lifecycle_status="needs_review", created_by="canonical_research_import",
            created_at=datetime.fromisoformat(artifact["created_at"].replace("Z", "+00:00")),
            denominator_feedback_records=0, processed_feedback_records=0,
            support_count=sum(ref.role == "supports" for ref in refs),
            counter_count=sum(ref.role == "opposes" for ref in refs),
            evidence_synthesis=[need["rationale"] for need in needs],
        )
        supporting = [index["evidence"][ref.evidence_id] for ref in refs if ref.role == "supports"]
        opposing = [index["evidence"][ref.evidence_id] for ref in refs if ref.role == "opposes"]
        authored_impact = index["scores"][artifact["requirement_id"]].get("components_0_to_4", {}).get("customer_impact")
        impact = (CriterionInput(value=authored_impact, basis="Authored impact judgment from the canonical score "
                                 "artifact; unapproved, not a measured customer effect.")
                  if authored_impact is not None else None)
        score = build_score(requirement, supporting, opposing, run_id=run_id,
                            corpus_hash=corpus["corpus_hash"], today=corpus["as_of"], customer_impact=impact)
        quality = validate_requirement_quality(artifact, needs, findings,
                    [index["evidence"][identity] for identity in evidence_ids],
                    peer_requirements=corpus["requirements"]).as_dict()
        candidates.append({"requirement": requirement, "score": score, "quality": quality,
                           "lineage": {"need_ids": artifact["need_ids"], "finding_ids": finding_ids,
                                       "evidence_ids": list(roles)}})
    return candidates


def canonical_view(root: Path = ROOT) -> dict[str, Any]:
    corpus = load_corpus(root)
    return {"corpus_hash": corpus["corpus_hash"],
            "counts": {kind: len(corpus[kind]) for kind in ARTIFACT_FILES},
            "requirements": [{"requirement": item["requirement"].model_dump(mode="json"),
                              "crps": item["score"].coverage["crps"],
                              "lineage": item["lineage"], "quality": item["quality"]}
                             for item in _candidates(corpus)]}


def canonical_review_details(requirement: RequirementRevision, score: ScoreSnapshot | None,
                             judgments: dict[str, Any]) -> dict[str, Any]:
    """Current-revision quality and process gates for heterogeneous requirements."""
    provenance = requirement.canonical_provenance
    artifact = {**provenance.get("artifact", {}), "title": requirement.title,
                "requirement": requirement.customer_outcome}
    quality = validate_requirement_quality(
        artifact, provenance.get("need_artifacts", []), provenance.get("finding_artifacts", []),
        [ref.provenance.get("source_record", {}) for ref in requirement.evidence_references],
    ).as_dict()
    policy = load_policy()
    blockers = []
    if not policy.get("approved", False):
        blockers.append("CRPS policy is exploratory and has not been approved by the PM.")
    supporting = [ref for ref in requirement.evidence_references if ref.role == "supports"]
    if not supporting or any(
        ref.evidence_id not in judgments or judgments[ref.evidence_id].verdict != "supports"
        for ref in supporting
    ):
        blockers.append("Supporting claims need human entailment review.")
    if requirement.feasibility not in {"conditional", "feasible_reviewed"}:
        blockers.append("Feasibility needs a documented review or conditional acceptance.")
    if score is None:
        blockers.append("Current revision has no matching score; reassess edited content.")
    else:
        if (score.policy_id, score.policy_revision) != (policy["policy_id"], policy["revision"]):
            blockers.append("Score belongs to a different CRPS policy version.")
        missing = [key for key, value in score.criterion_inputs.items()
                   if value.value is None and value.lower_value is None]
        if missing:
            blockers.append("Missing value criteria: " + ", ".join(sorted(missing)))
    if not quality["passed"]:
        blockers.append("Requirement quality validation has unresolved blockers.")
    return {"quality": quality, "readiness": {
        "requirement_id": requirement.requirement_id, "ready_for_commitment": not blockers,
        "blockers": blockers, "interpretation": "Process safeguards, not measured recommendation quality."
    }}


def import_canonical(database: Database, *, actor_id: str, request_id: str,
                     rationale: str, root: Path = ROOT) -> dict[str, Any]:
    """Atomically persist immutable artifacts, revision one and score snapshots."""
    if not all(value.strip() for value in (actor_id, request_id, rationale)):
        raise ValueError("Canonical import requires actor, request ID and rationale")
    corpus = load_corpus(root)
    candidates = _candidates(corpus)
    fingerprint = content_hash({"corpus": corpus["corpus_hash"], "actor": actor_id, "rationale": rationale})
    run_id = f"canonical-import-{corpus['corpus_hash'][:20]}"
    database.initialize()
    created, preserved = [], []
    with database.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        existing = database._existing_event(connection, request_id)
        if existing and (existing.after_hash != fingerprint or existing.action != "import_canonical"):
            raise WorkflowError("Import request ID already refers to different input")
        if existing:
            return {"corpus_hash": corpus["corpus_hash"], "requirement_ids": [
                item["requirement"].requirement_id for item in candidates], "created": [],
                "preserved": [item["requirement"].requirement_id for item in candidates], "replayed": True}

        def audit(action: str, kind: str, identity: str, payload: Any, reason: str,
                  revision: int | None = None) -> None:
            digest = content_hash(payload)
            database._append_audit(connection, actor_id=actor_id, actor_type="demo_pm",
                action=action, object_type=kind, object_id=identity, object_revision=revision,
                before_hash=None, after_hash=digest, reason=reason,
                request_id=f"{run_id}:{action}:{identity}:{digest[:16]}", result="success", run_id=run_id)

        actions = {"evidence": "evidence_import", "findings": "finding_generation_import",
                   "needs": "need_derivation_import", "requirements": "requirement_artifact_import",
                   "scores": "legacy_score_artifact_import", "research_runs": "research_run_import"}
        for kind in (*ARTIFACT_FILES, "research_runs"):
            identity_field = ARTIFACT_FILES[kind][1] if kind in ARTIFACT_FILES else "run_id"
            for row in corpus[kind]:
                identity = row[identity_field]
                key = f"{corpus['corpus_hash']}:{kind}:{identity}"
                inserted = database._insert_immutable(connection, "canonical_artifacts", "artifact_key", key,
                    {"artifact_key": key, "corpus_hash": corpus["corpus_hash"], "artifact_kind": kind,
                     "artifact_id": identity, "payload_json": canonical_json(row), "payload_hash": content_hash(row)})
                if inserted:
                    audit(actions[kind], kind, identity, row,
                          "Imported existing canonical artifact with its original lineage; no research or generation was rerun.")
        for item in candidates:
            requirement, score = item["requirement"], item["score"]
            existing_requirement = connection.execute(
                "SELECT revision FROM requirement_revisions WHERE requirement_id=? ORDER BY revision DESC LIMIT 1",
                (requirement.requirement_id,),
            ).fetchone()
            if existing_requirement:
                preserved.append(requirement.requirement_id)
                continue
            connection.execute("INSERT INTO requirement_revisions "
                "(requirement_id,revision,lifecycle_status,payload_json,payload_hash) VALUES (?,?,?,?,?)",
                (requirement.requirement_id, requirement.revision, requirement.lifecycle_status,
                 requirement.model_dump_json(), content_hash(requirement)))
            audit("create_requirement_candidate", "requirement", requirement.requirement_id, requirement,
                  "Created canonical web requirement; external references retain their own provenance and remain unreviewed.", 1)
            database._insert_immutable(connection, "score_snapshots", "score_snapshot_id", score.score_snapshot_id,
                {"score_snapshot_id": score.score_snapshot_id, "requirement_id": score.requirement_id,
                 "requirement_revision": score.requirement_revision, "lower_bound": score.lower_bound,
                 "upper_bound": score.upper_bound, "run_id": score.run_id,
                 "payload_json": score.model_dump_json(), "payload_hash": content_hash(score)})
            audit("score_requirement", "score_snapshot", score.score_snapshot_id, score,
                  "Python seven-factor CRPS; page counts are not prevalence; unknowns retain their intervals.", 1)
            created.append(requirement.requirement_id)
        audit("research_import_manifest", "research_import", run_id,
              {"hashes": corpus["file_hashes"], "as_of": corpus["as_of"].isoformat()},
              "Artifact import context, not an invented extraction run. Original run IDs remain unknown where absent.")
        database._append_audit(connection, actor_id=actor_id, actor_type="demo_pm", action="import_canonical",
            object_type="canonical_corpus", object_id=corpus["corpus_hash"], object_revision=None,
            before_hash=None, after_hash=fingerprint, reason=rationale, request_id=request_id,
            result="success", run_id=run_id)
        connection.commit()
    return {"corpus_hash": corpus["corpus_hash"], "requirement_ids": [
        item["requirement"].requirement_id for item in candidates], "created": created,
        "preserved": preserved, "replayed": False}
