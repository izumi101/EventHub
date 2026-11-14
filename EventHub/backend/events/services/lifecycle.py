"""Event lifecycle: create/update/clone and status transitions."""

import logging

from django.db import transaction
from django.utils.translation import gettext_lazy as _

from common.choices import EventStatusChoices

from ..models import INACTIVE_REGISTRATION_STATUSES, Event

logger = logging.getLogger(__name__)


def create_event(*, organizer, validated_data):
    return Event.objects.create(organizer=organizer, **validated_data)


# Changes ticket holders are told about: (field, label shown to them).
NOTIFIED_CHANGES = (
    ('date', _('Date')),
    ('end_date', _('End')),
    ('location', _('Venue')),
    ('address', _('Address')),
    ('is_online', _('Online')),
    ('online_link', _('Online link')),
)


def _display(field, value):
    from notifications.messages import format_datetime

    if field in ('date', 'end_date'):
        return format_datetime(value)
    if field == 'is_online':
        return str(_('Yes') if value else _('No'))
    return value or ''


@transaction.atomic
def update_event(*, event: Event, validated_data):
    before = {field: getattr(event, field) for field, _label in NOTIFIED_CHANGES}
    for attr, value in validated_data.items():
        setattr(event, attr, value)
    event.save()

    changes = [
        (str(label), _display(field, before[field]), _display(field, getattr(event, field)))
        for field, label in NOTIFIED_CHANGES
        if getattr(event, field) != before[field]
    ]
    if changes and event.status == EventStatusChoices.PUBLISHED:
        from notifications import types
        from notifications.service import notify_many, ticket_holders

        notify_many(ticket_holders(event), types.EVENT_UPDATED, event=event, changes=changes)
    return event


@transaction.atomic
def clone_event(*, event: Event, actor):
    """Duplicate an event as a fresh draft owned by `actor`.

    Copies core fields, the seat map (all seats reset to available) and any
    promo codes (usage counters reset). Registrations/payments are NOT copied.
    """
    from ..models import EventSeat, PromoCode, SeatMap

    clone = Event.objects.create(
        title=f'{event.title} (Copy)',
        description=event.description,
        organizer=actor,
        category=event.category,
        date=event.date,
        end_date=event.end_date,
        location=event.location,
        address=event.address,
        price=event.price,
        max_participants=event.max_participants,
        status=EventStatusChoices.DRAFT,
        is_online=event.is_online,
        online_link=event.online_link,
        tax_percent=event.tax_percent,
        service_fee_percent=event.service_fee_percent,
        fees_passed_to_buyer=event.fees_passed_to_buyer,
        currency=event.currency,
        refundable=event.refundable,
        seo_title=event.seo_title,
        seo_description=event.seo_description,
        image=event.image.name if event.image else None,
    )

    # Copy seat map + seats (all freshly available).
    src_map = SeatMap.objects.filter(event=event).first()
    if src_map:
        new_map = SeatMap.objects.create(
            event=clone,
            rows=src_map.rows,
            cols=src_map.cols,
            layout=src_map.layout,
        )
        EventSeat.objects.bulk_create(
            [
                EventSeat(seat_map=new_map, row=s.row, col=s.col, price_zone=s.price_zone, is_available=True)
                for s in src_map.seats.all()
            ]
        )

    # Copy promo codes with counters reset.
    PromoCode.objects.bulk_create(
        [
            PromoCode(
                event=clone,
                code=p.code,
                discount_type=p.discount_type,
                discount_value=p.discount_value,
                max_uses=p.max_uses,
                expires_at=p.expires_at,
                is_active=p.is_active,
            )
            for p in event.promo_codes.all()
        ]
    )

    # Copy ticket types (sold counts reset naturally — no registrations copied).
    from ..models import TicketType

    TicketType.objects.bulk_create(
        [
            TicketType(
                event=clone,
                name=t.name,
                description=t.description,
                kind=t.kind,
                price=t.price,
                quantity=t.quantity,
                min_per_order=t.min_per_order,
                max_per_order=t.max_per_order,
                sale_start=t.sale_start,
                sale_end=t.sale_end,
                is_active=t.is_active,
                order=t.order,
            )
            for t in event.ticket_types.all()
        ]
    )

    # Copy custom questions.
    from ..models import EventQuestion

    EventQuestion.objects.bulk_create(
        [
            EventQuestion(
                event=clone,
                label=q.label,
                question_type=q.question_type,
                options=q.options,
                is_required=q.is_required,
                order=q.order,
            )
            for q in event.questions.all()
        ]
    )

    return clone


@transaction.atomic
def approve_event(event: Event):
    # Only something waiting for review can be published — approving a
    # cancelled or completed event would put it back on sale.
    if event.status not in (EventStatusChoices.PENDING, EventStatusChoices.REJECTED):
        raise ValueError(f'Only events pending review can be approved (this one is {event.status}).')
    event.status = EventStatusChoices.PUBLISHED
    event.save(update_fields=['status'])
    return event


