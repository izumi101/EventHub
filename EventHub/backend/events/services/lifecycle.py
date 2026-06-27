"""Event lifecycle: create/update/clone and status transitions."""

from django.db import transaction
from django.utils import timezone

from common.choices import EventStatusChoices, RegistrationStatusChoices

from ..models import Event


def create_event(*, organizer, validated_data):
    return Event.objects.create(organizer=organizer, **validated_data)


def update_event(*, event: Event, validated_data):
    for attr, value in validated_data.items():
        setattr(event, attr, value)
    event.save()
    return event


@transaction.atomic
def clone_event(*, event: Event, actor):
    """Duplicate an event as a fresh draft owned by `actor`.

    Copies core fields, the seat map (all seats reset to available) and any
    promo codes (usage counters reset). Registrations/payments are NOT copied.
    """
    from ..models import SeatMap, EventSeat, PromoCode

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
    )

    # Copy seat map + seats (all freshly available).
    src_map = SeatMap.objects.filter(event=event).first()
    if src_map:
        new_map = SeatMap.objects.create(
            event=clone, rows=src_map.rows, cols=src_map.cols, layout=src_map.layout,
        )
        EventSeat.objects.bulk_create([
            EventSeat(seat_map=new_map, row=s.row, col=s.col, price_zone=s.price_zone, is_available=True)
            for s in src_map.seats.all()
        ])

    # Copy promo codes with counters reset.
    PromoCode.objects.bulk_create([
        PromoCode(
            event=clone, code=p.code, discount_type=p.discount_type,
            discount_value=p.discount_value, max_uses=p.max_uses,
            expires_at=p.expires_at, is_active=p.is_active,
        ) for p in event.promo_codes.all()
    ])

    # Copy ticket types (sold counts reset naturally — no registrations copied).
    from ..models import TicketType
    TicketType.objects.bulk_create([
        TicketType(
            event=clone, name=t.name, description=t.description, kind=t.kind,
            price=t.price, quantity=t.quantity, min_per_order=t.min_per_order,
            max_per_order=t.max_per_order, sale_start=t.sale_start,
            sale_end=t.sale_end, is_active=t.is_active, order=t.order,
        ) for t in event.ticket_types.all()
    ])

    # Copy custom questions.
    from ..models import EventQuestion
    EventQuestion.objects.bulk_create([
        EventQuestion(
            event=clone, label=q.label, question_type=q.question_type,
            options=q.options, is_required=q.is_required, order=q.order,
        ) for q in event.questions.all()
    ])

    return clone


@transaction.atomic
def approve_event(event: Event):
    event.status = EventStatusChoices.PUBLISHED
    event.save(update_fields=['status'])
    return event


@transaction.atomic
def reject_event(event: Event):
    event.status = EventStatusChoices.REJECTED
    event.save(update_fields=['status'])
    return event


def mark_completed_if_past(event: Event):
    """Lazily flip a published event to COMPLETED once it has ended."""
    if event.status != EventStatusChoices.PUBLISHED:
        return event
    end = event.end_date or event.date
    if end and end < timezone.now():
        event.status = EventStatusChoices.COMPLETED
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


@transaction.atomic
def cancel_event(*, event: Event, actor):
    """Organizer cancels an event: refund paid tickets, notify every attendee."""
    from common.permissions import can_manage_event
    if not can_manage_event(event, actor):
        raise PermissionError('Only the organizer can cancel this event.')
    if event.status in (EventStatusChoices.CANCELLED, EventStatusChoices.COMPLETED):
        raise ValueError('This event is already finished or cancelled.')

    # Snapshot attendees BEFORE refunds (full refunds cancel registrations).
    regs = list(
        event.registrations.exclude(status__in=[
            RegistrationStatusChoices.CANCELLED, RegistrationStatusChoices.REJECTED,
        ]).select_related('payment', 'user')
    )

    event.status = EventStatusChoices.CANCELLED
    event.save(update_fields=['status'])

    refunded = 0
    for reg in regs:
        payment = getattr(reg, 'payment', None)
        if payment and payment.is_refundable:
            try:
                from payments.services import refund_payment
                refund_payment(payment=payment, reason='Event cancelled by the organizer', notify_user=False)
                refunded += 1
            except Exception:
                pass

    from ..notify import notify
    for reg in regs:
        try:
            notify(
                reg.user, 'event_cancelled',
                f'❌ Event cancelled: {event.title}',
                'The organizer has cancelled this event.'
                + (' Your payment has been refunded.' if getattr(reg, 'payment', None) else ''),
                event=event,
            )
        except Exception:
            pass

    return {'notified': len(regs), 'refunded': refunded}
