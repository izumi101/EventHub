"""One known defect per SQL data check, to prove that each check catches it.

Used by the tests (events/test_sql_checks.py) and by
`manage.py run_sql_checks --inject-defects`, always inside a transaction that
is rolled back afterwards. Every defect builds its own small set of rows, so
it does not depend on (and never changes) existing data.
"""

import uuid
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import DatabaseError, connection, transaction
from django.utils import timezone

from accounts.models import UserProfile
from bookings.models import Booking
from events.models import (
    CheckInList,
    CheckInLog,
    Event,
    EventSeat,
    PromoCode,
    RefundRequest,
    Registration,
    Review,
    SeatMap,
    TicketType,
    WaitlistEntry,
)
from jobs.models import Job
from payments.models import Payment, Refund

PRICE = Decimal('5000.00')


class DefectSkipped(Exception):
    """The defect needs more rights than the current connection has."""


class Factory:
    def __init__(self):
        self.now = timezone.now()

    def user(self, role='attendee', **fields):
        tag = uuid.uuid4().hex[:10]
        user = User.objects.create(username=f'defect_{tag}', email=f'defect_{tag}@example.invalid', **fields)
        UserProfile.objects.filter(user=user).update(role=role)
        return user

    def event(self, organizer=None, **fields):
        values = {
            'title': 'Defect probe',
            'description': 'Injected by sql_check_defects',
            'organizer': organizer or self.user('organizer'),
            'date': self.now + timedelta(days=7),
            'end_date': self.now + timedelta(days=7, hours=3),
            'location': 'Probe Hall, Almaty',
            'status': 'published',
            'max_participants': 10,
            'price': PRICE,
            'currency': 'KZT',
        }
        values.update(fields)
        return Event.objects.create(**values)

    def registration(self, event, user=None, **fields):
        values = {'status': 'confirmed'}
        values.update(fields)
        return Registration.objects.create(user=user or self.user(), event=event, **values)

    def payment(self, registration=None, booking=None, **fields):
        values = {'amount': PRICE, 'currency': 'kzt', 'status': 'completed'}
        values.update(fields)
        return Payment.objects.create(registration=registration, booking=booking, **values)

    def seat(self, event, available=False, row=1, col=1):
        seat_map, _ = SeatMap.objects.get_or_create(event=event, defaults={'rows': 1, 'cols': 1})
        return EventSeat.objects.create(seat_map=seat_map, row=row, col=col, is_available=available)

    def refund(self, payment, amount, status='succeeded'):
        return Refund.objects.create(
            payment=payment,
            amount=amount,
            currency=payment.currency.upper(),
            kind=Refund.Kind.CUSTOMER,
            status=status,
            provider='mock',
            processed_at=self.now if status != 'pending' else None,
        )


def capacity_overrun(f):
    event = f.event(max_participants=1, price=0)
    f.registration(event)
    f.registration(event)


def seat_held_twice(f):
    event = f.event(price=0)
    seat = f.seat(event)
    f.registration(event, seat=seat)
    f.registration(event, seat=seat)


def seat_marked_free_but_taken(f):
    event = f.event(price=0)
    f.registration(event, seat=f.seat(event, available=True))


def seat_blocked_without_holder(f):
    f.seat(f.event(), available=False)


def cross_event_references(f):
    event, other = f.event(price=0), f.event(price=0)
    tier = TicketType.objects.create(event=other, name='Other event tier', kind='free', price=0)
    f.registration(event, ticket_type=tier)


def confirmed_paid_ticket_without_payment(f):
    f.registration(f.event(), locked_price=PRICE)


def money_kept_for_void_ticket(f):
    f.payment(f.registration(f.event(), status='cancelled', locked_price=PRICE))


def payment_amounts_invalid(f):
    reg = f.registration(f.event(), locked_price=PRICE)
    f.payment(reg, refunded_amount=PRICE + 2000, refunded_at=f.now)


def currency_mismatch(f):
    reg = f.registration(f.event(), locked_price=PRICE)
    f.payment(reg, currency='usd')


def refund_ledger_over_refund(f):
    reg = f.registration(f.event(), locked_price=PRICE)
    payment = f.payment(reg, status='refunded', refunded_amount=PRICE, refunded_at=f.now)
    f.refund(payment, Decimal('3000.00'))
    f.refund(payment, Decimal('3000.00'))


def refund_ledger_drift(f):
    payment = f.payment(f.registration(f.event(), locked_price=PRICE))
    f.refund(payment, Decimal('1000.00'))


def stale_holds(f):
    f.registration(f.event(), status='pending', locked_price=PRICE, seat_held_until=f.now - timedelta(hours=1))


def checkin_on_invalid_ticket(f):
    f.registration(f.event(price=0), status='cancelled', is_checked_in=True, checked_in_at=f.now)


