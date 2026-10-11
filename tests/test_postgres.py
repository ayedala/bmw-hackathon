"""Run integration tests only against an explicitly configured disposable local PostgreSQL."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sqlite3
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import pytest

from bmw_pm.advisor.bridge import source_catalog
from bmw_pm.advisor.evidence import build_packet
from bmw_pm.data_pipeline.video_memory import TranscriptInput, save_transcript
from bmw_pm.storage import Database
from bmw_pm.storage.config import StorageError, connection_options, database_target
from bmw_pm.storage.postgres import translate_sql
from bmw_pm.storage.schema import install_schema
from bmw_pm.storage.supabase import create_collaborator, direct_migration_target, migrate_sqlite
from test_advisor import evidence_db, request


@pytest.fixture
def postgres_target():
    dsn = os.getenv('BMW_TEST_POSTGRES_DSN')
    if not dsn:
        pytest.skip('Set BMW_TEST_POSTGRES_DSN to a disposable local PostgreSQL instance')
    parsed = urlsplit(dsn)
    assert parsed.hostname in {'127.0.0.1', 'localhost'} and parsed.path.startswith('/bmw_test'), 'Never run destructive fixtures against a shared project'
    psycopg = pytest.importorskip('psycopg')
    from psycopg import sql
    name = 'bmw_test_' + uuid4().hex[:12]
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    target = urlunsplit((parsed.scheme, parsed.netloc, '/' + name, parsed.query, ''))
    try:
        yield target
    finally:
        with psycopg.connect(dsn, autocommit=True) as admin:
            admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))


def test_database_config_does_not_leak_or_fall_back(monkeypatch, tmp_path):
    monkeypatch.delenv('DATABASE_URL', raising=False)
    monkeypatch.delenv('BMW_PM_DB_PATH', raising=False)
    (tmp_path / '.env').write_text('DATABASE_URL="postgresql://test:private@localhost/test"\n')
    assert database_target(root=tmp_path) == 'postgresql://test:private@localhost/test'
    assert database_target(tmp_path / 'explicit.db', root=tmp_path) == tmp_path / 'explicit.db'
    monkeypatch.setenv('BMW_PM_DB_PATH', str(tmp_path / 'isolated.db'))
    assert database_target(root=tmp_path) == tmp_path / 'isolated.db'
    with pytest.raises(StorageError) as error:
        connection_options('postgresql://test:private@remote.invalid/test?sslmode=disable')
    assert 'private' not in str(error.value)
    assert 'private' not in str(Database('postgresql://test:private@localhost/test').path)


def test_large_migration_uses_direct_supabase_endpoint():
    session = 'postgresql://postgres.abcdefghijklmnopqrst:encoded%40pass@aws-1-eu-west-3.pooler.supabase.com:5432/postgres?sslmode=require'
    assert direct_migration_target(session) == ('postgresql://postgres:encoded%40pass@'
        'db.abcdefghijklmnopqrst.supabase.co:5432/postgres?sslmode=require')
    local = 'postgresql://postgres:local@127.0.0.1:5432/bmw_test'
    assert direct_migration_target(local) == local


def test_sql_parameters_preserve_literals_and_ignore_duplicate_inserts():
    statement = "SELECT '?' AS mark, '100%' AS percent, json_extract(payload_json,'$.payload.name') FROM item WHERE id=?"
    result = translate_sql(statement)
    assert "'?' AS mark" in result and "'100%%'" in result
    assert "#>> '{payload,name}'" in result and 'id=%s' in result
    assert translate_sql('INSERT OR IGNORE INTO x VALUES (?)').endswith('ON CONFLICT DO NOTHING')


def test_migration_preserves_evidence_files_and_duplicate_invariance(postgres_target, evidence_db, tmp_path):
    source_files = tmp_path / 'sources'
    source_files.mkdir()
    original = b'%PDF synthetic private source bytes\x00\xff'
    (source_files / 'source.pdf').write_bytes(original)
    before = build_packet(request(), evidence_db)
    migrated = migrate_sqlite(evidence_db, postgres_target, files=source_files)
    after = build_packet(request(), postgres_target)
    assert before.model_dump() == after.model_dump()
    assert migrated['tables']['feedback_records']['rows'] == 5
    assert migrated['source_files'] == 1
    assert migrate_sqlite(evidence_db, postgres_target, files=source_files)['status'] == 'already_imported'
    db = Database(postgres_target)
    assert db.verify_audit_chain()[0]
    with db.connect() as connection:
        assert bytes(connection.execute('SELECT content FROM shared_source_files').fetchone()[0]) == original
        assert connection.execute('SELECT count(*) FROM audit_events').fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError, match='immutable'):
            connection.execute("UPDATE audit_events SET event_hash='modified'")
    catalog = source_catalog(postgres_target, tmp_path)
    assert catalog.database_backend == 'postgres' and sum(r.feedback_records for r in catalog.scopes) == 5
    assert 'synthetic-local-test-password' not in catalog.model_dump_json()


def test_schema_mismatch_rolls_back_the_entire_copy(postgres_target, evidence_db):
    with sqlite3.connect(evidence_db) as local:
        local.execute('ALTER TABLE priority_assessments ADD COLUMN unknown_column TEXT')
    with pytest.raises(StorageError, match='columns'):
        migrate_sqlite(evidence_db, postgres_target)
    with Database(postgres_target).connect() as connection:
        assert connection.execute('SELECT count(*) FROM feedback_records').fetchone()[0] == 0
        assert connection.execute('SELECT count(*) FROM audit_events').fetchone()[0] == 0


def test_simultaneous_writers_keep_a_single_valid_audit_chain(postgres_target):
    db = Database(postgres_target)
    with db.connect() as connection:
        install_schema(connection)
    def write(index):
        with db.connect() as connection:
            db._append_audit(connection, actor_id='synthetic', actor_type='pipeline', action='concurrent_test',
                object_type='fixture', object_id=str(index), object_revision=None, before_hash=None,
                after_hash=None, reason='Synthetic concurrency test', request_id=f'parallel-{index}', result='success')
            connection.commit()
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(write, range(18)))
    assert db.verify_audit_chain()[0]
    with db.connect() as connection:
        assert connection.execute('SELECT count(*) FROM audit_events').fetchone()[0] == 18


def test_collaborator_permissions_and_shared_memory(postgres_target, evidence_db, tmp_path, monkeypatch):
    import bmw_pm.storage.supabase as setup
    import psycopg
    from psycopg import sql
    migrate_sqlite(evidence_db, postgres_target)
    monkeypatch.setattr(setup, 'ROOT', tmp_path)
    names = []
    try:
        targets = {}
        for access in ('reader', 'writer'):
            name = 'bmw_user_' + uuid4().hex[:12]
            output = tmp_path / ('.env.' + name)
            create_collaborator(postgres_target, name, access, output)
            names.append(name)
            targets[access] = json.loads(output.read_text().split('DATABASE_URL=', 1)[1])
        item = TranscriptInput(video_url='https://youtu.be/abcdefghijk', title='Shared synthetic transcript',
            model_code='G60', market='US', transcript='Physical climate buttons are easy to find and use without leaving the road out of sight.')
        assert save_transcript(targets['writer'], item)['inserted']
        assert not save_transcript(targets['writer'], item)['inserted']
        packet = build_packet(request(), targets['reader'])
        assert any(e.channel == 'video_transcript_memory' for e in packet.evidence)
        with pytest.raises(StorageError):
            save_transcript(targets['reader'], item.model_copy(update={'title': 'Forbidden', 'transcript': item.transcript + ' Extra text.'}))
        with Database(targets['writer']).connect() as connection:
            with pytest.raises(StorageError):
                connection.execute('DELETE FROM feedback_records')
        assert Database(postgres_target).verify_audit_chain()[0]
    finally:
        # Remove only roles created by this fixture, after releasing their memberships/grants.
        with psycopg.connect(postgres_target, autocommit=True) as admin:
            for name in names:
                admin.execute(sql.SQL('DROP OWNED BY {}').format(sql.Identifier(name)))
                admin.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(name)))


def test_existing_revision_and_replay_workflow_on_postgres(postgres_target, tmp_path, monkeypatch):
    import test_audit
    db = Database(postgres_target)
    with db.connect() as connection:
        install_schema(connection)
    monkeypatch.setattr(test_audit, 'Database', lambda path: db)
    test_audit.test_review_revision_idempotency_stale_conflict_and_replay(tmp_path)
