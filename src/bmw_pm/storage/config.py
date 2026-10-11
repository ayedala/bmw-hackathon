"""Server-side database selection; credentials never become display paths."""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[3]


class StorageError(RuntimeError):
    """A safe, user-facing storage configuration or connection failure."""


def local_settings(root: Path = ROOT) -> dict[str, str]:
    values = {}
    for file in (root / '.env', root / '.env.local'):
        if not file.is_file():
            continue
        for line in file.read_text(encoding='utf-8-sig').splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            name, value = line.split('=', 1)
            name, value = name.strip(), value.strip()
            if name not in {'DATABASE_URL', 'BMW_PM_DB_PATH'}:
                continue
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            if value:
                values[name] = value
    return values


def is_postgres(value: str | Path) -> bool:
    return isinstance(value, str) and value.startswith(('postgresql://', 'postgres://'))


def database_target(value: str | Path | None = None, *, root: Path = ROOT) -> str | Path:
    if value is not None:
        return value if is_postgres(value) else Path(value)
    # An explicit process-level local path isolates tests and local-only commands.
    for settings in (os.environ, local_settings(root)):
        if settings.get('DATABASE_URL', '').strip():
            target = settings['DATABASE_URL'].strip()
            if not is_postgres(target):
                raise StorageError('DATABASE_URL must be a PostgreSQL connection URL.')
            return target
        if settings.get('BMW_PM_DB_PATH', '').strip():
            return Path(settings['BMW_PM_DB_PATH'])
    return root / 'data/processed/bmw_pm.db'


def database_label(value: str | Path) -> str:
    if is_postgres(value):
        return 'Shared PostgreSQL database'
    return 'Local SQLite database'


def connection_options(dsn: str) -> dict:
    try:
        from psycopg.conninfo import conninfo_to_dict
        options = conninfo_to_dict(dsn)
        host = options.get('host', '')
        parsed = urlsplit(dsn)
        if not host or not parsed.username or not parsed.path.strip('/'):
            raise ValueError()
        if host not in {'localhost', '127.0.0.1', '::1'}:
            if options.get('sslmode', 'require') not in {'require', 'verify-ca', 'verify-full'}:
                raise StorageError('Remote database connections must use sslmode=require or verify-full.')
            options.setdefault('sslmode', 'require')
        options['connect_timeout'] = 10
        options['application_name'] = 'bmw-decision-lab'
        # The application schema is fixed and excluded from the public Data API.
        options.pop('options', None)
        return options
    except ImportError:
        raise StorageError('Install the postgres extra: pip install -e ".[postgres]".') from None
    except StorageError:
        raise
    except Exception:
        raise StorageError('Check DATABASE_URL in the local .env.local file; its connection format is invalid.') from None
