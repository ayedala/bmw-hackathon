# Persistence and audit

`database.py` owns SQLite schema creation, evidence persistence, immutable requirement revisions, score snapshots, decisions and the chronological hash-linked audit events. Review transactions enforce optimistic concurrency and request idempotency. Audit table triggers prevent application updates and deletes; chain verification detects inconsistent history.

The local database is ignored by Git. Use the core CLI and services rather than editing its tables. Imported foreign SQL and triggers are never run in the active database.

The trail covers important writes and selected access paths, not every read, file access or provider action. It is not independently anchored against an administrator rewriting the database. Complete access auditing and verified identity remain explicit gaps against the challenge brief. See [audit design](../../../docs/HUMAN_REVIEW_AND_AUDIT.md).
