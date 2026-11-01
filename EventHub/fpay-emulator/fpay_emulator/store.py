"""SQLite repository (stdlib ``sqlite3``, WAL).

All state lives here, including the callback retry schedule and the virtual
clock offset, so a restart of the emulator resumes pending deliveries.
The emulator is a single process; one connection guarded by a lock is enough.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from .models import PENDING_STATUSES, SUCCESS, Operation, Payment, iso

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS payments (
    payment_id INTEGER PRIMARY KEY,
    merchant_id TEXT NOT NULL,
    order_id TEXT,
    customer TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS payments_order ON payments (merchant_id, order_id, payment_id);
CREATE INDEX IF NOT EXISTS payments_status ON payments (status, expires_at);
CREATE TABLE IF NOT EXISTS operations (
    op_id INTEGER PRIMARY KEY,
    payment_id INTEGER NOT NULL REFERENCES payments (payment_id),
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS operations_payment ON operations (payment_id, op_id);
CREATE TABLE IF NOT EXISTS idempotency (
    merchant_id TEXT NOT NULL,
    scope TEXT NOT NULL,
    key TEXT NOT NULL,
    response TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (merchant_id, scope, key)
);
CREATE TABLE IF NOT EXISTS callback_jobs (
    job_id INTEGER PRIMARY KEY AUTOINCREMENT,
    payment_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    state TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    first_attempt_at TEXT,
    next_attempt_at TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS callback_jobs_due ON callback_jobs (state, next_attempt_at);
CREATE TABLE IF NOT EXISTS deliveries (
    delivery_id INTEGER PRIMARY KEY AUTOINCREMENT,
    payment_id INTEGER NOT NULL,
    job_id INTEGER,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS deliveries_payment ON deliveries (payment_id, delivery_id);
CREATE TABLE IF NOT EXISTS faults (
    fault_id INTEGER PRIMARY KEY AUTOINCREMENT,
    endpoint TEXT NOT NULL,
    data TEXT NOT NULL
);
"""

ID_SEQUENCE_START = 1030000000000


