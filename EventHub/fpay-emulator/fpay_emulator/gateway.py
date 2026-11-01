"""Payment engine: lifecycle, money operations and the scheduler tick.

Endpoints, the hosted page and the control API all go through this class, so
a payment behaves the same whether a browser, a test or the clock drives it.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from . import cards, errors
from .callbacks import Notifier, Verdict
from .clock import Clock
from .config import Merchant, Settings
from .errors import ApiError
from .faults import FaultRegistry
from .models import (
    CANCEL,
    ERROR,
    NEW,
    PENDING_STATUSES,
    PROCESS,
    REFUND,
    SUCCESS,
    WAITING,
    Operation,
    Payment,
    iso,
)
from .store import Store

log = logging.getLogger('fpay.gateway')


@dataclass
class Money:
    """Derived money state of a payment."""

    refunded: Decimal
    cancelled: Decimal
    is_cancelled: bool

    @property
    def returned(self) -> Decimal:
        return self.refunded + self.cancelled


class Gateway:
    def __init__(
        self,
        settings: Settings,
        store: Store,
        clock: Clock,
        notifier: Notifier,
        faults: FaultRegistry,
    ) -> None:
        self.settings = settings
        self.store = store
        self.clock = clock
        self.notifier = notifier
        self.faults = faults
        self._locks: dict[int, asyncio.Lock] = {}
        self.busy: dict[int, str] = {}
        self._tick_lock = asyncio.Lock()

    # -- helpers ------------------------------------------------------------

    def lock(self, payment_id: int) -> asyncio.Lock:
        lock = self._locks.get(payment_id)
        if lock is None:
            lock = self._locks[payment_id] = asyncio.Lock()
        return lock

    def now(self) -> datetime:
        return self.clock.now()

    def local_time(self, moment: datetime) -> str:
        return moment.astimezone(self.settings.tz).strftime('%Y-%m-%d %H:%M:%S')

    def redirect_url(self, payment: Payment) -> str:
        return f'{self.settings.public_url}/pay.html?customer={payment.customer}'

    def _reference(self, seed: int) -> str:
        """RRN-like 12-digit reference: ``yyMMdd`` of the virtual clock and six digits of an id."""
        return self.now().strftime('%y%m%d') + f'{seed % 1_000_000:06d}'

    def money(self, payment: Payment, ops: list[Operation] | None = None) -> Money:
        ops = self.store.operations(payment.payment_id) if ops is None else ops
        refunded = sum((o.amount for o in ops if o.kind == REFUND and o.status == SUCCESS), Decimal(0))
        cancels = [o for o in ops if o.kind == CANCEL and o.status == SUCCESS]
        cancelled = sum((o.amount for o in cancels), Decimal(0))
        return Money(refunded=refunded, cancelled=cancelled, is_cancelled=bool(cancels))

    def merchant_of(self, payment: Payment) -> Merchant | None:
        return self.settings.merchant(payment.merchant_id)

    # -- creation -----------------------------------------------------------

    def create_payment(self, merchant: Merchant, values: dict[str, Any]) -> Payment:
        now = self.now()
        payment = Payment(
            payment_id=self.store.next_id(),
            merchant_id=merchant.merchant_id,
            customer=str(uuid.uuid4()),
            created_at=now,
            expires_at=now + timedelta(seconds=values['lifetime']),
            **values,
        )
        self.store.insert_payment(payment)
        log.info(
            'payment created',
            extra={
                'payment_id': payment.payment_id,
                'merchant_id': merchant.merchant_id,
                'order_id': payment.order_id,
                'amount': str(payment.amount),
                'currency': payment.currency,
            },
        )
        return payment

    # -- expiry -------------------------------------------------------------

    def expire_if_due(self, payment: Payment) -> bool:
        """Lazily expire an unpaid payment; the Result call goes out on the next tick."""
        if payment.status not in PENDING_STATUSES or payment.expires_at > self.now():
            return False
        payment.status = ERROR
        payment.failure_code = errors.LIFETIME_EXPIRED
        payment.failure_description = errors.failure_text(errors.LIFETIME_EXPIRED)
        payment.paid_at = self.now()
        payment.challenge = None
        payment.can_reject = False
        self.store.save_payment(payment)
        if self.settings.result_on_expiry:
            self.notifier.enqueue_result(payment)
        log.info('payment expired', extra={'payment_id': payment.payment_id})
        return True

    # -- settlement ---------------------------------------------------------

    def mark_waiting(self, payment: Payment) -> None:
        if payment.status == NEW:
            payment.status = WAITING
            self.store.save_payment(payment)

    async def run_check(self, payment: Payment) -> Verdict | None:
        verdict = await self.notifier.check(payment)
        if verdict is not None and verdict.verdict != 'ok':
            description = verdict.description or f'Check refused ({verdict.verdict})'
            await self.settle_failure(payment, self.settings.reject_failure_code, description)
        return verdict

    async def start(
        self, payment: Payment, scenario: str, *, card: dict[str, str] | None = None, failure_code: str | None = None
    ) -> str:
        """Apply a buyer action or a pre-set scenario. Returns the next page: result, 3ds, processing, waiting."""
        if payment.is_final:
            return 'result'
        if self.expire_if_due(payment):
            return 'result'
        if scenario == cards.ABANDON:
            self.mark_waiting(payment)
            return 'waiting'
        if scenario == cards.HANG:
            payment.status = PROCESS
            payment.payment_method = 'bankcard'
            self.store.save_payment(payment)
            return 'processing'
        card = card or cards.card_record(cards.DEFAULT_CARD, '12', '30', 'TEST CARDHOLDER')
        payment.card = card
        payment.payment_method = 'bankcard'
        payment.status = PROCESS
        self.store.save_payment(payment)
        verdict = await self.run_check(payment)
        if verdict is not None and verdict.verdict != 'ok':
            return 'result'
        if scenario in (cards.THREE_DS_SUCCESS, cards.THREE_DS_FAIL):
            payment.challenge = {'expected': 'success' if scenario == cards.THREE_DS_SUCCESS else 'fail'}
            self.store.save_payment(payment)
            return '3ds'
        if scenario == cards.DECLINE:
            await self.settle_failure(payment, failure_code or errors.INSUFFICIENT_FUNDS)
            return 'result'
        await self.settle_success(payment)
        return 'result'

    async def finish_challenge(self, payment: Payment, passed: bool) -> None:
        if payment.is_final or payment.challenge is None:
            return
        if self.expire_if_due(payment):
            return
        payment.challenge = None
        if passed:
            await self.settle_success(payment)
        else:
            await self.settle_failure(payment, errors.THREE_DS_FAILED)

    async def settle_success(self, payment: Payment) -> None:
        now = self.now()
        payment.status = SUCCESS
        payment.paid_at = now
        payment.reference = self._reference(payment.payment_id)
        payment.auth_code = f'{secrets.randbelow(1_000_000):06d}'
        payment.failure_code = payment.failure_description = None
        if payment.auto_clearing:
            payment.captured = True
            payment.captured_at = now
            payment.clearing_amount = payment.amount
        payment.can_reject = bool(payment.result_url)
        self.store.save_payment(payment)
        log.info('payment succeeded', extra={'payment_id': payment.payment_id})
        await self._notify(payment)

    async def settle_failure(self, payment: Payment, code: str, description: str | None = None) -> None:
        payment.status = ERROR
        payment.paid_at = self.now()
        payment.reference = payment.reference or self._reference(payment.payment_id)
        payment.failure_code = code
        payment.failure_description = description or errors.failure_text(code)
        payment.can_reject = False
        payment.challenge = None
        self.store.save_payment(payment)
        log.info('payment declined', extra={'payment_id': payment.payment_id, 'failure_code': code})
        await self._notify(payment)

    async def _notify(self, payment: Payment) -> None:
        job_id = self.notifier.enqueue_result(payment)
        if job_id is not None:
            await self.notifier.deliver_job(job_id, self.merchant_rejected)

    def merchant_rejected(self, payment_id: int, description: str | None) -> None:
        """The merchant answered ``rejected`` to a Result with ``pg_can_reject=1``: roll back."""
        payment = self.store.get_payment(payment_id)
        if payment is None or payment.status != SUCCESS or payment.merchant_rejected:
            return
        amount = payment.clearing_amount if payment.captured else payment.amount
        op_id = self.store.next_id()
        self.store.insert_operation(
            Operation(
                op_id=op_id,
                payment_id=payment_id,
                kind=CANCEL,
                status=SUCCESS,
                amount=amount,
                created_at=self.now(),
                reference=self._reference(op_id),
                origin='merchant_rejected',
            )
        )
        payment.merchant_rejected = True
        payment.merchant_reply_description = description
        payment.can_reject = False
        self.store.save_payment(payment)
        log.info('payment rejected by the merchant', extra={'payment_id': payment_id})

    # -- capture ------------------------------------------------------------

    def capture(self, payment: Payment, amount: Decimal | None) -> Decimal:
        """``do_capture.php``. Returns the captured (clearing) amount."""
        if payment.status != SUCCESS or payment.card is None:
            raise ApiError(errors.CAPTURE_NOT_POSSIBLE)
        if payment.captured:
            return payment.clearing_amount  # one clearing per payment; a repeat returns it
        if self.money(payment).is_cancelled:
            return Decimal(0)  # released hold: nothing captured
        amount = amount or payment.amount
        if amount > payment.amount:
            raise ApiError(errors.CLEARING_AMOUNT_EXCEEDED)
        payment.captured = True
        payment.captured_at = self.now()
        payment.clearing_amount = amount
        self.store.save_payment(payment)
        log.info('payment captured', extra={'payment_id': payment.payment_id, 'amount': str(amount)})
        return amount

    # -- cancel and refund --------------------------------------------------

    def _record(
        self,
        payment: Payment,
        kind: str,
        status: str,
        amount: Decimal,
        *,
        failure_code: str | None = None,
        idempotency_key: str | None = None,
        origin: str = 'api',
    ) -> Operation:
        op_id = self.store.next_id()
        op = Operation(
            op_id=op_id,
            payment_id=payment.payment_id,
            kind=kind,
            status=status,
            amount=amount,
            created_at=self.now(),
            reference=self._reference(op_id),
            failure_code=failure_code,
            failure_description=errors.failure_text(failure_code) if failure_code else None,
            idempotency_key=idempotency_key,
            origin=origin,
        )
        self.store.insert_operation(op)
        return op

    def cancel(self, payment: Payment, idempotency_key: str | None = None, origin: str = 'api') -> Operation:
        """``/cancel``: release a hold, or refund a captured payment in full (S9)."""
        money = self.money(payment)
        failure = None
        if payment.status != SUCCESS:
            failure = errors.NOT_SUCCESSFUL
        elif money.is_cancelled:
            failure = errors.ALREADY_CANCELLED
        elif money.refunded > 0 or (payment.captured and payment.clearing_amount < payment.amount):
            failure = errors.CANNOT_REFUND  # partial refund or partial clearing: only revoke works
        if failure:
            return self._record(
                payment,
                CANCEL,
                ERROR,
                payment.amount,
                failure_code=failure,
                idempotency_key=idempotency_key,
                origin=origin,
            )
        amount = payment.clearing_amount if payment.captured else payment.amount
        payment.can_reject = False
        self.store.save_payment(payment)
        op = self._record(payment, CANCEL, SUCCESS, amount, idempotency_key=idempotency_key, origin=origin)
        log.info('payment cancelled', extra={'payment_id': payment.payment_id, 'captured': payment.captured})
        return op

    def refund(self, payment: Payment, amount: Decimal | None, idempotency_key: str | None = None) -> Operation:
        """``/revoke``: full or partial refund of the remainder (S8)."""
        if not self.settings.refunds_enabled:
            raise ApiError(errors.ACTION_DISABLED)
        if payment.status != SUCCESS:
            raise ApiError(errors.REFUND_NOT_SUCCESSFUL)
        money = self.money(payment)
        if not payment.captured and money.is_cancelled:
            raise ApiError(errors.REFUND_NOT_CAPTURABLE)
        window = timedelta(days=self.settings.refund_window_days)
        if self.settings.refund_window_days and payment.paid_at and self.now() - payment.paid_at > window:
            raise ApiError(errors.TOO_OLD)
        if not payment.captured:
            # Two-step payment: revoke captures the full amount first (S8).
            self.capture(payment, None)
        remainder = payment.clearing_amount - money.returned
        requested = amount or remainder
        if remainder <= 0 or requested > remainder:
            return self._record(
                payment,
                REFUND,
                ERROR,
                requested if requested > 0 else Decimal(0),
                failure_code=errors.CANNOT_REFUND,
                idempotency_key=idempotency_key,
            )
        payment.can_reject = False
        self.store.save_payment(payment)
        op = self._record(payment, REFUND, SUCCESS, requested, idempotency_key=idempotency_key)
        log.info('payment refunded', extra={'payment_id': payment.payment_id, 'amount': str(requested)})
        return op

    # -- scheduler ----------------------------------------------------------

    def _auto_process(self) -> int:
        days = self.settings.auto_capture_days
        if not days:
            return 0
        done = 0
        for payment in self.store.successful_uncaptured():
            if payment.testing_mode and not self.settings.auto_process_test_payments:
                continue  # test payments are not auto-processed (S10, S11)
            if payment.paid_at is None or self.now() - payment.paid_at < timedelta(days=days):
                continue
            if self.money(payment).is_cancelled:
                continue
            if self.settings.auto_capture_action == 'capture':
                self.capture(payment, None)
            else:
                self.cancel(payment, origin='auto_cancel')
            payment = self.store.get_payment(payment.payment_id) or payment
            payment.auto_processed = self.settings.auto_capture_action
            self.store.save_payment(payment)
            done += 1
        return done

    async def tick(self) -> dict[str, int]:
        """Expire, auto-capture and deliver everything that is due on the virtual clock."""
        async with self._tick_lock:
            expired = 0
            for payment in self.store.expired_pending(iso(self.now())):
                expired += int(self.expire_if_due(payment))
            auto = self._auto_process()
            attempts = 0
            for _ in range(1000):
                due = self.store.due_job_ids(iso(self.now()))
                if not due:
                    break
                for job_id in due:
                    if await self.notifier.deliver_job(job_id, self.merchant_rejected) is not None:
                        attempts += 1
            return {'expired': expired, 'auto_processed': auto, 'callback_attempts': attempts}

    async def run_scheduler(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                await self.tick()
            except Exception:
                log.exception('scheduler tick failed')
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=self.settings.scheduler_tick_seconds)
