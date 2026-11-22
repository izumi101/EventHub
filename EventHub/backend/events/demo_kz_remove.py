"""`manage.py seed_demo_kz --remove [--dry-run]`: delete what the seed created, and nothing else.

What the seed created is found by what only it can have made:

- users: a `kz_` user name and an address on `demo.eventhub.local`;
- events: a title from `demo_kz_data.EVENTS`, owned by a demo user, or by the
  `--organizer` the seed was given (the seed hands that user a third of them);
- everything else hangs off those events (tickets, payments, refunds, gates,
  staff, reviews ...) or off those users.

Kept on purpose, and reported: an event that real accounts bought tickets for
(money records must never disappear), and a demo user who owns or holds
something outside the events being removed. Categories are shared and stay.

The deletes run in an order the PROTECT foreign keys allow (refunds before
payments before tickets before events) inside one transaction.
"""

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q

from bookings.models import Booking, BookingSeat
from common.demo_seed import DEMO_EMAIL_DOMAIN
from events.demo_kz_data import TITLES, USERNAME_PREFIX
from events.models import (
    Affiliate,
    CheckInList,
    CheckInLog,
    Event,
    EventStaff,
    Notification,
    PromoCode,
    RefundRequest,
    Registration,
    Review,
    SeatMap,
    TicketType,
    WaitlistEntry,
)
from payments.models import Payment, PaymentEvent, Refund


def demo_users():
    return User.objects.filter(username__startswith=USERNAME_PREFIX, email__iendswith=f'@{DEMO_EMAIL_DOMAIN}')


def candidate_events(owner):
    """Events with a demo title owned by a demo user or by `owner`."""
    owners = Q(organizer__in=demo_users())
    if owner is not None:
        owners |= Q(organizer=owner)
    return Event.objects.filter(owners, title__in=TITLES)


def build_plan(owner):
    """[(label, queryset)] in deletion order, plus notes about what is kept."""
    # Ids are fetched first: subqueries over the big ticket tables plan badly on freshly loaded data.
    demo = demo_users()
    demo_ids = list(demo.values_list('pk', flat=True))
    candidates = candidate_events(owner)
    candidate_ids = list(candidates.values_list('pk', flat=True))
    sold_to_others = set(
        Registration.objects.filter(event_id__in=candidate_ids)
        .exclude(user_id__in=demo_ids)
        .values_list('event_id', flat=True)
    ) | set(
        Booking.objects.filter(event_id__in=candidate_ids)
        .exclude(owner_id__in=demo_ids)
        .values_list('event_id', flat=True)
    )
    event_ids = list(candidates.exclude(pk__in=sold_to_others).values_list('pk', flat=True))

    payment_ids = list(
        Payment.objects.filter(
            Q(registration__event_id__in=event_ids) | Q(booking__event_id__in=event_ids)
        ).values_list('pk', flat=True)
    )
    payments = Payment.objects.filter(pk__in=payment_ids)
    # A demo user is removed unless it owns or holds something outside the removed events.
    keep = set(
        Event.objects.filter(organizer_id__in=demo_ids).exclude(pk__in=event_ids).values_list('organizer_id', flat=True)
    )
    keep |= set(
        Registration.objects.filter(user_id__in=demo_ids)
        .exclude(event_id__in=event_ids)
        .values_list('user_id', flat=True)
    )
    keep |= set(
        Booking.objects.filter(owner_id__in=demo_ids).exclude(event_id__in=event_ids).values_list('owner_id', flat=True)
    )
    users = User.objects.filter(pk__in=[pk for pk in demo_ids if pk not in keep])
    steps = [
        ('payment events', PaymentEvent.objects.filter(payment__in=payments)),
        ('refunds', Refund.objects.filter(payment__in=payments)),
        ('payments', payments),
        ('booking seats', BookingSeat.objects.filter(booking__event_id__in=event_ids)),
        ('bookings', Booking.objects.filter(event_id__in=event_ids)),
        ('check-in logs', CheckInLog.objects.filter(checkin_list__event_id__in=event_ids)),
        ('check-in lists', CheckInList.objects.filter(event_id__in=event_ids)),
        ('refund requests', RefundRequest.objects.filter(registration__event_id__in=event_ids)),
        ('registrations', Registration.objects.filter(event_id__in=event_ids)),
        ('waitlist entries', WaitlistEntry.objects.filter(event_id__in=event_ids)),
        ('reviews', Review.objects.filter(event_id__in=event_ids)),
        ('promo codes', PromoCode.objects.filter(event_id__in=event_ids)),
        ('affiliates', Affiliate.objects.filter(event_id__in=event_ids)),
        ('event staff', EventStaff.objects.filter(event_id__in=event_ids)),
        ('ticket types', TicketType.objects.filter(event_id__in=event_ids)),
        ('seat maps', SeatMap.objects.filter(event_id__in=event_ids)),
        ('events', Event.objects.filter(pk__in=event_ids)),
        ('users', users),
    ]
    notes = {
        'kept_events': len(sold_to_others),
        'other_owner': Event.objects.filter(title__in=TITLES).exclude(pk__in=candidates).count(),
        'kept_users': demo.count() - users.count(),
        'notifications': Notification.objects.filter(user__in=users).count(),
    }
    return steps, notes


def remove(command, owner, *, dry_run):
    """Print the per-model counts; delete unless `dry_run`."""
    steps, notes = build_plan(owner)
    counts = [(label, queryset.count()) for label, queryset in steps]
    if not dry_run:
        with transaction.atomic():
            for _, queryset in steps:
                queryset.delete()
    verb = 'Would delete' if dry_run else 'Deleted'
    command.stdout.write(f'{verb}:')
    for label, count in counts:
        command.stdout.write(f'  {label}: {count}')
    command.stdout.write(f'  (notifications of those users, removed with them: {notes["notifications"]})')
    if notes['kept_events']:
        command.stdout.write(f'Kept {notes["kept_events"]} demo events that real accounts bought tickets for.')
    if notes['kept_users']:
        command.stdout.write(
            f'Kept {notes["kept_users"]} demo users that own or hold something outside the demo events.'
        )
    if notes['other_owner'] and owner is None:
        command.stdout.write(
            f'{notes["other_owner"]} events with demo titles belong to other accounts and were left alone '
            '(pass --organizer USERNAME if the seed was run with it).'
        )
    if dry_run:
        command.stdout.write('Dry run: nothing was deleted.')
