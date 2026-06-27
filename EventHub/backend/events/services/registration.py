"""Ticket purchase, cancellation and check-in."""

from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from common.choices import EventStatusChoices, RegistrationStatusChoices

from ..models import Event, EventSeat, Registration
from .holds import SEAT_HOLD_MINUTES, release_expired_seat_holds, reconcile_paid_registrations
from .realtime import broadcast_seat_update


@transaction.atomic
def ensure_attendee_can_buy(user):
    """Business rule: only attendee accounts buy tickets — organizers and
    admins manage events, they never purchase."""
    profile_role = getattr(getattr(user, 'profile', None), 'role', '')
    if user.is_staff or user.is_superuser or profile_role == 'organizer':
        raise ValueError('Only attendee accounts can buy tickets.')


def register_for_event(*, user, event: Event, notes: str = '', seat_id=None,
                       promo_code: str = '', answers: dict = None,
                       ticket_type_id=None, donation_amount=None, affiliate_code: str = ''):
    # Lock the event row so two concurrent registrations serialise and cannot
    # both pass the capacity check below.
    event = Event.objects.select_for_update().get(pk=event.pk)

    ensure_attendee_can_buy(user)

    if event.organizer == user:
        raise ValueError('Organizers cannot register for their own events')

    if event.status != EventStatusChoices.PUBLISHED:
        raise ValueError('This event is not open for registration.')

    if event.date < timezone.now():
        raise ValueError('This event has already taken place.')

    # Free up any seats whose hold expired before we check availability.
    release_expired_seat_holds(event)

    if Registration.objects.filter(
        user=user,
        event=event,
    ).exclude(status__in=[
        RegistrationStatusChoices.CANCELLED,
        RegistrationStatusChoices.REJECTED,
    ]).exists():
        raise ValueError('You are already registered for this event')

    # People holding an active waitlist offer skip the queue and get the
    # spots reserved for them below.
    from ..models import WaitlistEntry
    has_offer = WaitlistEntry.objects.filter(
        event=event, user=user, status=WaitlistEntry.STATUS_OFFERED,
    ).exists()

    # High-demand events run a virtual waiting room: without an admission
    # token you must queue first. Fails open if Redis is unavailable.
    if not has_offer:
        try:
            from ..queue import is_queue_active, validate_queue_token
            queue_active = is_queue_active(event)
            if queue_active and not validate_queue_token(event.id, user.id):
                raise ValueError('QUEUE_REQUIRED')
        except ValueError:
            raise
        except Exception:
            pass

    free = event.available_spots
    if free <= 0:
        raise ValueError('No available spots')

    # Spots claimed by outstanding waitlist offers are reserved — only the
    # offered users may take them until the offers expire.
    if not has_offer:
        try:
            from ..waitlist import promote_waitlist
            promote_waitlist(event)  # expires stale offers first
        except Exception:
            pass
        outstanding = WaitlistEntry.objects.filter(
            event=event, status=WaitlistEntry.STATUS_OFFERED,
        ).exclude(user=user).count()
        if free - outstanding <= 0:
            raise ValueError('The remaining spots are reserved for people on the waitlist.')

    # ── Resolve ticket tier (if the event uses them) ──
    from ..models import TicketType
    ticket_type = None
    if event.has_ticket_types:
        if not ticket_type_id:
            raise ValueError('Please choose a ticket type.')
        ticket_type = (
            TicketType.objects.select_for_update()
            .filter(id=ticket_type_id, event=event)
            .first()
        )
        if ticket_type is None:
            raise ValueError('Ticket type not found for this event.')
        if not ticket_type.on_sale:
            state = ticket_type.sale_state
            msg = {
                'inactive': 'This ticket type is not available.',
                'scheduled': 'Sales for this ticket type have not started yet.',
                'ended': 'Sales for this ticket type have ended.',
                'sold_out': 'This ticket type is sold out.',
            }.get(state, 'This ticket type is not on sale.')
            raise ValueError(msg)
        # Per-tier capacity (row-locked above to avoid oversell).
        if ticket_type.quantity is not None and ticket_type.sold >= ticket_type.quantity:
            raise ValueError('This ticket type is sold out.')

    # Determine whether money is owed (drives pending vs confirmed).
    if ticket_type is not None:
        is_paid = ticket_type.kind != TicketType.KIND_FREE
        # Validate donation amount against the suggested minimum.
        if ticket_type.kind == TicketType.KIND_DONATION:
            chosen = Decimal(str(donation_amount)) if donation_amount is not None else ticket_type.price
            if chosen < ticket_type.price:
                raise ValueError(f'Minimum contribution is ${ticket_type.price}.')
            donation_amount = chosen
            is_paid = chosen > 0
        else:
            donation_amount = None
    else:
        is_paid = not event.is_free

    # Resolve promo code (paid only). Invalid codes raise and abort.
    promo = None
    if promo_code and is_paid:
        from ..promo import get_valid_promo, PromoError
        try:
            promo = get_valid_promo(event, promo_code)
        except PromoError as exc:
            raise ValueError(str(exc))

    # Seat selection (seat-map events only; not used with ticket tiers).
    seat = None
    if seat_id and ticket_type is None:
        seat = (
            EventSeat.objects.select_for_update()
            .filter(id=seat_id, seat_map__event=event)
            .first()
        )
        if seat is None:
            raise ValueError('Seat not found for this event')
        if not seat.is_available:
            raise ValueError('Selected seat is not available')

    # Resolve affiliate referral code (best-effort, never blocks registration).
    affiliate = None
    if affiliate_code:
        from ..models import Affiliate
        affiliate = Affiliate.objects.filter(
            event=event, code__iexact=affiliate_code.strip(), is_active=True,
        ).first()

    # Server-side enforcement of required checkout questions (the client
    # validates too, but the API must not accept incomplete registrations).
    from ..models import EventQuestion
    answers = answers or {}
    missing = [
        q.label for q in EventQuestion.objects.filter(event=event, is_required=True)
        if str(answers.get(q.id, answers.get(str(q.id), '')) or '').strip() in ('', 'False', 'None')
    ]
    if missing:
        raise ValueError(f'Please answer the required question: {missing[0]}')

    # GA flat-price events: lock the dynamic price now so the amount charged
    # at checkout equals the price the attendee was quoted.
    locked_price = None
    if ticket_type is None and seat is None and is_paid:
        try:
            from ..pricing import get_dynamic_price
            locked_price = Decimal(str(get_dynamic_price(event)['current_price']))
        except Exception:
            locked_price = Decimal(str(event.price))

    # Free → confirmed instantly; paid → pending until Stripe succeeds.
    if is_paid:
        new_status = RegistrationStatusChoices.PENDING
        held_until = timezone.now() + timedelta(minutes=SEAT_HOLD_MINUTES)
    else:
        new_status = RegistrationStatusChoices.CONFIRMED
        held_until = None

    registration, created = Registration.objects.get_or_create(
        user=user,
        event=event,
        defaults={
            'status': new_status,
            'notes': notes,
            'seat': seat,
            'seat_held_until': held_until,
            'promo_code': promo,
            'ticket_type': ticket_type,
            'donation_amount': donation_amount,
            'affiliate': affiliate,
            'locked_price': locked_price,
        },
    )

    if not created:
        registration.status = new_status
        registration.notes = notes
        registration.seat = seat
        registration.seat_held_until = held_until
        registration.promo_code = promo
        registration.ticket_type = ticket_type
        registration.donation_amount = donation_amount
        registration.locked_price = locked_price
        if affiliate:
            registration.affiliate = affiliate
        registration.save(update_fields=[
            'status', 'notes', 'seat', 'seat_held_until', 'promo_code',
            'ticket_type', 'donation_amount', 'affiliate', 'locked_price',
        ])

    # Reserve the seat.
    if seat:
        seat.is_available = False
        seat.save(update_fields=['is_available'])
        broadcast_seat_update(seat)

    # If this user was on the waitlist, mark their entry converted.
    try:
        from ..waitlist import mark_converted
        mark_converted(user=user, event=event)
    except Exception:
        pass

    # Done with the waiting room — release the admission token.
    try:
        from ..queue import leave_queue
        leave_queue(event.id, user.id)
    except Exception:
        pass

    # Persist answers to custom checkout questions.
    if answers:
        _save_question_answers(registration, answers)

    # Fire the registration_created webhook (free → also a completed sale).
    try:
        from ..webhooks import fire
        fire(event, 'registration_created', {
            'registration_id': registration.id,
            'user': user.username,
            'status': registration.status,
            'ticket_type': ticket_type.name if ticket_type else None,
        })
    except Exception:
        pass

    return registration