def checkin_outside_event_window(f):
    event = f.event(price=0, date=f.now - timedelta(days=1), end_date=f.now - timedelta(hours=21), status='completed')
    f.registration(event, is_checked_in=True, checked_in_at=event.date - timedelta(days=2))


def checkin_log_wrong_event(f):
    event, other = f.event(price=0), f.event(price=0)
    gate = CheckInList.objects.create(event=other, name='Other event gate')
    CheckInLog.objects.create(checkin_list=gate, registration=f.registration(event))


def organizer_ticket_for_own_event(f):
    event = f.event(price=0)
    f.registration(event, user=event.organizer)


def tickets_held_by_non_attendees(f):
    f.registration(f.event(price=0), user=f.user(is_staff=True))


def duplicate_active_registrations(f):
    # The partial unique index forbids this; only the schema owner can drop it
    # (inside the rolled-back transaction) to simulate a lost index.
    try:
        with transaction.atomic(), connection.cursor() as cur:
            cur.execute('DROP INDEX uniq_active_registration_per_user_event')
    except DatabaseError as exc:
        raise DefectSkipped('needs the schema owner to drop the unique index (DJANGO_DB_AS_OWNER=1)') from exc
    event, user = f.event(price=0), f.user()
    f.registration(event, user=user)
    f.registration(event, user=user)


def promo_over_max_uses(f):
    PromoCode.objects.create(event=f.event(), code='DEFECT1', discount_value=10, max_uses=1, times_used=2)


def promo_counter_drift(f):
    PromoCode.objects.create(event=f.event(), code='DEFECT2', discount_value=10, times_used=3)


def ticket_type_oversold(f):
    event = f.event(price=0)
    tier = TicketType.objects.create(event=event, name='Probe tier', kind='free', price=0, quantity=1)
    f.registration(event, ticket_type=tier)
    f.registration(event, ticket_type=tier)


def group_booking_inconsistent(f):
    Booking.objects.create(owner=f.user(), event=f.event(), status=Booking.Status.CONFIRMED, amount_paid=PRICE)


def past_event_still_published(f):
    f.event(date=f.now - timedelta(days=3), end_date=f.now - timedelta(days=3) + timedelta(hours=2))


def event_data_invalid(f):
    f.event(end_date=f.now)  # starts in a week, "ends" now


def orphan_money_rows(f):
    payment = f.payment(f.registration(f.event(), status='cancelled', locked_price=PRICE), status='failed')
    f.refund(payment, Decimal('1000.00'))


def outbox_jobs_stuck(f):
    Job.objects.create(kind='send_email', payload={}, run_after=f.now - timedelta(hours=1))


def duplicate_provider_ids(f):
    event = f.event()
    for _ in range(2):
        f.payment(f.registration(event, locked_price=PRICE), stripe_checkout_session_id='cs_defect_duplicate')


def waitlist_inconsistent(f):
    WaitlistEntry.objects.create(
        user=f.user(), event=f.event(), status='offered', offered_at=f.now, offer_expires_at=f.now - timedelta(hours=1)
    )


def review_without_attendance(f):
    event = f.event(date=f.now - timedelta(days=2), end_date=f.now - timedelta(days=2, hours=-3), status='completed')
    Review.objects.create(user=f.user(), event=event, rating=1, comment='Never attended')


def refund_request_inconsistent(f):
    reg = f.registration(f.event(), locked_price=PRICE)
    f.payment(reg)
    RefundRequest.objects.create(registration=reg, status='approved', resolved_at=f.now)


# check name -> function that injects one defect it must catch
DEFECTS = {
    fn.__name__: fn
    for fn in (
        capacity_overrun,
        seat_held_twice,
        seat_marked_free_but_taken,
        seat_blocked_without_holder,
        cross_event_references,
        confirmed_paid_ticket_without_payment,
        money_kept_for_void_ticket,
        payment_amounts_invalid,
        currency_mismatch,
        refund_ledger_over_refund,
        refund_ledger_drift,
        stale_holds,
        checkin_on_invalid_ticket,
        checkin_outside_event_window,
        checkin_log_wrong_event,
        organizer_ticket_for_own_event,
        tickets_held_by_non_attendees,
        duplicate_active_registrations,
        promo_over_max_uses,
        promo_counter_drift,
        ticket_type_oversold,
        group_booking_inconsistent,
        past_event_still_published,
        event_data_invalid,
        orphan_money_rows,
        outbox_jobs_stuck,
        duplicate_provider_ids,
        waitlist_inconsistent,
        review_without_attendance,
        refund_request_inconsistent,
    )
}


def inject_all():
    """Inject every defect (each in a savepoint). Returns {name: None | skip reason}.

    Call inside a transaction that the caller rolls back.
    """
    factory = Factory()
    outcome = {}
    for name, inject in DEFECTS.items():
        try:
            with transaction.atomic():
                inject(factory)
            outcome[name] = None
        except DefectSkipped as exc:
            outcome[name] = str(exc)
    return outcome
