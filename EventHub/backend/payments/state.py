"""Payment state machine (ADR 0001, section 2).

`TRANSITIONS` is the single source of truth for the allowed status changes.
`transition()` is the one function meant to change `Payment.status`; the
switch work package (WP1b) moves the remaining direct assignments in the
legacy services onto it.

The database half of the enforcement is `status_trigger_sql()`: a
PostgreSQL BEFORE UPDATE trigger generated from the same table. It is
deliberately not installed yet, because the legacy services still make
moves the table forbids (a late payment goes `pending -> refunded` in one
step). WP1b installs it with
`migrations.RunSQL(status_trigger_sql(), DROP_STATUS_TRIGGER_SQL)` once no
code path makes such a move any more; payments/test_state.py installs it
inside a test transaction to prove it matches the table.
"""

import logging

from django.utils import timezone

from common.choices import PaymentStatusChoices as Status

logger = logging.getLogger(__name__)

TRANSITIONS: dict[str, frozenset[str]] = {
    Status.PENDING: frozenset({Status.COMPLETED, Status.FAILED, Status.EXPIRED}),
    # A new attempt, or a provider reporting success after all.
    Status.FAILED: frozenset({Status.PENDING, Status.COMPLETED}),
    # A new attempt, or money that arrived after the session expired.
    Status.EXPIRED: frozenset({Status.PENDING, Status.COMPLETED}),
    Status.COMPLETED: frozenset({Status.REFUNDED, Status.DISPUTED}),
    # Dispute won, or lost / refunded.
    Status.DISPUTED: frozenset({Status.COMPLETED, Status.REFUNDED}),
    Status.REFUNDED: frozenset(),
}

TRIGGER_NAME = 'payments_payment_status_guard'
DROP_STATUS_TRIGGER_SQL = (
    f'DROP TRIGGER IF EXISTS {TRIGGER_NAME} ON payments_payment; DROP FUNCTION IF EXISTS {TRIGGER_NAME}();'
)


class IllegalPaymentTransition(Exception):
    """The requested status change is not in TRANSITIONS, or the payment
    changed underneath the caller."""

    def __init__(self, payment_id, from_status, to_status, detail=''):
        self.payment_id = payment_id
        self.from_status = from_status
        self.to_status = to_status
        message = f'Payment {payment_id}: {from_status} -> {to_status} is not allowed'
        super().__init__(f'{message} ({detail})' if detail else message)


def can_transition(from_status: str, to_status: str) -> bool:
    return to_status in TRANSITIONS.get(from_status, frozenset())


def transition(payment, to: str, *, reason: str = ''):
    """Move `payment` to status `to` and persist only that change.

    The write is a compare-and-set on the status the caller has seen, so a
    concurrent change (another worker, a stale object) raises instead of
    being overwritten. Callers still take the Payment row lock first (lock
    order: Payment, then its target); this check is the safety net.
    """
    current = payment.status
    if not can_transition(current, to):
        raise IllegalPaymentTransition(payment.pk, current, to)

    from .models import Payment

    now = timezone.now()
    updated = Payment.objects.filter(pk=payment.pk, status=current).update(status=to, updated_at=now)
    if updated != 1:
        actual = Payment.objects.filter(pk=payment.pk).values_list('status', flat=True).first()
        raise IllegalPaymentTransition(payment.pk, current, to, f'the stored status is {actual}')
    payment.status = to
    payment.updated_at = now
    logger.info('Payment %s: %s -> %s%s', payment.pk, current, to, f' ({reason})' if reason else '')
    return payment


def status_trigger_sql() -> str:
    """SQL that installs the BEFORE UPDATE trigger enforcing TRANSITIONS."""
    pairs = ', '.join(
        f"('{source}', '{target}')" for source in sorted(TRANSITIONS) for target in sorted(TRANSITIONS[source])
    )
    return f"""
CREATE OR REPLACE FUNCTION {TRIGGER_NAME}() RETURNS trigger AS $$
BEGIN
    IF NEW.status IS DISTINCT FROM OLD.status
       AND (OLD.status::text, NEW.status::text) NOT IN (VALUES {pairs}) THEN
        RAISE EXCEPTION 'illegal payment status transition % -> % (payment %)',
            OLD.status, NEW.status, OLD.id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS {TRIGGER_NAME} ON payments_payment;
CREATE TRIGGER {TRIGGER_NAME}
    BEFORE UPDATE OF status ON payments_payment
    FOR EACH ROW EXECUTE FUNCTION {TRIGGER_NAME}();
"""
