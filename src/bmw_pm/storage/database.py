"""SQLite persistence, immutable revisions and an append-only chained application audit trail."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence
from uuid import uuid4

from ..contracts import (
    AuditEvent,
    Decision,
    DecisionAction,
    FeedbackIngestionResult,
    FeedbackRecord,
    RequirementRevision,
    RunManifest,
    ScoreSnapshot,
    Signal,
    StudyIngestionResult,
)
from ..utils import canonical_json, content_hash, sha256_bytes, utc_now


class RevisionConflict(RuntimeError):
    pass


class WorkflowError(RuntimeError):
    pass


SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    source_id TEXT PRIMARY KEY,
    sha256 TEXT NOT NULL UNIQUE,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS feedback_records (
    record_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    source_record_id TEXT NOT NULL,
    model_code TEXT,
    country TEXT,
    powertrain TEXT,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE(source_id, source_record_id)
);
CREATE TABLE IF NOT EXISTS legacy_annotations (
    annotation_id TEXT PRIMARY KEY,
    feedback_record_id TEXT NOT NULL REFERENCES feedback_records(record_id),
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS transformations (
    transformation_id TEXT PRIMARY KEY,
    feedback_record_id TEXT NOT NULL REFERENCES feedback_records(record_id),
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS survey_observations (
    survey_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    market TEXT NOT NULL,
    model TEXT NOT NULL,
    category_raw TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ingestion_findings (
    finding_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS signals (
    signal_id TEXT PRIMARY KEY,
    feedback_record_id TEXT NOT NULL REFERENCES feedback_records(record_id),
    need_domain TEXT NOT NULL,
    polarity TEXT NOT NULL,
    run_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS requirement_revisions (
    requirement_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    lifecycle_status TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    PRIMARY KEY(requirement_id, revision)
);
CREATE TABLE IF NOT EXISTS score_snapshots (
    score_snapshot_id TEXT PRIMARY KEY,
    requirement_id TEXT NOT NULL,
    requirement_revision INTEGER NOT NULL,
    lower_bound REAL NOT NULL,
    upper_bound REAL NOT NULL,
    run_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    FOREIGN KEY(requirement_id, requirement_revision)
      REFERENCES requirement_revisions(requirement_id, revision)
);
CREATE TABLE IF NOT EXISTS decisions (
    decision_id TEXT PRIMARY KEY,
    requirement_id TEXT NOT NULL,
    requirement_revision INTEGER NOT NULL,
    action TEXT NOT NULL,
    request_id TEXT NOT NULL UNIQUE,
    recorded_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    FOREIGN KEY(requirement_id, requirement_revision)
      REFERENCES requirement_revisions(requirement_id, revision)
);
CREATE TABLE IF NOT EXISTS run_manifests (
    run_id TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_events (
    monotonic_sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    recorded_at TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    action TEXT NOT NULL,
    object_type TEXT NOT NULL,
    object_id TEXT NOT NULL,
    object_revision INTEGER,
    request_id TEXT NOT NULL UNIQUE,
    previous_event_hash TEXT NOT NULL,
    event_hash TEXT NOT NULL,
    result TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_feedback_scope
  ON feedback_records(model_code, country, powertrain);
CREATE TABLE IF NOT EXISTS priority_assessments (
    assessment_id TEXT PRIMARY KEY,
    requirement_id TEXT NOT NULL,
    requirement_revision INTEGER NOT NULL,
    sequence INTEGER NOT NULL,
    request_id TEXT NOT NULL UNIQUE,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    UNIQUE(requirement_id, requirement_revision, sequence),
    FOREIGN KEY(requirement_id,requirement_revision) REFERENCES requirement_revisions(requirement_id,revision)
);
CREATE TRIGGER IF NOT EXISTS priorities_no_update BEFORE UPDATE ON priority_assessments
BEGIN SELECT RAISE(ABORT, 'priorities are immutable'); END;
CREATE TRIGGER IF NOT EXISTS priorities_no_delete BEFORE DELETE ON priority_assessments
BEGIN SELECT RAISE(ABORT, 'priorities are immutable'); END;
CREATE INDEX IF NOT EXISTS ix_signals_domain ON signals(need_domain);
CREATE INDEX IF NOT EXISTS ix_requirements_latest
  ON requirement_revisions(requirement_id, revision DESC);
CREATE TRIGGER IF NOT EXISTS audit_events_no_update
BEFORE UPDATE ON audit_events
BEGIN SELECT RAISE(ABORT, 'audit_events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_events_no_delete
BEFORE DELETE ON audit_events
BEGIN SELECT RAISE(ABORT, 'audit_events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS requirement_revisions_no_update
BEFORE UPDATE ON requirement_revisions
BEGIN SELECT RAISE(ABORT, 'requirement revisions are immutable'); END;
CREATE TRIGGER IF NOT EXISTS requirement_revisions_no_delete
BEFORE DELETE ON requirement_revisions
BEGIN SELECT RAISE(ABORT, 'requirement revisions are immutable'); END;
"""


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
        finally:
            connection.close()

    @staticmethod
    def _ensure_source(connection: sqlite3.Connection, source: Any) -> bool:
        row = connection.execute(
            "SELECT sha256 FROM sources WHERE source_id=?", (source.source_id,)
        ).fetchone()
        if row:
            if row["sha256"] != source.sha256:
                raise WorkflowError(f"source identity collision for {source.source_id}")
            return False
        connection.execute(
            """
            INSERT INTO sources (source_id,sha256,payload_json,payload_hash)
            VALUES (?,?,?,?)
            """,
            (
                source.source_id,
                source.sha256,
                source.model_dump_json(),
                content_hash(source),
            ),
        )
        return True

    @staticmethod
    def _insert_immutable(
        connection: sqlite3.Connection,
        table: str,
        key_column: str,
        key_value: str,
        columns: dict[str, Any],
    ) -> bool:
        row = connection.execute(
            f"SELECT payload_hash FROM {table} WHERE {key_column} = ?", (key_value,)
        ).fetchone()
        if row:
            if row["payload_hash"] != columns["payload_hash"]:
                raise WorkflowError(f"immutable {table} identity collision for {key_value}")
            return False
        names = list(columns)
        placeholders = ",".join("?" for _ in names)
        connection.execute(
            f"INSERT INTO {table} ({','.join(names)}) VALUES ({placeholders})",
            tuple(columns[name] for name in names),
        )
        return True

    @staticmethod
    def _existing_event(
        connection: sqlite3.Connection, request_id: str
    ) -> AuditEvent | None:
        row = connection.execute(
            "SELECT payload_json FROM audit_events WHERE request_id = ?", (request_id,)
        ).fetchone()
        return AuditEvent.model_validate_json(row["payload_json"]) if row else None

    @staticmethod
    def _event_hash_payload(event: AuditEvent | dict[str, Any]) -> str:
        data = (
            event.model_dump(mode="json")
            if isinstance(event, AuditEvent)
            else dict(event)
        )
        data.pop("event_hash", None)
        return sha256_bytes(canonical_json(data).encode("utf-8"))

    def _append_audit(
        self,
        connection: sqlite3.Connection,
        *,
        actor_id: str,
        actor_type: str,
        action: str,
        object_type: str,
        object_id: str,
        object_revision: int | None,
        before_hash: str | None,
        after_hash: str | None,
        reason: str,
        request_id: str,
        result: str,
        run_id: str | None = None,
    ) -> AuditEvent:
        existing = self._existing_event(connection, request_id)
        if existing:
            return existing
        previous = connection.execute(
            "SELECT monotonic_sequence, event_hash FROM audit_events ORDER BY monotonic_sequence DESC LIMIT 1"
        ).fetchone()
        sequence = (previous["monotonic_sequence"] + 1) if previous else 1
        previous_hash = previous["event_hash"] if previous else "GENESIS"
        event_data = {
            "schema_version": "1",
            "event_id": f"evt_{uuid4().hex}",
            "monotonic_sequence": sequence,
            "recorded_at": utc_now(),
            "actor_id": actor_id,
            "actor_type": actor_type,
            "action": action,
            "object_type": object_type,
            "object_id": object_id,
            "object_revision": object_revision,
            "before_hash": before_hash,
            "after_hash": after_hash,
            "reason": reason,
            "request_id": request_id,
            "run_id": run_id,
            "previous_event_hash": previous_hash,
            "event_hash": "",
            "result": result,
        }
        event = AuditEvent.model_validate(event_data)
        event = event.model_copy(update={"event_hash": self._event_hash_payload(event)})
        connection.execute(
            """
            INSERT INTO audit_events (
              monotonic_sequence,event_id,recorded_at,actor_id,action,object_type,
              object_id,object_revision,request_id,previous_event_hash,event_hash,result,payload_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                event.monotonic_sequence,
                event.event_id,
                event.recorded_at.isoformat(),
                event.actor_id,
                event.action,
                event.object_type,
                event.object_id,
                event.object_revision,
                event.request_id,
                event.previous_event_hash,
                event.event_hash,
                event.result,
                event.model_dump_json(),
            ),
        )
        return event

    def persist_feedback_ingestion(
        self,
        batch: FeedbackIngestionResult,
        *,
        request_id: str,
        actor_id: str = "pipeline",
    ) -> AuditEvent:
        self.initialize()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = self._existing_event(connection, request_id)
            if existing:
                connection.rollback()
                return existing
            self._ensure_source(connection, batch.source)
            new_records = 0
            for record in batch.records:
                payload = record.model_dump_json()
                new_records += self._insert_immutable(
                    connection,
                    "feedback_records",
                    "record_id",
                    record.record_id,
                    {
                        "record_id": record.record_id,
                        "source_id": record.source_id,
                        "source_record_id": record.source_record_id,
                        "model_code": record.model_code,
                        "country": record.country,
                        "powertrain": record.powertrain,
                        "payload_json": payload,
                        "payload_hash": content_hash(record),
                    },
                )
            for annotation in batch.annotations:
                self._insert_immutable(
                    connection,
                    "legacy_annotations",
                    "annotation_id",
                    annotation.annotation_id,
                    {
                        "annotation_id": annotation.annotation_id,
                        "feedback_record_id": annotation.feedback_record_id,
                        "payload_json": annotation.model_dump_json(),
                        "payload_hash": content_hash(annotation),
                    },
                )
            for transformation in batch.transformations:
                self._insert_immutable(
                    connection,
                    "transformations",
                    "transformation_id",
                    transformation.transformation_id,
                    {
                        "transformation_id": transformation.transformation_id,
                        "feedback_record_id": transformation.record_id,
                        "payload_json": transformation.model_dump_json(),
                        "payload_hash": content_hash(transformation),
                    },
                )
            for finding in batch.quarantined:
                finding_id = sha256_bytes(
                    canonical_json(finding.model_dump(mode="json")).encode("utf-8")
                )
                self._insert_immutable(
                    connection,
                    "ingestion_findings",
                    "finding_id",
                    finding_id,
                    {
                        "finding_id": finding_id,
                        "source_id": finding.source_id,
                        "payload_json": finding.model_dump_json(),
                        "payload_hash": content_hash(finding),
                    },
                )
            event = self._append_audit(
                connection,
                actor_id=actor_id,
                actor_type="pipeline",
                action="ingest_feedback_source",
                object_type="source",
                object_id=batch.source.source_id,
                object_revision=None,
                before_hash=None,
                after_hash=batch.source.sha256,
                reason=(
                    f"Accepted {len(batch.records)} unique feedback IDs from "
                    f"{batch.input_annotation_rows} annotation rows; quarantined "
                    f"{len(batch.quarantined)} IDs; {new_records} records were new."
                ),
                request_id=request_id,
                result="success" if new_records else "noop",
            )
            connection.commit()
            return event

    def persist_study_ingestion(
        self,
        batch: StudyIngestionResult,
        *,
        request_id: str,
        actor_id: str = "pipeline",
    ) -> AuditEvent:
        self.initialize()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = self._existing_event(connection, request_id)
            if existing:
                connection.rollback()
                return existing
            self._ensure_source(connection, batch.source)
            inserted = 0
            for observation in batch.observations:
                inserted += self._insert_immutable(
                    connection,
                    "survey_observations",
                    "survey_id",
                    observation.survey_id,
                    {
                        "survey_id": observation.survey_id,
                        "source_id": observation.source_id,
                        "market": observation.market,
                        "model": observation.model,
                        "category_raw": observation.category_raw,
                        "payload_json": observation.model_dump_json(),
                        "payload_hash": content_hash(observation),
                    },
                )
            event = self._append_audit(
                connection,
                actor_id=actor_id,
                actor_type="pipeline",
                action="ingest_customer_study_source",
                object_type="source",
                object_id=batch.source.source_id,
                object_revision=None,
                before_hash=None,
                after_hash=batch.source.sha256,
                reason=(
                    f"Validated {len(batch.observations)} aggregate survey observations; "
                    f"{inserted} were new. Respondent counts remain unavailable."
                ),
                request_id=request_id,
                result="success" if inserted else "noop",
            )
            connection.commit()
            return event

    def feedback_records(
        self,
        *,
        model_code: str | None = None,
        countries: Sequence[str] | None = None,
        powertrains: Sequence[str] | None = None,
    ) -> list[FeedbackRecord]:
        clauses: list[str] = []
        params: list[Any] = []
        if model_code:
            clauses.append("model_code = ?")
            params.append(model_code)
        if countries:
            clauses.append(f"country IN ({','.join('?' for _ in countries)})")
            params.extend(countries)
        if powertrains:
            clauses.append(f"powertrain IN ({','.join('?' for _ in powertrains)})")
            params.extend(powertrains)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.connect() as connection:
            rows = connection.execute(
                f"SELECT payload_json FROM feedback_records {where} ORDER BY record_id", params
            ).fetchall()
        return [FeedbackRecord.model_validate_json(row["payload_json"]) for row in rows]

    def survey_count(self, *, model: str | None = None) -> int:
        with self.connect() as connection:
            if model:
                row = connection.execute(
                    "SELECT COUNT(*) AS n FROM survey_observations WHERE model = ?", (model,)
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT COUNT(*) AS n FROM survey_observations"
                ).fetchone()
        return int(row["n"])

    def persist_run(self, manifest: RunManifest) -> None:
        self.initialize()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._insert_immutable(
                connection,
                "run_manifests",
                "run_id",
                manifest.run_id,
                {
                    "run_id": manifest.run_id,
                    "payload_json": manifest.model_dump_json(),
                    "payload_hash": content_hash(manifest),
                },
            )
            connection.commit()

    def run_manifest(self, run_id: str) -> RunManifest | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM run_manifests WHERE run_id = ?", (run_id,)
            ).fetchone()
        return RunManifest.model_validate_json(row["payload_json"]) if row else None

    def persist_signals(self, signals: Sequence[Signal]) -> int:
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            inserted = 0
            for signal in signals:
                existing = connection.execute(
                    "SELECT payload_json FROM signals WHERE signal_id=?", (signal.signal_id,)
                ).fetchone()
                if existing:
                    previous = Signal.model_validate_json(existing["payload_json"])
                    prior_payload = previous.model_dump(mode="json")
                    next_payload = signal.model_dump(mode="json")
                    prior_payload.pop("run_id", None)
                    next_payload.pop("run_id", None)
                    if prior_payload != next_payload:
                        raise WorkflowError(
                            f"immutable signal identity collision for {signal.signal_id}"
                        )
                    continue
                connection.execute(
                    """
                    INSERT INTO signals
                      (signal_id,feedback_record_id,need_domain,polarity,run_id,payload_json,payload_hash)
                    VALUES (?,?,?,?,?,?,?)
                    """,
                    (
                        signal.signal_id,
                        signal.feedback_record_id,
                        signal.need_domain,
                        signal.polarity.value,
                        signal.run_id,
                        signal.model_dump_json(),
                        content_hash(signal),
                    ),
                )
                inserted += 1
            connection.commit()
            return inserted

    @staticmethod
    def _requirement_semantic_payload(requirement: RequirementRevision) -> dict[str, Any]:
        payload = requirement.model_dump(mode="json")
        for key in ("revision", "supersedes_revision", "created_at", "created_by"):
            payload.pop(key, None)
        return payload

    def ensure_requirement(
        self,
        requirement: RequirementRevision,
        *,
        request_id: str,
        run_id: str,
    ) -> RequirementRevision:
        self.initialize()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT payload_json FROM requirement_revisions
                WHERE requirement_id = ? ORDER BY revision DESC LIMIT 1
                """,
                (requirement.requirement_id,),
            ).fetchone()
            before_hash = None
            result = "success"
            action = "create_requirement_candidate"
            target = requirement
            if row:
                current = RequirementRevision.model_validate_json(row["payload_json"])
                if self._requirement_semantic_payload(current) == self._requirement_semantic_payload(
                    requirement
                ):
                    target = current
                    result = "noop"
                    action = "requirement_candidate_unchanged"
                else:
                    before_hash = content_hash(current)
                    target = requirement.model_copy(
                        update={
                            "revision": current.revision + 1,
                            "supersedes_revision": current.revision,
                        }
                    )
            if result != "noop":
                connection.execute(
                    """
                    INSERT INTO requirement_revisions
                      (requirement_id,revision,lifecycle_status,payload_json,payload_hash)
                    VALUES (?,?,?,?,?)
                    """,
                    (
                        target.requirement_id,
                        target.revision,
                        target.lifecycle_status,
                        target.model_dump_json(),
                        content_hash(target),
                    ),
                )
            self._append_audit(
                connection,
                actor_id="pipeline",
                actor_type="pipeline",
                action=action,
                object_type="requirement",
                object_id=target.requirement_id,
                object_revision=target.revision,
                before_hash=before_hash,
                after_hash=content_hash(target),
                reason="Candidate derived from validated signals; no product approval was applied.",
                request_id=request_id,
                result=result,
                run_id=run_id,
            )
            connection.commit()
            return target

    def persist_score(
        self, score: ScoreSnapshot, *, request_id: str
    ) -> AuditEvent:
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            inserted = self._insert_immutable(
                connection,
                "score_snapshots",
                "score_snapshot_id",
                score.score_snapshot_id,
                {
                    "score_snapshot_id": score.score_snapshot_id,
                    "requirement_id": score.requirement_id,
                    "requirement_revision": score.requirement_revision,
                    "lower_bound": score.lower_bound,
                    "upper_bound": score.upper_bound,
                    "run_id": score.run_id,
                    "payload_json": score.model_dump_json(),
                    "payload_hash": content_hash(score),
                },
            )
            event = self._append_audit(
                connection,
                actor_id="scoring_engine",
                actor_type="deterministic_service",
                action="score_requirement",
                object_type="score_snapshot",
                object_id=score.score_snapshot_id,
                object_revision=score.requirement_revision,
                before_hash=None,
                after_hash=content_hash(score),
                reason="Calculated from the recorded policy and criterion inputs.",
                request_id=request_id,
                result="success" if inserted else "noop",
                run_id=score.run_id,
            )
            connection.commit()
            return event

    def latest_requirement(self, requirement_id: str) -> RequirementRevision:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM requirement_revisions
                WHERE requirement_id = ? ORDER BY revision DESC LIMIT 1
                """,
                (requirement_id,),
            ).fetchone()
        if not row:
            raise KeyError(requirement_id)
        return RequirementRevision.model_validate_json(row["payload_json"])

    def requirement(self, requirement_id: str, revision: int) -> RequirementRevision:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM requirement_revisions WHERE requirement_id=? AND revision=?",
                (requirement_id, revision),
            ).fetchone()
        if not row:
            raise KeyError((requirement_id, revision))
        return RequirementRevision.model_validate_json(row["payload_json"])

    def latest_score(self, requirement_id: str, revision: int) -> ScoreSnapshot | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM score_snapshots
                WHERE requirement_id=? AND requirement_revision=?
                ORDER BY rowid DESC LIMIT 1
                """,
                (requirement_id, revision),
            ).fetchone()
        return ScoreSnapshot.model_validate_json(row["payload_json"]) if row else None

    def signal(self, signal_id: str) -> Signal:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM signals WHERE signal_id=?", (signal_id,)
            ).fetchone()
        if not row:
            raise KeyError(signal_id)
        return Signal.model_validate_json(row["payload_json"])

    def requirement_summaries(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                WITH latest AS (
                  SELECT requirement_id, MAX(revision) AS revision
                  FROM requirement_revisions GROUP BY requirement_id
                )
                SELECT r.payload_json,
                  (SELECT s.payload_json FROM score_snapshots s
                   WHERE s.requirement_id=r.requirement_id AND s.requirement_revision=r.revision
                   ORDER BY s.rowid DESC LIMIT 1) AS score_json,
                  (SELECT d.payload_json FROM decisions d
                   WHERE d.requirement_id=r.requirement_id AND d.requirement_revision=r.revision
                   ORDER BY d.rowid DESC LIMIT 1) AS decision_json
                FROM requirement_revisions r JOIN latest l
                  ON r.requirement_id=l.requirement_id AND r.revision=l.revision
                """
            ).fetchall()
        summaries: list[dict[str, Any]] = []
        for row in rows:
            requirement = RequirementRevision.model_validate_json(row["payload_json"])
            score = (
                ScoreSnapshot.model_validate_json(row["score_json"])
                if row["score_json"]
                else None
            )
            decision = (
                Decision.model_validate_json(row["decision_json"])
                if row["decision_json"]
                else None
            )
            summaries.append(
                {"requirement": requirement, "score": score, "decision": decision}
            )
        return sorted(
            summaries,
            key=lambda item: (
                -(item["score"].lower_bound if item["score"] else -1),
                item["requirement"].requirement_id,
            ),
        )

    def atomic_review(
        self,
        *,
        requirement_id: str,
        expected_revision: int,
        action: DecisionAction,
        rationale: str,
        actor_id: str,
        role: str,
        request_id: str,
        edited_revision: RequirementRevision | None = None,
    ) -> tuple[Decision, RequirementRevision | None]:
        self.initialize()
        conflict_message: str | None = None
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing_event = self._existing_event(connection, request_id)
            if existing_event:
                row = connection.execute(
                    "SELECT payload_json FROM decisions WHERE request_id=?", (request_id,)
                ).fetchone()
                if not row:
                    connection.rollback()
                    raise RevisionConflict(existing_event.reason)
                decision = Decision.model_validate_json(row["payload_json"])
                connection.rollback()
                return decision, None
            row = connection.execute(
                """
                SELECT payload_json FROM requirement_revisions
                WHERE requirement_id=? ORDER BY revision DESC LIMIT 1
                """,
                (requirement_id,),
            ).fetchone()
            if not row:
                connection.rollback()
                raise KeyError(requirement_id)
            current = RequirementRevision.model_validate_json(row["payload_json"])
            if current.revision != expected_revision:
                conflict_message = (
                    f"Stale review: expected revision {expected_revision}, latest is {current.revision}."
                )
                self._append_audit(
                    connection,
                    actor_id=actor_id,
                    actor_type=role,
                    action="review_revision_conflict",
                    object_type="requirement",
                    object_id=requirement_id,
                    object_revision=expected_revision,
                    before_hash=content_hash(current),
                    after_hash=None,
                    reason=conflict_message,
                    request_id=request_id,
                    result="failure",
                )
                connection.commit()
            else:
                terminal = connection.execute(
                    """
                    SELECT action FROM decisions
                    WHERE requirement_id=? AND requirement_revision=?
                      AND action IN ('approve','reject','defer')
                    ORDER BY rowid DESC LIMIT 1
                    """,
                    (requirement_id, expected_revision),
                ).fetchone()
                if terminal and action in {
                    DecisionAction.APPROVE,
                    DecisionAction.REJECT,
                    DecisionAction.DEFER,
                }:
                    connection.rollback()
                    raise WorkflowError(
                        "a final decision already exists for this revision; edit or challenge it"
                    )
                new_revision: RequirementRevision | None = None
                if action == DecisionAction.EDIT:
                    if edited_revision is None:
                        connection.rollback()
                        raise WorkflowError("edit action requires an edited revision")
                    if (
                        edited_revision.requirement_id != requirement_id
                        or edited_revision.revision != current.revision + 1
                        or edited_revision.supersedes_revision != current.revision
                    ):
                        connection.rollback()
                        raise WorkflowError("edited revision identity is inconsistent")
                    connection.execute(
                        """
                        INSERT INTO requirement_revisions
                          (requirement_id,revision,lifecycle_status,payload_json,payload_hash)
                        VALUES (?,?,?,?,?)
                        """,
                        (
                            edited_revision.requirement_id,
                            edited_revision.revision,
                            edited_revision.lifecycle_status,
                            edited_revision.model_dump_json(),
                            content_hash(edited_revision),
                        ),
                    )
                    new_revision = edited_revision
                score_row = connection.execute(
                    """
                    SELECT score_snapshot_id FROM score_snapshots
                    WHERE requirement_id=? AND requirement_revision=?
                    ORDER BY rowid DESC LIMIT 1
                    """,
                    (requirement_id, expected_revision),
                ).fetchone()
                priority_row = connection.execute(
                    "SELECT assessment_id FROM priority_assessments WHERE requirement_id=? AND requirement_revision=? ORDER BY sequence DESC LIMIT 1",
                    (requirement_id, expected_revision),
                ).fetchone()
                decision = Decision(
                    decision_id=f"decision_{uuid4().hex}",
                    requirement_id=requirement_id,
                    requirement_revision=expected_revision,
                    action=action,
                    rationale=rationale,
                    actor_id=actor_id,
                    role=role,
                    recorded_at=utc_now(),
                    score_snapshot_id=score_row["score_snapshot_id"] if score_row else None,
                    priority_assessment_id=priority_row["assessment_id"] if priority_row else None,
                    expected_revision=expected_revision,
                    request_id=request_id,
                )
                connection.execute(
                    """
                    INSERT INTO decisions
                      (decision_id,requirement_id,requirement_revision,action,request_id,
                       recorded_at,payload_json,payload_hash)
                    VALUES (?,?,?,?,?,?,?,?)
                    """,
                    (
                        decision.decision_id,
                        decision.requirement_id,
                        decision.requirement_revision,
                        decision.action.value,
                        decision.request_id,
                        decision.recorded_at.isoformat(),
                        decision.model_dump_json(),
                        content_hash(decision),
                    ),
                )
                after_hash = content_hash(new_revision) if new_revision else content_hash(decision)
                self._append_audit(
                    connection,
                    actor_id=actor_id,
                    actor_type=role,
                    action=f"review_{action.value}",
                    object_type="requirement",
                    object_id=requirement_id,
                    object_revision=(new_revision.revision if new_revision else expected_revision),
                    before_hash=content_hash(current),
                    after_hash=after_hash,
                    reason=rationale,
                    request_id=request_id,
                    result="success",
                )
                connection.commit()
                return decision, new_revision
        if conflict_message:
            raise RevisionConflict(conflict_message)
        raise AssertionError("review transaction ended without a result")

    def audit_events(self) -> list[AuditEvent]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM audit_events ORDER BY monotonic_sequence"
            ).fetchall()
        return [AuditEvent.model_validate_json(row["payload_json"]) for row in rows]

    def verify_audit_chain(self) -> tuple[bool, str]:
        previous_hash = "GENESIS"
        for expected_sequence, event in enumerate(self.audit_events(), start=1):
            if event.monotonic_sequence != expected_sequence:
                return False, f"sequence gap at {expected_sequence}"
            if event.previous_event_hash != previous_hash:
                return False, f"previous hash mismatch at sequence {expected_sequence}"
            calculated = self._event_hash_payload(event)
            if calculated != event.event_hash:
                return False, f"event hash mismatch at sequence {expected_sequence}"
            previous_hash = event.event_hash
        return True, previous_hash

    def replay_requirement(self, requirement_id: str) -> dict[str, Any]:
        valid, checkpoint = self.verify_audit_chain()
        with self.connect() as connection:
            revisions = [
                RequirementRevision.model_validate_json(row["payload_json"])
                for row in connection.execute(
                    """
                    SELECT payload_json FROM requirement_revisions
                    WHERE requirement_id=? ORDER BY revision
                    """,
                    (requirement_id,),
                ).fetchall()
            ]
            decisions = [
                Decision.model_validate_json(row["payload_json"])
                for row in connection.execute(
                    """
                    SELECT payload_json FROM decisions
                    WHERE requirement_id=? ORDER BY recorded_at
                    """,
                    (requirement_id,),
                ).fetchall()
            ]
        return {
            "audit_valid": valid,
            "audit_checkpoint": checkpoint,
            "revisions": [item.model_dump(mode="json") for item in revisions],
            "decisions": [item.model_dump(mode="json") for item in decisions],
        }
