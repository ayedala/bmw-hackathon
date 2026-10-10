from __future__ import annotations

import json
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Sequence
from uuid import uuid4

from .contracts import CriterionInput, PolicyVersion, RunManifest
from .decision import assess_ranking, reach_input, score_requirement
from .ingestion import CustomerStudyWorkbookAdapter, FeedbackWorkbookAdapter
from .intelligence.provider import ExtractionProvider
from .intelligence.requirements import build_requirement_candidates
from .storage import Database
from .utils import content_hash, utc_now


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def ingest_supplied_data(
    *,
    database: Database,
    input_dir: str | Path,
    profile: dict[str, Any],
) -> dict[str, Any]:
    root = Path(input_dir)
    feedback_adapter = FeedbackWorkbookAdapter(
        powertrain_aliases=profile.get("powertrain_aliases", {}),
        alias_assumptions=profile.get("alias_assumptions", {}),
    )
    report: dict[str, Any] = {"feedback": {}, "studies": {}}
    for model in ("F70", "G60", "G70"):
        path = root / f"{model}_feedback_hackathon.xlsx"
        if not path.exists():
            raise FileNotFoundError(path)
        batch = feedback_adapter.parse(path, model_code=model)
        event = database.persist_feedback_ingestion(
            batch,
            request_id=f"ingest:{batch.source.sha256}",
        )
        report["feedback"][model] = {
            "source_sha256": batch.source.sha256,
            "annotation_rows": batch.input_annotation_rows,
            "unique_feedback_ids": batch.input_unique_ids,
            "accepted_feedback_ids": len(batch.records),
            "legacy_annotations": len(batch.annotations),
            "quarantined_feedback_ids": len(batch.quarantined),
            "audit_result": event.result,
        }
    study_path = root / "F70_G60_G68_G70_customer_studies.xlsx"
    if not study_path.exists():
        raise FileNotFoundError(study_path)
    study_batch = CustomerStudyWorkbookAdapter().parse(study_path)
    event = database.persist_study_ingestion(
        study_batch,
        request_id=f"ingest:{study_batch.source.sha256}",
    )
    report["studies"] = {
        "source_sha256": study_batch.source.sha256,
        "mean_observations": sum(
            item.statistic_type == "mean" for item in study_batch.observations
        ),
        "distribution_observations": sum(
            item.statistic_type == "categorical_distribution"
            for item in study_batch.observations
        ),
        "quarantined_blocks": len(study_batch.quarantined),
        "respondent_counts_available": False,
        "audit_result": event.result,
    }
    return report


def deterministic_stratified_sample(records: Sequence[Any], limit: int) -> list[Any]:
    buckets: dict[tuple[str, str], deque[Any]] = defaultdict(deque)
    for record in sorted(records, key=lambda item: item.record_id):
        buckets[(record.source_label or "unknown", record.powertrain or "unknown")].append(record)
    ordered_keys = sorted(buckets)
    sample: list[Any] = []
    while len(sample) < limit and any(buckets.values()):
        for key in ordered_keys:
            if buckets[key] and len(sample) < limit:
                sample.append(buckets[key].popleft())
    return sample


