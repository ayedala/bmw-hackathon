from __future__ import annotations

from typing import Any

from .contracts import FeedbackRecord, RequirementRevision, Signal, SourceDocument
from .storage import Database


EXPECTED_FEEDBACK = {
    "F70": {"annotations": 4076, "records": 2128},
    "G60": {"annotations": 5005, "records": 4000},
    "G70": {"annotations": 4690, "records": 4000},
}


def validate_database(database: Database, *, expect_supplied_shape: bool = False) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    with database.connect() as connection:
        feedback_rows = connection.execute(
            """
            SELECT f.model_code, COUNT(DISTINCT f.record_id) AS records,
                   COUNT(a.annotation_id) AS annotations
            FROM feedback_records f
            LEFT JOIN legacy_annotations a ON a.feedback_record_id=f.record_id
            GROUP BY f.model_code ORDER BY f.model_code
            """
        ).fetchall()
        feedback = {
            row["model_code"]: {
                "records": int(row["records"]),
                "annotations": int(row["annotations"]),
            }
            for row in feedback_rows
        }
        feedback_passed = (
            feedback == EXPECTED_FEEDBACK if expect_supplied_shape else bool(feedback)
        )
        checks.append(
            {
                "check": "feedback_reconciliation",
                "passed": feedback_passed,
                "detail": feedback,
            }
        )

        survey_rows = connection.execute(
            """
            SELECT json_extract(payload_json, '$.statistic_type') AS statistic_type,
                   COUNT(*) AS n
            FROM survey_observations GROUP BY statistic_type
            """
        ).fetchall()
        studies = {row["statistic_type"]: int(row["n"]) for row in survey_rows}
        expected_studies = {"mean": 185, "categorical_distribution": 206}
        checks.append(
            {
                "check": "study_reconciliation",
                "passed": studies == expected_studies if expect_supplied_shape else bool(studies),
                "detail": studies,
            }
        )

        sources = {
            row["source_id"]: SourceDocument.model_validate_json(row["payload_json"])
            for row in connection.execute(
                "SELECT source_id,payload_json FROM sources"
            ).fetchall()
        }
        records = {
            row["record_id"]: FeedbackRecord.model_validate_json(row["payload_json"])
            for row in connection.execute(
                "SELECT record_id,payload_json FROM feedback_records"
            ).fetchall()
        }
        signals = {
            row["signal_id"]: Signal.model_validate_json(row["payload_json"])
            for row in connection.execute("SELECT signal_id,payload_json FROM signals").fetchall()
        }
        citation_errors: list[str] = []
        for signal in signals.values():
            record = records.get(signal.feedback_record_id)
            if not record:
                citation_errors.append(f"{signal.signal_id}: missing feedback record")
                continue
            for index, span in enumerate(signal.evidence_spans):
                if span.record_id != record.record_id:
                    citation_errors.append(f"{signal.signal_id}:{index}: record mismatch")
                if record.redacted_text[span.start : span.end] != span.text:
                    citation_errors.append(f"{signal.signal_id}:{index}: span mismatch")
                source = sources.get(span.locator.source_id)
                if not source or source.sha256 != span.locator.source_hash:
                    citation_errors.append(f"{signal.signal_id}:{index}: source hash mismatch")
        checks.append(
            {
                "check": "citation_resolution_and_exact_spans",
                "passed": not citation_errors,
                "detail": {
                    "signals": len(signals),
                    "errors": citation_errors[:20],
                    "error_count": len(citation_errors),
                },
            }
        )

        latest_requirements = [
            RequirementRevision.model_validate_json(row["payload_json"])
            for row in connection.execute(
                """
                WITH latest AS (
                  SELECT requirement_id,MAX(revision) AS revision
                  FROM requirement_revisions GROUP BY requirement_id
                )
                SELECT r.payload_json FROM requirement_revisions r JOIN latest l
                  ON r.requirement_id=l.requirement_id AND r.revision=l.revision
                """
            ).fetchall()
        ]
        recurrence_errors: list[str] = []
        for requirement in latest_requirements:
            support_records = {
                signals[signal_id].feedback_record_id
                for signal_id in requirement.supporting_signal_ids
                if signal_id in signals
            }
            counter_records = {
                signals[signal_id].feedback_record_id
                for signal_id in requirement.counter_signal_ids
                if signal_id in signals
            } - support_records
            missing_signal_ids = (
                set(requirement.supporting_signal_ids)
                | set(requirement.counter_signal_ids)
            ) - set(signals)
            if missing_signal_ids:
                recurrence_errors.append(
                    f"{requirement.requirement_id}: {len(missing_signal_ids)} missing signal IDs"
                )
            if len(support_records) != requirement.support_count:
                recurrence_errors.append(
                    f"{requirement.requirement_id}: support count does not use unique feedback IDs"
                )
            if len(counter_records) != requirement.counter_count:
                recurrence_errors.append(
                    f"{requirement.requirement_id}: counter count does not use unique feedback IDs"
                )
            if requirement.evidence_links:
                linked_ids = {link.signal_id for link in requirement.evidence_links}
                expected_ids = (
                    set(requirement.supporting_signal_ids)
                    | set(requirement.counter_signal_ids)
                    | set(requirement.context_signal_ids)
                )
                if linked_ids != expected_ids:
                    recurrence_errors.append(
                        f"{requirement.requirement_id}: evidence links do not cover signal IDs"
                    )
                for link in requirement.evidence_links:
                    signal = signals.get(link.signal_id)
                    if signal is None or not any(
                        span.locator == link.locator
                        and span.text == link.locator.exact_quote
                        for span in signal.evidence_spans
                    ):
                        recurrence_errors.append(
                            f"{requirement.requirement_id}: unresolved evidence link {link.signal_id}"
                        )
                    expected_role = (
                        "supports" if link.signal_id in requirement.supporting_signal_ids
                        else "preserves" if link.signal_id in requirement.counter_signal_ids
                        else "context"
                    )
                    if link.role != expected_role:
                        recurrence_errors.append(
                            f"{requirement.requirement_id}: incorrect evidence role {link.signal_id}"
                        )
        checks.append(
            {
                "check": "unique_id_recurrence",
                "passed": not recurrence_errors,
                "detail": {
                    "requirements": len(latest_requirements),
                    "errors": recurrence_errors,
                },
            }
        )

        uncertainty_errors = [
            requirement.requirement_id
            for requirement in latest_requirements
            if requirement.feasibility != "unknown" or requirement.implementation_cost is not None
        ]
        checks.append(
            {
                "check": "unavailable_engineering_dimensions_remain_unknown",
                "passed": not uncertainty_errors,
                "detail": {"violating_requirements": uncertainty_errors},
            }
        )

    audit_valid, checkpoint = database.verify_audit_chain()
    checks.append(
        {
            "check": "audit_chain",
            "passed": audit_valid,
            "detail": {"checkpoint": checkpoint},
        }
    )
    return {"passed": all(item["passed"] for item in checks), "checks": checks}
