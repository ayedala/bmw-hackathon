"""Private shared database setup, verified SQLite migration and team access.

Run with python -m bmw_pm.storage.supabase. Credentials are read from .env,
never accepted as CLI arguments or printed in output.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
from itertools import islice
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import tempfile
from urllib.parse import quote, urlsplit, urlunsplit
from uuid import uuid4

from .config import ROOT, StorageError, database_target, is_postgres
from .database import Database
from .schema import APPLICATION_TABLES, MIGRATABLE_TABLES, ROW_ORDER_TABLES, install_schema
from ..utils import canonical_json, content_hash, sha256_bytes, utc_now


def shared_database(target=None) -> Database:
    db = Database(database_target(target))
    if not db.is_postgres:
        raise StorageError('Add the Supabase Session pooler DATABASE_URL to the local .env file first.')
    return db


def direct_migration_target(target: str) -> str:
    """Use the project's direct endpoint for long-running owner COPY jobs.

    Normal app traffic keeps using the configured IPv4 session pooler. Supavisor
    closed large synthetic COPY streams in testing; the direct IPv6 endpoint
    was verified for this project's migration.
    """
    parsed = urlsplit(target)
    host = parsed.hostname or ''
    if not host.endswith('.pooler.supabase.com'):
        return target
    username = parsed.username or ''
    if not username.startswith('postgres.') or ':' not in parsed.netloc.split('@', 1)[0]:
        raise StorageError('The administrator Session pooler URL is incomplete.')
    project = username.split('.', 1)[1]
    if not re.fullmatch(r'[a-z0-9]{10,40}', project):
        raise StorageError('The Supabase project reference is invalid.')
    encoded_password = parsed.netloc.split('@', 1)[0].split(':', 1)[1]
    authority = f'postgres:{encoded_password}@db.{project}.supabase.co:5432'
    return urlunsplit((parsed.scheme, authority, parsed.path, parsed.query, ''))


def _table_manifest(connection, table: str) -> dict:
    if table not in APPLICATION_TABLES:
        raise StorageError('Unsupported source table; no data was migrated.')
    ordered = table in ROW_ORDER_TABLES
    order_column = '_insertion_order' if hasattr(connection, 'raw') else 'rowid'
    cursor = connection.execute(f'SELECT *' + (f', {order_column} AS migration_order' if ordered else '') + f' FROM {table}')
    names = [c[0] for c in cursor.description]
    indices = [i for i, name in enumerate(names) if name not in {'_insertion_order', 'migration_order'}]
    columns = [names[i] for i in indices]
    hashes = sorted(sha256_bytes(canonical_json([row[i] for i in indices] + ([row[-1]] if ordered else [])).encode('utf-8')) for row in cursor)
    digest = hashlib.sha256('\n'.join(hashes).encode()).hexdigest()
    return {'rows': len(hashes), 'columns': columns, 'sha256': digest}


def _source_files(directory: Path | None) -> list[dict]:
    if directory is None:
        return []
    directory = directory.resolve()
    if not directory.is_dir():
        raise StorageError('The source-file directory does not exist.')
    files, total = [], 0
    for file in sorted(directory.rglob('*')):
        if not file.is_file() or file.suffix.lower() not in {'.xlsx', '.pdf', '.csv', '.json', '.txt'}:
            continue
        resolved = file.resolve()
        if not resolved.is_relative_to(directory):
            raise StorageError('Source files must remain inside the selected directory.')
        size = file.stat().st_size
        total += size
        if size > 50_000_000 or total > 250_000_000:
            raise StorageError('Source transfer exceeds the 50 MB/file or 250 MB/batch limit.')
        files.append({'relative_path': file.relative_to(directory).as_posix(),
                      'sha256': sha256_bytes(file.read_bytes()), 'byte_count': size})
    return files


def migrate_sqlite(source: Path, target: str, *, files: Path | None = None, progress=None) -> dict:
    """Atomic copy into an empty schema; preserve originals and refuse overwrites."""
    from psycopg import sql
    if not source.is_file():
        raise StorageError('The source SQLite database is missing.')
    notify = progress or (lambda message: None)
    scratch = ROOT / '.tmp'
    scratch.mkdir(exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix='supabase-snapshot-', suffix='.db', dir=scratch)
    os.close(descriptor)
    snapshot = Path(name)
    try:
        with closing(sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True)) as original:
            with closing(sqlite3.connect(snapshot)) as backup:
                original.backup(backup)
        with closing(sqlite3.connect(snapshot)) as local:
            if local.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or local.execute('PRAGMA foreign_key_check').fetchone():
                raise StorageError('The source database failed integrity checks.')
            names = {r[0] for r in local.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
            if names - set(MIGRATABLE_TABLES):
                raise StorageError('The source contains an unsupported table. Extend the migration before copying it.')
            if not Database(snapshot).verify_audit_chain()[0]:
                raise StorageError('The source audit chain is invalid.')
            tables = {table: _table_manifest(local, table) for table in MIGRATABLE_TABLES if table in names}
            file_manifest = _source_files(files)
            manifest = {'tables': tables, 'source_files': file_manifest}
            fingerprint = content_hash(manifest)
            db = shared_database(direct_migration_target(target))
            with db.connect() as connection:
                install_schema(connection)
                # Bulk COPY over a remote connection can exceed the interactive
                # query deadline. This setting applies only to this transaction.
                connection.raw.execute("SET LOCAL statement_timeout = '15min'")
                connection.write_lock()
                prior = connection.execute('SELECT manifest_json FROM migration_runs WHERE fingerprint=?', (fingerprint,)).fetchone()
                if prior:
                    if json.loads(prior[0]) != manifest:
                        raise StorageError('Stored migration receipt does not match this source.')
                    return {'status': 'already_imported', 'fingerprint': fingerprint, 'tables': tables,
                            'source_files': len(file_manifest)}
                if any(connection.execute(f'SELECT 1 FROM {table} LIMIT 1').fetchone() for table in APPLICATION_TABLES if table != 'schema_version'):
                    raise StorageError('The shared schema already contains data. Migration never replaces or merges an existing dataset.')
                for table, expected in tables.items():
                    actual_columns = [c.name for c in connection.raw.execute(sql.SQL('SELECT * FROM {} LIMIT 0').format(sql.Identifier(table))).description if c.name != '_insertion_order']
                    if expected['columns'] != actual_columns:
                        raise StorageError(f'Source columns do not match the supported schema for {table}.')
                    notify(f'Copying {table}: {expected["rows"]} records')
                    ordered = table in ROW_ORDER_TABLES
                    copy_columns = expected['columns'] + (['_insertion_order'] if ordered else [])
                    statement = sql.SQL('COPY {} ({}) FROM STDIN').format(sql.Identifier(table),
                        sql.SQL(',').join(map(sql.Identifier, copy_columns)))
                    rows = iter(local.execute('SELECT *' + (', rowid' if ordered else '') + f' FROM {table}'))
                    copied = 0
                    while batch := list(islice(rows, 500)):
                        # Bound each remote COPY request. The pooler and direct
                        # endpoint have both closed prolonged COPY streams for
                        # this real dataset; the transaction stays atomic.
                        with connection.raw.cursor().copy(statement) as copy:
                            for row in batch:
                                copy.write_row(row)
                        copied += len(batch)
                        if copied % 5000 == 0:
                            notify(f'  {table}: {copied}/{expected["rows"]} transferred')
                    if ordered:
                        connection.raw.execute(sql.SQL("SELECT setval(pg_get_serial_sequence(%s,'_insertion_order'), COALESCE((SELECT max(_insertion_order) FROM {}),0)+1,false)")
                            .format(sql.Identifier(table)), ('bmw_pm.' + table,))
                    if _table_manifest(connection, table) != expected:
                        raise StorageError(f'Content verification failed for {table}; the copy was rolled back.')
                for item in file_manifest:
                    content = (files / item['relative_path']).read_bytes()
                    if sha256_bytes(content) != item['sha256']:
                        raise StorageError('A source file changed during migration; the copy was rolled back.')
                    connection.execute('INSERT INTO shared_source_files VALUES (?,?,?,?)',
                        (item['relative_path'], item['sha256'], item['byte_count'], content))
                    stored = connection.execute('SELECT content FROM shared_source_files WHERE relative_path=? AND sha256=?',
                        (item['relative_path'], item['sha256'])).fetchone()
                    if sha256_bytes(bytes(stored[0])) != item['sha256']:
                        raise StorageError('Transferred source bytes failed verification; the copy was rolled back.')
                db._append_audit(connection, actor_id='supabase-migration', actor_type='pipeline',
                    action='migrate_shared_database', object_type='dataset', object_id=fingerprint,
                    object_revision=None, before_hash=None, after_hash=fingerprint,
                    reason='Verified complete row hashes against a consistent SQLite snapshot; original source bytes retained.',
                    request_id='supabase-migration:' + fingerprint, result='success')
                connection.execute('INSERT INTO migration_runs VALUES (?,?,?)',
                    (fingerprint, utc_now().isoformat(), canonical_json(manifest)))
                connection.commit()
            return {'status': 'imported', 'fingerprint': fingerprint, 'tables': tables,
                    'source_files': len(file_manifest), 'audit_event_added': True}
    finally:
        # Only the uniquely created temporary file is removed; no directory deletion.
        if snapshot.parent.resolve() == scratch.resolve():
            snapshot.unlink(missing_ok=True)


def create_collaborator(target: str, username: str, access: str, output: Path) -> dict:
    """Generate an individual login and an ignored local connection file."""
    from psycopg import sql
    if not re.fullmatch(r'bmw_user_[a-z0-9_]{1,40}', username) or access not in {'reader', 'writer'}:
        raise StorageError('Use a bmw_user_ name followed by lowercase letters, digits or underscores, and reader/writer access.')
    if output.exists() or not output.name.startswith('.env.') or output.parent.resolve() != ROOT.resolve():
        raise StorageError('Write credentials to a new .env.<name> file in the repository root.')
    password = secrets.token_urlsafe(32)
    db = shared_database(target)
    db.initialize()
    created_file = False
    try:
        with db.connect() as connection:
            connection.write_lock()
            if connection.raw.execute('SELECT 1 FROM pg_roles WHERE rolname=%s', (username,)).fetchone():
                raise StorageError('That collaborator login already exists. No credentials were replaced.')
            connection.raw.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD {}')
                .format(sql.Identifier(username), sql.Literal(password)))
            connection.raw.execute(sql.SQL('GRANT {} TO {}').format(sql.Identifier('bmw_pm_' + access), sql.Identifier(username)))
            parsed = urlsplit(target)
            old_user = parsed.username or ''
            suffix = '.' + old_user.split('.', 1)[1] if '.pooler.supabase.com' in (parsed.hostname or '') and '.' in old_user else ''
            host = parsed.hostname or ''
            if ':' in host:
                host = '[' + host + ']'
            authority = quote(username + suffix, safe='') + ':' + quote(password, safe='') + '@' + host
            if parsed.port:
                authority += ':' + str(parsed.port)
            url = urlunsplit((parsed.scheme, authority, parsed.path, parsed.query, ''))
            with output.open('x', encoding='utf-8') as file:
                created_file = True
                file.write('# Private individual database credentials. Do not commit or paste in chat.\nDATABASE_URL=' + json.dumps(url) + '\n')
            db._append_audit(connection, actor_id='database-admin', actor_type='pipeline',
                action='grant_collaborator_access', object_type='database_role', object_id=username,
                object_revision=None, before_hash=None, after_hash=None,
                reason=f'Created individual {access} login for the private application schema.',
                request_id='collaborator:' + uuid4().hex, result='success')
            connection.commit()
    except Exception:
        # A failed role transaction must not leave a misleading credential file.
        if created_file and output.exists():
            output.unlink()
        raise
    return {'username': username, 'access': access, 'credentials_file': output.name}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('init')
    commands.add_parser('status')
    migrate = commands.add_parser('migrate')
    migrate.add_argument('--source', type=Path, default=ROOT / 'data/processed/bmw_pm.db')
    migrate.add_argument('--source-files', type=Path, help='Optional directory of original documents to share privately')
    verify = commands.add_parser('verify')
    verify.add_argument('--expect-supplied-shape', action='store_true')
    member = commands.add_parser('create-user')
    member.add_argument('username')
    member.add_argument('--access', choices=['reader', 'writer'], default='reader')
    download = commands.add_parser('download-source')
    download.add_argument('sha256')
    download.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        db = shared_database()
        if args.command == 'init':
            with db.connect() as connection:
                install_schema(connection)
            result = {'status': 'schema_initialized', 'schema': 'bmw_pm'}
        elif args.command == 'migrate':
            result = migrate_sqlite(args.source, str(db.target), files=args.source_files,
                progress=lambda message: print(message, flush=True))
        elif args.command == 'create-user':
            result = create_collaborator(str(db.target), args.username, args.access, ROOT / ('.env.' + args.username))
        elif args.command == 'verify':
            from ..validation import validate_database
            result = validate_database(db, expect_supplied_shape=args.expect_supplied_shape)
            print(json.dumps(result, indent=2))
            return 0 if result['passed'] else 1
        elif args.command == 'download-source':
            if not re.fullmatch('[a-f0-9]{64}', args.sha256) or args.output.exists():
                raise StorageError('Provide a SHA-256 and a new output filename.')
            with db.connect(readonly=True) as connection:
                row = connection.execute('SELECT content FROM shared_source_files WHERE sha256=? LIMIT 1', (args.sha256,)).fetchone()
                if row is None or sha256_bytes(bytes(row[0])) != args.sha256:
                    raise StorageError('The source was not found or its stored hash did not match.')
                with args.output.open('xb') as file:
                    file.write(bytes(row[0]))
            result = {'status': 'downloaded', 'sha256': args.sha256}
        else:
            db.initialize()
            with db.connect(readonly=True) as connection:
                result = {'database': 'shared_postgresql', 'schema': 'bmw_pm',
                    'tables': {t: connection.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in APPLICATION_TABLES}}
        print(json.dumps(result, indent=2))
        return 0
    except StorageError as error:
        print(str(error))
    except Exception:
        print('Shared database setup failed. Check connectivity, administrator permissions and the installed schema. No credentials are printed.')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