def run_candidate_pipeline(
    *,
    database: Database,
    profile: dict[str, Any],
    policy: PolicyVersion,
    provider: ExtractionProvider,
    limit: int | None = None,
) -> dict[str, Any]:
    eligible = database.feedback_records(
        model_code=profile["model_family"],
        countries=profile.get("countries"),
        powertrains=profile.get("powertrains"),
    )
    if not eligible:
        raise ValueError("no eligible feedback records found; run ingestion first")
    if provider.descriptor.mode == "live_ai":
        if limit is None:
            raise ValueError("live AI extraction requires an explicit --limit (maximum 50)")
        if limit > 50:
            raise ValueError("live AI extraction is capped at 50 records for this MVP")
    selected = (
        deterministic_stratified_sample(eligible, min(limit, len(eligible)))
        if limit is not None
        else list(eligible)
    )
    run_id = f"run_{uuid4().hex}"
    started_at = utc_now()
    corpus_manifest_hash = content_hash(
        {
            "eligible_record_ids": [record.record_id for record in eligible],
            "selected_record_ids": [record.record_id for record in selected],
            "profile_id": profile["profile_id"],
            "profile_revision": profile["revision"],
        }
    )
    signals = provider.extract(selected, run_id=run_id)
    candidates = build_requirement_candidates(
        signals=signals,
        eligible_records=eligible,
        processed_record_ids={record.record_id for record in selected},
        profile=profile,
        created_by=provider.descriptor.name,
    )
    inserted_signals = database.persist_signals(signals)
    scores = []
    stored_candidates = []
    for candidate in candidates:
        stored = database.ensure_requirement(
            candidate,
            request_id=f"{run_id}:requirement:{candidate.requirement_id}",
            run_id=run_id,
        )
        report_items = database.report_context_for_requirement(stored)
        public_items = database.public_evidence_for_requirement(stored)
        inputs = {
            "customer_impact": CriterionInput(
                missing_reason="No reviewed impact-rubric rating exists; keyword or model extraction is not a severity measurement."
            ),
            "evidence_backed_reach": reach_input(
                support_count=stored.support_count,
                eligible_count=stored.denominator_feedback_records,
                processed_count=stored.processed_feedback_records,
                saturation_share=policy.saturation_share,
            ),
            "strategic_contribution": CriterionInput(
                missing_reason="No PM-approved product objective or causal contribution rating is supplied."
            ),
            "competitive_outlook_need": CriterionInput(
                missing_reason="No matched competitive benchmark or approved outlook scenario is linked."
            ),
        }
        score = score_requirement(
            requirement=stored,
            policy=policy,
            criterion_inputs=inputs,
            profile_id=profile["profile_id"],
            profile_revision=profile["revision"],
            corpus_manifest_hash=corpus_manifest_hash,
            run_id=run_id,
            # Report context is cited for review, not converted into a score.
            extra_assumptions=[
                *profile.get("notes", []),
                *(["Report context for PM review (not scored): " + ", ".join(
                    item["context_id"] for item in report_items
                )] if report_items else []),
                *(["Public evidence snapshots for PM review (not scored): " + ", ".join(
                    item["record_id"] for item in public_items
                )] if public_items else []),
            ],
        )
        database.persist_score(score, request_id=f"{run_id}:score:{score.score_snapshot_id}")
        stored_candidates.append(stored)
        scores.append(score)
    manifest = RunManifest(
        run_id=run_id,
        started_at=started_at,
        finished_at=utc_now(),
        dataset_hashes=sorted(
            {
                record.row_locators[0].source_hash
                for record in eligible
                if record.row_locators
            }
        ),
        corpus_manifest_hash=corpus_manifest_hash,
        provider=provider.descriptor,
        profile_id=profile["profile_id"],
        profile_revision=profile["revision"],
        policy_id=policy.policy_id,
        policy_revision=policy.revision,
        statuses={
            "eligible_feedback_records": len(eligible),
            "processed_feedback_records": len(selected),
            "validated_signals": len(signals),
            "new_signals": inserted_signals,
            "requirement_candidates": len(stored_candidates),
            "execution_mode": provider.descriptor.mode,
        },
    )
    database.persist_run(manifest)
    return {
        "run": manifest.model_dump(mode="json"),
        "requirements": [item.model_dump(mode="json") for item in stored_candidates],
        "scores": [item.model_dump(mode="json") for item in scores],
        "ranking_assessment": assess_ranking(scores),
        "limitations": [
            "No model-quality or customer-prevalence claim is made by this run.",
            "Study observations are ingested as separate context and are not pooled into feedback recurrence.",
            "Feasibility, cost, strategic contribution, and competitive/outlook need remain unknown.",
            "Exact evidence spans are checked, but claim entailment and author expertise are not verified.",
            "The lower-bound list order is exploratory; overlapping score ranges do not establish a strict preference.",
        ],
    }