class Store:
    def __init__(self, path: str) -> None:
        if path != ':memory:':
            directory = os.path.dirname(os.path.abspath(path))
            os.makedirs(directory, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            self._db.execute('PRAGMA journal_mode=WAL')
            self._db.execute('PRAGMA synchronous=NORMAL')
            self._db.execute('PRAGMA foreign_keys=ON')
            self._db.execute('PRAGMA busy_timeout=5000')
            self._db.executescript(SCHEMA)
            # A crash during a delivery leaves the job claimed: hand it back.
            self._db.execute("UPDATE callback_jobs SET state = 'pending' WHERE state = 'running'")

    def close(self) -> None:
        with self._lock:
            self._db.close()

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._db.execute('BEGIN IMMEDIATE')
            try:
                yield self._db
            except BaseException:
                self._db.execute('ROLLBACK')
                raise
            self._db.execute('COMMIT')

    def ping(self) -> bool:
        with self._lock:
            return self._db.execute('SELECT 1').fetchone()[0] == 1

    # -- meta ---------------------------------------------------------------

    def get_meta(self, key: str, default: str | None = None) -> str | None:
        with self._lock:
            row = self._db.execute('SELECT value FROM meta WHERE key = ?', (key,)).fetchone()
        return row['value'] if row else default

    def set_meta(self, key: str, value: str) -> None:
        with self._lock:
            self._db.execute(
                'INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value',
                (key, value),
            )

    def next_id(self) -> int:
        """13-digit ids shared by payments, refunds and cancellations."""
        with self.tx() as db:
            row = db.execute("SELECT value FROM meta WHERE key = 'id_sequence'").fetchone()
            value = int(row['value']) + 1 if row else ID_SEQUENCE_START + 1
            db.execute(
                "INSERT INTO meta (key, value) VALUES ('id_sequence', ?) "
                'ON CONFLICT (key) DO UPDATE SET value = excluded.value',
                (str(value),),
            )
        return value

    # -- payments -----------------------------------------------------------

    def insert_payment(self, payment: Payment) -> None:
        with self._lock:
            self._db.execute(
                'INSERT INTO payments '
                '(payment_id, merchant_id, order_id, customer, status, created_at, expires_at, data) '
                'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                (
                    payment.payment_id,
                    payment.merchant_id,
                    payment.order_id,
                    payment.customer,
                    payment.status,
                    iso(payment.created_at),
                    iso(payment.expires_at),
                    json.dumps(payment.to_dict()),
                ),
            )

    def save_payment(self, payment: Payment) -> None:
        with self._lock:
            self._db.execute(
                'UPDATE payments SET status = ?, data = ? WHERE payment_id = ?',
                (payment.status, json.dumps(payment.to_dict()), payment.payment_id),
            )

    @staticmethod
    def _payment(row: sqlite3.Row | None) -> Payment | None:
        return Payment.from_dict(json.loads(row['data'])) if row else None

    def get_payment(self, payment_id: int) -> Payment | None:
        with self._lock:
            row = self._db.execute('SELECT data FROM payments WHERE payment_id = ?', (payment_id,)).fetchone()
        return self._payment(row)

    def get_payment_by_customer(self, customer: str) -> Payment | None:
        with self._lock:
            row = self._db.execute('SELECT data FROM payments WHERE customer = ?', (customer,)).fetchone()
        return self._payment(row)

    def latest_payment_by_order(self, merchant_id: str, order_id: str) -> Payment | None:
        with self._lock:
            row = self._db.execute(
                'SELECT data FROM payments WHERE merchant_id = ? AND order_id = ? ORDER BY payment_id DESC LIMIT 1',
                (merchant_id, order_id),
            ).fetchone()
        return self._payment(row)

    def list_payments(
        self,
        *,
        merchant_id: str | None = None,
        order_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[Payment]:
        clauses, args = [], []
        for column, value in (('merchant_id', merchant_id), ('order_id', order_id), ('status', status)):
            if value is not None:
                clauses.append(f'{column} = ?')
                args.append(value)
        where = f'WHERE {" AND ".join(clauses)}' if clauses else ''
        with self._lock:
            rows = self._db.execute(
                f'SELECT data FROM payments {where} ORDER BY payment_id DESC LIMIT ?',  # noqa: S608 - fixed columns
                (*args, limit),
            ).fetchall()
        return [p for p in (self._payment(r) for r in rows) if p]

    def expired_pending(self, now_iso: str) -> list[Payment]:
        marks = ','.join('?' * len(PENDING_STATUSES))
        with self._lock:
            rows = self._db.execute(
                f'SELECT data FROM payments WHERE status IN ({marks}) AND expires_at <= ?',  # noqa: S608
                (*PENDING_STATUSES, now_iso),
            ).fetchall()
        return [p for p in (self._payment(r) for r in rows) if p]

    def successful_uncaptured(self) -> list[Payment]:
        with self._lock:
            rows = self._db.execute('SELECT data FROM payments WHERE status = ?', (SUCCESS,)).fetchall()
        payments = [p for p in (self._payment(r) for r in rows) if p]
        return [p for p in payments if not p.auto_clearing and not p.captured and not p.auto_processed]

    # -- operations ---------------------------------------------------------

    def insert_operation(self, op: Operation) -> None:
        with self._lock:
            self._db.execute(
                'INSERT INTO operations (op_id, payment_id, data) VALUES (?, ?, ?)',
                (op.op_id, op.payment_id, json.dumps(op.to_dict())),
            )

    def operations(self, payment_id: int) -> list[Operation]:
        with self._lock:
            rows = self._db.execute(
                'SELECT data FROM operations WHERE payment_id = ? ORDER BY op_id', (payment_id,)
            ).fetchall()
        return [Operation.from_dict(json.loads(r['data'])) for r in rows]

    # -- idempotency --------------------------------------------------------

    def get_idempotent(self, merchant_id: str, scope: str, key: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute(
                'SELECT response FROM idempotency WHERE merchant_id = ? AND scope = ? AND key = ?',
                (merchant_id, scope, key),
            ).fetchone()
        return json.loads(row['response']) if row else None

    def put_idempotent(self, merchant_id: str, scope: str, key: str, response: dict[str, Any], now_iso: str) -> None:
        with self._lock:
            self._db.execute(
                'INSERT OR IGNORE INTO idempotency (merchant_id, scope, key, response, created_at) '
                'VALUES (?, ?, ?, ?, ?)',
                (merchant_id, scope, key, json.dumps(response), now_iso),
            )

    # -- callback jobs ------------------------------------------------------

    def create_job(self, payment_id: int, kind: str, next_attempt_iso: str, now_iso: str, data: dict[str, Any]) -> int:
        with self._lock:
            cursor = self._db.execute(
                'INSERT INTO callback_jobs (payment_id, kind, state, attempts, created_at, next_attempt_at, data) '
                "VALUES (?, ?, 'pending', 0, ?, ?, ?)",
                (payment_id, kind, now_iso, next_attempt_iso, json.dumps(data)),
            )
            return int(cursor.lastrowid)

    @staticmethod
    def _job(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        job = dict(row)
        job['data'] = json.loads(job['data'])
        return job

    def claim_job(self, job_id: int) -> dict[str, Any] | None:
        """Atomically move a pending job to ``running``; ``None`` if somebody else has it."""
        with self.tx() as db:
            cursor = db.execute(
                "UPDATE callback_jobs SET state = 'running' WHERE job_id = ? AND state = 'pending'", (job_id,)
            )
            if cursor.rowcount != 1:
                return None
            return self._job(db.execute('SELECT * FROM callback_jobs WHERE job_id = ?', (job_id,)).fetchone())

    def due_job_ids(self, now_iso: str) -> list[int]:
        with self._lock:
            rows = self._db.execute(
                "SELECT job_id FROM callback_jobs WHERE state = 'pending' AND next_attempt_at <= ? "
                'ORDER BY next_attempt_at, job_id',
                (now_iso,),
            ).fetchall()
        return [r['job_id'] for r in rows]

    def finish_job(
        self, job_id: int, *, state: str, attempts: int, first_attempt_iso: str | None, next_attempt_iso: str
    ) -> None:
        with self._lock:
            self._db.execute(
                'UPDATE callback_jobs SET state = ?, attempts = ?, first_attempt_at = ?, next_attempt_at = ? '
                'WHERE job_id = ?',
                (state, attempts, first_attempt_iso, next_attempt_iso, job_id),
            )

    def jobs(self, payment_id: int) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute(
                'SELECT * FROM callback_jobs WHERE payment_id = ? ORDER BY job_id', (payment_id,)
            ).fetchall()
        return [j for j in (self._job(r) for r in rows) if j]

    # -- delivery log -------------------------------------------------------

    def add_delivery(self, payment_id: int, job_id: int | None, data: dict[str, Any]) -> None:
        with self._lock:
            self._db.execute(
                'INSERT INTO deliveries (payment_id, job_id, data) VALUES (?, ?, ?)',
                (payment_id, job_id, json.dumps(data)),
            )

    def deliveries(self, payment_id: int) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute(
                'SELECT delivery_id, job_id, data FROM deliveries WHERE payment_id = ? ORDER BY delivery_id',
                (payment_id,),
            ).fetchall()
        return [{'delivery_id': r['delivery_id'], 'job_id': r['job_id'], **json.loads(r['data'])} for r in rows]

    # -- faults -------------------------------------------------------------

    def add_fault(self, endpoint: str, data: dict[str, Any]) -> int:
        with self._lock:
            cursor = self._db.execute('INSERT INTO faults (endpoint, data) VALUES (?, ?)', (endpoint, json.dumps(data)))
            return int(cursor.lastrowid)

    def faults(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute('SELECT fault_id, endpoint, data FROM faults ORDER BY fault_id').fetchall()
        return [{'fault_id': r['fault_id'], 'endpoint': r['endpoint'], **json.loads(r['data'])} for r in rows]

    def update_fault(self, fault_id: int, data: dict[str, Any] | None) -> None:
        with self._lock:
            if data is None:
                self._db.execute('DELETE FROM faults WHERE fault_id = ?', (fault_id,))
            else:
                self._db.execute('UPDATE faults SET data = ? WHERE fault_id = ?', (json.dumps(data), fault_id))

    def clear_faults(self) -> int:
        with self._lock:
            return self._db.execute('DELETE FROM faults').rowcount

    # -- reset --------------------------------------------------------------

    def reset(self) -> None:
        """Forget every payment, job, fault and the clock offset.

        The id sequence is kept on purpose: a client holding an old
        ``pg_payment_id`` must not see it reused by a new payment.
        """
        with self.tx() as db:
            for table in ('deliveries', 'callback_jobs', 'idempotency', 'operations', 'payments', 'faults'):
                db.execute(f'DELETE FROM {table}')  # noqa: S608 - fixed table names
            db.execute("DELETE FROM meta WHERE key <> 'id_sequence'")