@transaction.atomic
def reject_event(event: Event):
    if event.status != EventStatusChoices.PENDING:
        raise ValueError(f'Only events pending review can be rejected (this one is {event.status}).')
    event.status = EventStatusChoices.REJECTED
    event.save(update_fields=['status'])
    return event


@transaction.atomic
def submit_event(*, event: Event, actor):
    """Organizer sends a draft (e.g. a clone) to admin review."""
    from common.permissions import can_manage_event

    if not can_manage_event(event, actor):
        raise PermissionError('You do not manage this event.')
    if event.status not in (EventStatusChoices.DRAFT, EventStatusChoices.REJECTED):
        raise ValueError('Only draft or rejected events can be submitted for review.')
    event.status = EventStatusChoices.PENDING
    event.save(update_fields=['status'])
    return event


def cancel_event(*, event: Event, actor):
    """Organizer cancels an event: refund paid tickets, void the rest,
    notify every attendee.

    Each ticket is refunded in its own savepoint, so one failing refund
    (Stripe error, DB error) neither aborts the others nor rolls back money
    that was already returned — and the attendee is told the truth.
    """
    from common.permissions import can_manage_event
    from notifications import types
    from notifications.service import notify
    from payments.services import refund_payment

    from .registration import cancel_registration

    if not can_manage_event(event, actor):
        raise PermissionError('Only the organizer can cancel this event.')

    with transaction.atomic():
        event = Event.objects.select_for_update().get(pk=event.pk)
        if event.status in (EventStatusChoices.CANCELLED, EventStatusChoices.COMPLETED):
            raise ValueError('This event is already finished or cancelled.')
        event.status = EventStatusChoices.CANCELLED
        event.save(update_fields=['status'])

    regs = list(
        event.registrations.exclude(status__in=INACTIVE_REGISTRATION_STATUSES).select_related('payment', 'user')
    )

    refunded, failed = 0, 0
    outcome = {}
    for reg in regs:
        payment = getattr(reg, 'payment', None)
        try:
            with transaction.atomic():
                if payment and payment.is_refundable:
                    refund_payment(payment=payment, reason='Event cancelled by the organizer', notify_user=False)
                    refunded += 1
                    outcome[reg.id] = 'refunded'
                # Free / unpaid / already-refunded tickets are voided too, so
                # nothing for this event passes the door scanner any more.
                cancel_registration(registration=reg)
                outcome.setdefault(reg.id, 'voided')
        except Exception:
            failed += 1
            outcome[reg.id] = 'failed'
            logger.exception('Refund failed for registration %s while cancelling event %s', reg.id, event.id)

    booking_outcome = _cancel_group_bookings(event, actor)
    bookings_refunded = sum(1 for state, _users in booking_outcome if state == 'refunded')
    bookings_failed = sum(1 for state, _users in booking_outcome if state == 'failed')

    # One notice per ticket holder, with the worst refund outcome of their
    # tickets: a failed refund must not be hidden behind a successful one.
    rank = {'failed': 2, 'refunded': 1, 'voided': 0}
    recipients = {}
    for reg in regs:
        recipients.setdefault(reg.user_id, [reg.user, 'voided'])
        state = outcome.get(reg.id, 'voided')
        if rank[state] > rank[recipients[reg.user_id][1]]:
            recipients[reg.user_id][1] = state
    for state, users in booking_outcome:
        for index, user in enumerate(users):
            # The owner paid; friends who claimed a seat were not charged.
            user_state = state if index == 0 else 'voided'
            recipients.setdefault(user.pk, [user, 'voided'])
            if rank[user_state] > rank[recipients[user.pk][1]]:
                recipients[user.pk][1] = user_state
    for user, state in recipients.values():
        notify(user, types.EVENT_CANCELLED, event=event, refund=state)

    return {
        'notified': len(recipients),
        'refunded': refunded + bookings_refunded,
        'refund_failed': failed + bookings_failed,
    }


def _cancel_group_bookings(event, actor):
    """Refund paid group bookings and release held ones. Returns one
    (state, [owner, *friends who claimed a seat]) per booking, state being
    'refunded', 'voided' or 'failed'."""
    from bookings.models import Booking
    from bookings.services import cancel_booking, refund_booking

    outcome = []
    for booking in Booking.objects.filter(
        event=event,
        status__in=[Booking.Status.HOLDING, Booking.Status.CONFIRMED],
    ).select_related('owner'):
        holders = [booking.owner]
        holders += [bs.claimed_by for bs in booking.seats.select_related('claimed_by') if bs.claimed_by_id]
        try:
            with transaction.atomic():
                if booking.status == Booking.Status.CONFIRMED:
                    # Fires the refund webhook; the cancellation notice
                    # below tells the owner about the refund.
                    refund_booking(
                        booking, actor=actor, reason='Event cancelled by the organizer', event_cancelled=True
                    )
                    outcome.append(('refunded', holders))
                else:
                    cancel_booking(booking)
                    outcome.append(('voided', holders))
        except Exception:
            outcome.append(('failed', holders))
            logger.exception('Could not cancel group booking %s for event %s', booking.pk, event.id)
    return outcome
