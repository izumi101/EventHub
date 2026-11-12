"""Copy the legacy Stripe payment data into the provider-neutral ledger.

Expand step of ADR 0001 (docs/adr/0001-payment-provider-layer.md), data part.

1. Every ticket `Payment` gets `provider`, `provider_session_id`,
   `provider_payment_id` and `attempt` derived from its `stripe_*` columns:
   - `method == 'offline'` -> provider `offline`; a Stripe id such a row may
     still carry is kept in `provider_payload` only, never as a provider id,
     so a refund can never be sent to Stripe for money taken in cash;
   - only `mock_*` ids (STRIPE_MOCK_MODE) -> provider `mock`;
   - any other Stripe id -> provider `stripe`;
   - no id at all -> provider stays empty (no provider attempt was made).
   Only empty new columns are filled; values written by newer code win.
2. Every group `Booking` with money state gets the `Payment` row it never had
   (`booking=...`, registration NULL): bookings with a session or payment
   intent id, and every confirmed or refunded booking. Status mapping:
   - `refunded` booking -> `refunded`, `refunded_amount = amount`;
   - `confirmed` booking -> `completed`;
   - expired / cancelled / holding booking with a payment intent (money
     arrived after the hold ended) -> `refunded` when the booking records a
     refund, otherwise `completed` and flagged `needs_review`;
   - `holding` booking with a session -> `pending`;
   - expired / cancelled booking with a session but no payment intent (the
     buyer never paid) -> `expired`. That value is declared as a choice by
     the state-machine migration of the same release; choices are not
     enforced by the database.
   `amount` is `amount_paid`, else the seat total (zone price plus tax and
   fees, a frozen copy of `events.billing.quote_breakdown`), else 0 with
   `amount_source = 'unknown'`. `currency` is the event currency, lower case
   like every existing Payment row (case normalisation is part of the switch).
   The rows carry `provider_payload.legacy_import`; on a re-run they are
   re-derived from the booking, which stays the source of truth until the
   switch.

The legacy columns stay and the current services keep writing them, so this
copy goes stale for rows written after it ran. The function is idempotent:
the work package that switches the code to the new columns (WP1b) runs it
again in its own migration right before the contract step, which drops the
`stripe_*` columns, e.g. with
`RunPython(import_module('payments.migrations.0005_copy_legacy_payments').copy_legacy_payments)`.

Reverse: deletes the booking Payment rows this migration created (marked
with `legacy_import`) and refuses to continue while other booking Payments
exist, because the schema reversal makes `registration` mandatory again. The
values copied into ticket Payments are left alone: reversing the schema
migration drops those columns.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.db import migrations
from django.db.models import Q
from django.utils import timezone

MIGRATION = '0005_copy_legacy_payments'
MARKER = 'legacy_import'

CENT = Decimal('0.01')


def _q(value) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def _provider_for(*ids, method=''):
    if method == 'offline':
        return 'offline'
    present = [value for value in ids if value]
    if not present:
        return ''
    if all(value.startswith('mock_') for value in present):
        return 'mock'
    return 'stripe'


def _seat_total(event, price) -> Decimal:
    """Frozen copy of events.billing.quote_breakdown(event, price)['total']
    (group bookings carry no promo code)."""
    base = _q(price)
    tax_pct = Decimal(str(event.tax_percent or 0))
    fee_pct = Decimal(str(event.service_fee_percent or 0))
    tax = _q(base * tax_pct / Decimal('100')) if base > 0 else Decimal('0.00')
    fee = _q(base * fee_pct / Decimal('100')) if base > 0 else Decimal('0.00')
    return _q(base + tax + fee) if event.fees_passed_to_buyer else base


def _booking_amount(booking, BookingSeat):
    if booking.amount_paid is not None:
        return _q(booking.amount_paid), 'amount_paid'
    prices = list(BookingSeat.objects.filter(booking_id=booking.pk).values_list('price', flat=True))
    if prices:
        return sum((_seat_total(booking.event, price) for price in prices), Decimal('0.00')), 'seats'
    return Decimal('0.00'), 'unknown'


def _booking_status(booking):
    """(payment status, needs_review) for a legacy booking."""
    if booking.status == 'refunded':
        return 'refunded', False
    if booking.status == 'confirmed':
        return 'completed', False
    if booking.stripe_payment_intent_id:
        if booking.refunded_at is not None:
            return 'refunded', False
        return 'completed', True
    if booking.status == 'holding':
        return 'pending', False
    return 'expired', False


def _session_id_is_free(Payment, provider, session_id, pk=None):
    taken = Payment.objects.filter(provider=provider, provider_session_id=session_id)
    if pk is not None:
        taken = taken.exclude(pk=pk)
    return not taken.exists()


def _copy_ticket_payments(Payment, counters):
    for payment in Payment.objects.filter(registration__isnull=False).order_by('pk').iterator():
        session, intent = payment.stripe_checkout_session_id, payment.stripe_payment_intent_id
        payload = dict(payment.provider_payload or {})
        if payment.provider and MARKER not in payload:
            counters['ticket_payments_kept'] += 1  # written by newer code
            continue
        derived = _provider_for(session, intent, method=payment.method)
        provider = payment.provider or derived
        updates = {}
        note = dict(payload.get(MARKER) or {})

        if not payment.provider and derived:
            updates['provider'] = derived
        if provider == derived and provider in ('stripe', 'mock'):
            if not payment.provider_session_id and session:
                if _session_id_is_free(Payment, provider, session, payment.pk):
                    updates['provider_session_id'] = session
                else:
                    note['session_id_conflict'] = session
            if not payment.provider_payment_id and intent:
                updates['provider_payment_id'] = intent
        elif derived == 'offline' and (session or intent):
            note['stripe_checkout_session_id'] = session
            note['stripe_payment_intent_id'] = intent
        if payment.attempt == 0 and (session or payment.provider_session_id):
            updates['attempt'] = 1

        if updates or MARKER not in payload:
            note.setdefault('source', 'payments.Payment')
            note.setdefault('migration', MIGRATION)
            payload[MARKER] = note
            updates['provider_payload'] = payload
        if updates:
            # QuerySet.update(): keeps `updated_at`, which records the last
            # real change of the payment.
            Payment.objects.filter(pk=payment.pk).update(**updates)
            counters['ticket_payments_updated'] += 1


def _copy_booking_payments(Payment, Booking, BookingSeat, counters):
    with_money = (
        ~Q(stripe_session_id='') | ~Q(stripe_payment_intent_id='') | Q(status__in=['confirmed', 'refunded'])
    )
    for booking in Booking.objects.filter(with_money).select_related('event').order_by('created_at', 'pk').iterator():
        session, intent = booking.stripe_session_id, booking.stripe_payment_intent_id
        provider = _provider_for(session, intent)
        status, needs_review = _booking_status(booking)
        amount, amount_source = _booking_amount(booking, BookingSeat)
        note = {
            'source': 'bookings.Booking',
            'migration': MIGRATION,
            'booking_status': booking.status,
            'amount_source': amount_source,
            'needs_review': needs_review,
        }
        values = {
            'provider': provider,
            'provider_payment_id': intent,
            'attempt': 1 if session else 0,
            'amount': amount,
            'currency': (booking.event.currency or 'USD').lower(),
            'status': status,
            'refunded_amount': amount if status == 'refunded' else Decimal('0.00'),
            'refunded_at': booking.refunded_at,
            'refund_reason': booking.refund_reason,
        }

        existing = Payment.objects.filter(booking_id=booking.pk).first()
        if existing is not None and MARKER not in (existing.provider_payload or {}):
            counters['booking_payments_kept'] += 1  # written by newer code
            continue
        pk = existing.pk if existing is not None else None
        if session and _session_id_is_free(Payment, provider, session, pk):
            values['provider_session_id'] = session
        else:
            values['provider_session_id'] = ''
            if session:
                note['session_id_conflict'] = session
        values['provider_payload'] = {MARKER: note}

        if existing is None:
            Payment.objects.create(booking_id=booking.pk, **values)
            counters['booking_payments_created'] += 1
        elif any(getattr(existing, field) != value for field, value in values.items()):
            Payment.objects.filter(pk=existing.pk).update(**values, updated_at=timezone.now())
            counters['booking_payments_updated'] += 1


def copy_legacy_payments(apps, schema_editor=None):
    Payment = apps.get_model('payments', 'Payment')
    Booking = apps.get_model('bookings', 'Booking')
    BookingSeat = apps.get_model('bookings', 'BookingSeat')
    counters = {
        'ticket_payments_updated': 0,
        'ticket_payments_kept': 0,
        'booking_payments_created': 0,
        'booking_payments_updated': 0,
        'booking_payments_kept': 0,
    }
    _copy_ticket_payments(Payment, counters)
    _copy_booking_payments(Payment, Booking, BookingSeat, counters)
    return counters


def remove_copied_booking_payments(apps, schema_editor=None):
    Payment = apps.get_model('payments', 'Payment')
    booking_payments = Payment.objects.filter(booking__isnull=False)
    booking_payments.filter(provider_payload__has_key=MARKER).delete()
    if booking_payments.exists():
        raise RuntimeError(
            'Booking payments written after the legacy copy exist; reversing would lose them because '
            'payments.registration becomes mandatory again. Move them back to the booking first.'
        )


class Migration(migrations.Migration):
    dependencies = [
        ('bookings', '0003_booking_refunds'),
        ('events', '0016_registration_history_constraints_and_indexes'),
        ('payments', '0004_ledger_models'),
    ]

    operations = [
        migrations.RunPython(copy_legacy_payments, remove_copied_booking_payments, elidable=False),
    ]
