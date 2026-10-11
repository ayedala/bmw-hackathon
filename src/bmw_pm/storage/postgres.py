"""Small DB-API adapter for the application's existing, bounded SQLite SQL dialect.

Only SQL authored in this repository reaches this adapter. Source text is always
bound as parameters. Schema installation is a separate administrator operation.
"""
from __future__ import annotations

import re
import sqlite3

from .config import StorageError, connection_options

SCHEMA_NAME = 'bmw_pm'
SCHEMA_VERSION = '1'
WRITE_LOCK = 1112364801
EXTRA_TABLES = {'imported_evidence', 'bmw_context', 'source_acquisitions',
                'youtube_bundles', 'youtube_findings', 'video_memories', 'successor_drafts'}


class Row:
    def __init__(self, names, values):
        self.names, self.values = names, values
    def __getitem__(self, key):
        return self.values[key if isinstance(key, (int, slice)) else self.names.index(key)]
    def __iter__(self):
        return iter(self.values)
    def __len__(self):
        return len(self.values)
    def keys(self):
        return self.names


class Cursor:
    def __init__(self, cursor):
        self.cursor = cursor
    @property
    def rowcount(self):
        return self.cursor.rowcount
    @property
    def description(self):
        return self.cursor.description
    def _row(self, values):
        return None if values is None else Row([c.name for c in self.cursor.description], values)
    def fetchone(self):
        return self._row(self.cursor.fetchone())
    def fetchall(self):
        return [self._row(row) for row in self.cursor.fetchall()]
    def __iter__(self):
        for row in self.cursor:
            yield self._row(row)


def translate_sql(sql: str, *, parameters: bool = True) -> str:
    sql = re.sub(r'\browid\b', '_insertion_order', sql)
    sql = re.sub(r'\bsqlite_master\b',
        "(SELECT table_name AS name, 'table' AS type FROM information_schema.tables WHERE table_schema='bmw_pm') AS sqlite_master", sql)
    sql = re.sub(r"json_extract\(\s*([\w.]+)\s*,\s*'\$\.([\w.]+)'\s*\)",
        lambda m: f"({m[1]}::jsonb #>> '{{{','.join(m[2].split('.'))}}}')", sql, flags=re.I)
    if re.match(r'\s*INSERT OR IGNORE\b', sql, re.I):
        sql = re.sub(r'INSERT OR IGNORE', 'INSERT', sql, count=1, flags=re.I).rstrip().rstrip(';') + ' ON CONFLICT DO NOTHING'
    if not parameters:
        return sql
    # Escape psycopg's percent syntax and replace qmark binds outside SQL literals.
    output, quote, index = [], None, 0
    while index < len(sql):
        char = sql[index]
        if char == '%':
            output.append('%%')
        elif quote:
            output.append(char)
            if char == quote:
                if index + 1 < len(sql) and sql[index + 1] == quote:
                    index += 1
                    output.append(quote)
                else:
                    quote = None
        elif char in "\"'":
            quote = char
            output.append(char)
        else:
            output.append('%s' if char == '?' else char)
        index += 1
    return ''.join(output)


class PostgresConnection:
    def __init__(self, dsn: str, *, readonly: bool = False):
        options = connection_options(dsn)
        if str(options.get('port', '5432')) == '6543':
            raise StorageError('Use the Supabase Session pooler on port 5432, not the transaction pooler.')
        try:
            import psycopg
            self.raw = psycopg.connect(**options, autocommit=True, prepare_threshold=None)
            self.raw.execute('SET search_path = bmw_pm, pg_catalog')
            self.raw.execute("SET statement_timeout = '120s'")
            self.raw.execute("SET lock_timeout = '20s'")
            self.raw.autocommit = False
            self.raw.read_only = readonly
            self.raw.isolation_level = (psycopg.IsolationLevel.REPEATABLE_READ if readonly
                                        else psycopg.IsolationLevel.READ_COMMITTED)
        except Exception:
            if hasattr(self, 'raw'):
                self.raw.close()
            raise StorageError('Cannot connect to the shared database. Check DATABASE_URL, the database password and network access.') from None

    def write_lock(self):
        self.raw.execute('SELECT pg_advisory_xact_lock(%s)', (WRITE_LOCK,))

    def execute(self, sql: str, params=None):
        import psycopg
        try:
            command = sql.strip().rstrip(';').upper()
            if command in {'BEGIN', 'BEGIN IMMEDIATE'}:
                if command == 'BEGIN IMMEDIATE':
                    self.write_lock()
                return Cursor(self.raw.execute('SELECT 1'))
            # These optional tables are installed by the administrator migration.
            table = re.match(r'\s*CREATE TABLE IF NOT EXISTS\s+(\w+)', sql, re.I)
            if table:
                if table[1] not in EXTRA_TABLES:
                    raise StorageError('The shared schema must be updated by an administrator.')
                return Cursor(self.raw.execute(f'SELECT 1 FROM {table[1]} LIMIT 0'))
            if re.match(r'\s*CREATE UNIQUE INDEX IF NOT EXISTS ix_imported_row_key\b', sql, re.I):
                return Cursor(self.raw.execute('SELECT 1'))
            return Cursor(self.raw.execute(translate_sql(sql, parameters=params is not None), params))
        except psycopg.IntegrityError as error:
            # Keep the established DB-API contract without exposing bound source data.
            message = 'Database integrity or immutable/append-only rule rejected this change.'
            raise sqlite3.IntegrityError(message) from None
        except psycopg.Error:
            raise StorageError('The shared database operation failed. Check permissions, schema version and concurrent jobs.') from None

    def executescript(self, script: str):
        # The only runtime extension script creates the immutable successor table.
        if 'CREATE TABLE IF NOT EXISTS successor_drafts' not in script:
            raise StorageError('Shared database schema changes require the administrator setup command.')
        self.execute('SELECT 1 FROM successor_drafts LIMIT 0')
        self.commit()

    def commit(self):
        self.raw.commit()
    def rollback(self):
        self.raw.rollback()
    def close(self):
        try:
            if not self.raw.closed:
                self.raw.rollback()
        finally:
            self.raw.close()


def assert_schema(connection: PostgresConnection) -> None:
    row = connection.execute('SELECT version FROM schema_version WHERE singleton=1').fetchone()
    if not row or row[0] != SCHEMA_VERSION:
        raise StorageError('Initialize or migrate the shared schema with the Supabase setup command.')
