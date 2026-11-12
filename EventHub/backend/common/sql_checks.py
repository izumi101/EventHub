"""Data-integrity checks written in SQL (backend/sql/checks/*.sql).

Every file is one check: a header of `-- key: value` comment lines (name,
severity, invariant, why) followed by one PostgreSQL query that returns rows
only when something is wrong. The first column identifies the offending row
and is what the runner prints as a sample.

The runner executes each check in its own read-only transaction:

* as the read-only role (POSTGRES_READONLY_USER) when its password is set,
  so a check can never change data even if it were written wrongly;
* otherwise on Django's own connection, still inside `SET TRANSACTION READ
  ONLY` (or, when the caller already holds a transaction, in a savepoint of
  it: the tests and `--inject-defects` need to see their uncommitted rows).
"""

import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings
from django.db import connection, transaction

SEVERITIES = ('CRITICAL', 'WARNING', 'INFO')
STATEMENT_TIMEOUT = '60s'
_HEADER = re.compile(r'^--\s*(name|severity|invariant|why):\s*(.*)$')


class CheckDefinitionError(Exception):
    pass


@dataclass(frozen=True)
class Check:
    name: str
    severity: str
    invariant: str
    why: str
    sql: str = field(repr=False)
    path: Path = field(repr=False)


@dataclass
class CheckResult:
    check: Check
    columns: list = field(default_factory=list)
    rows: list = field(default_factory=list)
    error: str = ''
    seconds: float = 0.0

    @property
    def found(self):
        return len(self.rows)

    @property
    def failed(self):
        return bool(self.rows) or bool(self.error)

    def samples(self, limit=5):
        return [str(row[0]) for row in self.rows[:limit]]

    def as_dict(self, row_limit=5):
        return {
            'name': self.check.name,
            'severity': self.check.severity,
            'file': self.check.path.name,
            'rows': self.found,
            'samples': self.samples(),
            'error': self.error,
            'seconds': round(self.seconds, 4),
            'columns': self.columns,
            'first_rows': [[_plain(v) for v in row] for row in self.rows[:row_limit]],
        }


def _plain(value):
    return value if value is None or isinstance(value, (int, float, bool, str)) else str(value)


def checks_dir():
    return Path(settings.BASE_DIR) / 'sql' / 'checks'


def load_checks(directory=None, only=None):
    """Parse every *.sql file of `directory` (sorted by file name)."""
    directory = Path(directory or checks_dir())
    checks = []
    for path in sorted(directory.glob('*.sql')):
        text = path.read_text(encoding='utf-8')
        meta, last = {}, None
        for line in text.splitlines():
            if not line.startswith('--'):
                break
            match = _HEADER.match(line)
            if match:
                last = match.group(1)
                meta[last] = match.group(2).strip()
            elif last:
                meta[last] = f'{meta[last]} {line[2:].strip()}'.strip()
        missing = {'name', 'severity', 'invariant', 'why'} - meta.keys()
        if missing:
            raise CheckDefinitionError(f'{path.name}: header misses {", ".join(sorted(missing))}')
        severity = meta['severity'].upper()
        if severity not in SEVERITIES:
            raise CheckDefinitionError(f'{path.name}: unknown severity {meta["severity"]!r}')
        checks.append(Check(meta['name'], severity, meta['invariant'], meta['why'], text, path))
    names = [c.name for c in checks]
    if len(set(names)) != len(names):
        raise CheckDefinitionError('Two check files use the same name.')
    if only:
        wanted = set(only)
        unknown = wanted - set(names)
        if unknown:
            raise CheckDefinitionError(f'Unknown check(s): {", ".join(sorted(unknown))}')
        checks = [c for c in checks if c.name in wanted]
    return checks


class ReadonlyRoleExecutor:
    """Runs checks as POSTGRES_READONLY_USER on a separate connection."""

    def __init__(self):
        from common.db_roles import connect_as

        self.role = settings.DB_READONLY_USER
        self.conn = connect_as(self.role, settings.DB_READONLY_PASSWORD)

    @property
    def description(self):
        return f'read-only role "{self.role}"'

    def run(self, check):
        with self.conn.transaction(force_rollback=True):
            self.conn.execute('SET TRANSACTION READ ONLY')
            self.conn.execute(f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT}'")
            cur = self.conn.execute(check.sql)
            return [d.name for d in cur.description], cur.fetchall()

    def close(self):
        self.conn.close()


class DjangoConnectionExecutor:
    """Runs checks on Django's default connection, read-only where possible."""

    def __init__(self):
        self.nested = connection.in_atomic_block

    @property
    def description(self):
        user = connection.settings_dict['USER']
        mode = 'savepoints of the current transaction' if self.nested else 'read-only transactions'
        return f'Django connection as "{user}" ({mode})'

    def run(self, check):
        with transaction.atomic(), connection.cursor() as cur:
            if not self.nested:
                cur.execute('SET TRANSACTION READ ONLY')
            cur.execute(f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT}'")
            cur.execute(check.sql)
            return [d[0] for d in cur.description], cur.fetchall()

    def close(self):
        pass


def make_executor(use_default_connection=False):
    if settings.DB_READONLY_PASSWORD and not use_default_connection and not connection.in_atomic_block:
        return ReadonlyRoleExecutor()
    return DjangoConnectionExecutor()


def run_checks(checks, executor):
    results = []
    for check in checks:
        result = CheckResult(check)
        started = time.monotonic()
        try:
            result.columns, result.rows = executor.run(check)
        except Exception as exc:  # a broken check must not hide the others; it is reported as an error
            result.error = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
        result.seconds = time.monotonic() - started
        results.append(result)
    return results