def _save_question_answers(registration, answers: dict):
    """Upsert answers ({question_id: value}) for a registration."""
    from ..models import EventQuestion, QuestionAnswer
    valid_ids = set(
        EventQuestion.objects.filter(event=registration.event).values_list('id', flat=True)
    )
    for qid, value in (answers or {}).items():
        try:
            qid_int = int(qid)
        except (TypeError, ValueError):
            continue
        if qid_int not in valid_ids:
            continue
        QuestionAnswer.objects.update_or_create(
            registration=registration, question_id=qid_int,
            defaults={'answer': '' if value is None else str(value)},
        )


def attendee_cancel(*, user, event: Event):
    """Attendee releases a PENDING (unpaid) seat hold only.

    Confirmed tickets cannot be cancelled by the attendee at all: paid ones go
    through the refund-request flow, free ones stay as issued.
    Returns ('cancelled', None).
    """
    registration = get_object_or_404(Registration, user=user, event=event)

    if registration.status != RegistrationStatusChoices.PENDING:
        raise ValueError(
            'Tickets cannot be cancelled. Paid tickets can be refunded via a refund request.'
        )

    cancel_registration(user=user, event=event)
    return 'cancelled', None


@transaction.atomic
def cancel_registration(*, user, event: Event):
    registration = get_object_or_404(Registration, user=user, event=event)
    registration.status = RegistrationStatusChoices.CANCELLED

    # Release seat if assigned
    released_seat = registration.seat
    if released_seat:
        released_seat.is_available = True
        released_seat.save(update_fields=['is_available'])

    registration.seat = None
    registration.seat_held_until = None
    registration.save(update_fields=['status', 'seat', 'seat_held_until'])

    if released_seat:
        broadcast_seat_update(released_seat)

    # A spot just freed — offer it to the next person on the waitlist.
    try:
        from ..waitlist import promote_waitlist
        promote_waitlist(event)
    except Exception:
        pass

    return registration


@transaction.atomic
def check_in_registration(*, registration: Registration, actor):
    from common.permissions import can_check_in_event
    if not can_check_in_event(registration.event, actor):
        raise PermissionError('You do not have check-in rights for this event.')

    # Heal pending-but-paid registrations before judging the status.
    reconcile_paid_registrations(event=registration.event)
    registration.refresh_from_db()

    if registration.status == RegistrationStatusChoices.PENDING:
        raise ValueError('Ticket is NOT paid — registration is still pending payment.')
    if registration.status in (RegistrationStatusChoices.CANCELLED, RegistrationStatusChoices.REJECTED):
        raise ValueError('Ticket is cancelled — entry must be refused.')

    if registration.is_checked_in:
        return registration, True

    registration.is_checked_in = True
    registration.checked_in_at = timezone.now()
    registration.save(update_fields=['is_checked_in', 'checked_in_at'])

    try:
        from ..webhooks import fire
        fire(registration.event, 'attendee_checked_in', {
            'registration_id': registration.id,
            'user': registration.user.username,
            'checked_in_at': registration.checked_in_at.isoformat(),
        })
    except Exception:
        pass

    return registration, False
