"""Ticket purchase, cancellation and check-in."""

import logging
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.http import Http404
from django.utils import timezone

from common.choices import EventStatusChoices, PaymentStatusChoices, RegistrationStatusChoices

from ..models import INACTIVE_REGISTRATION_STATUSES, Event, EventSeat, Registration
from .holds import SEAT_HOLD_MINUTES, release_expired_seat_holds
from .realtime import broadcast_seat_update

logger = logging.getLogger(__name__)


def ensure_attendee_can_buy(user, event: Event = None):
    """Business rule: only attendee accounts buy tickets — organizers and
    admins manage events, they never purchase (and never for their own event)."""
    profile_role = getattr(getattr(user, 'profile', None), 'role', '')
    if user.is_staff or user.is_superuser or profile_role == 'organizer':
        raise ValueError('Only attendee accounts can buy tickets.')
    if event is not None and event.organizer_id == user.id:
        raise ValueError('Organizers cannot register for their own events')


def ensure_event_on_sale(event: Event):
    if event.status != EventStatusChoices.PUBLISHED:
        raise ValueError('This event is not open for registration.')
    if event.date < timezone.now():
        raise ValueError('This event has already taken place.')


def get_active_registration(*, user, event: Event):
    """The user's live (not cancelled/rejected) registration, or None.

    Cancelled rows are kept as history, so (user, event) alone is not unique.
    """
    return (
        Registration.objects
        .filter(user=user, event=event)
        .exclude(status__in=INACTIVE_REGISTRATION_STATUSES)
        .first()
    )


def _parse_amount(value):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError('Enter a valid amount.')
    if not amount.is_finite():
        raise ValueError('Enter a valid amount.')
    return amount


@transaction.atomic
def register_for_event(*, user, event: Event, notes: str = '', seat_id=None,
                       promo_code: str = '', answers: dict = None,
                       ticket_type_id=None, donation_amount=None, affiliate_code: str = ''):
    # Lock the event row so two concurrent registrations serialise and cannot
    # both pass the capacity check below. The lock lives until this
    # transaction commits, which is why the whole function is atomic.
    event = Event.objects.select_for_update().get(pk=event.pk)

    ensure_attendee_can_buy(user, event)
    ensure_event_on_sale(event)

    # Free up any seats whose hold expired before we check availability.
    release_expired_seat_holds(event)

    if get_active_registration(user=user, event=event) is not None:
        raise ValueError('You are already registered for this event')

    # People holding an active waitlist offer skip the queue and get the
    # spots reserved for them below.
    from ..models import WaitlistEntry
    has_offer = WaitlistEntry.objects.filter(
        event=event, user=user, status=WaitlistEntry.STATUS_OFFERED,
        offer_expires_at__gte=timezone.now(),
    ).exists()

    # High-demand events run a virtual waiting room: without an admission
    # token you must queue first. Fails open if Redis is unavailable.
    if not has_offer:
        from ..queue import is_queue_active, validate_queue_token
        try:
            queue_active = is_queue_active(event)
            token_ok = not queue_active or validate_queue_token(event.id, user.id)
        except Exception:
            logger.exception('Queue check failed for event %s; letting the buyer through', event.id)
            token_ok = True
        if not token_ok:
            raise ValueError('QUEUE_REQUIRED')

    free = event.available_spots
    if free <= 0:
        raise ValueError('No available spots')

    # Spots claimed by outstanding waitlist offers are reserved — only the
    # offered users may take them until the offers expire.
    if not has_offer:
        from ..waitlist import promote_waitlist
        promote_waitlist(event)  # expires stale offers first
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
            chosen = _parse_amount(donation_amount) if donation_amount not in (None, '') else ticket_type.price
            if chosen < ticket_type.price:
                raise ValueError(f'Minimum contribution is {ticket_type.price} {event.currency}.')
            donation_amount = chosen
            is_paid = chosen > 0
        else:
            donation_amount = None
    else:
        is_paid = not event.is_free

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
    answers = answers if isinstance(answers, dict) else {}
    missing = [
        q.label for q in EventQuestion.objects.filter(event=event, is_required=True)
        if str(answers.get(q.id, answers.get(str(q.id), '')) or '').strip() in ('', 'False', 'None')
    ]
    if missing:
        raise ValueError(f'Please answer the required question: {missing[0]}')

    # Lock the quoted base price now (before promo, tax and fees) for every
    # kind of paid ticket, so the amount charged at checkout equals the price
    # the attendee saw even if the organizer edits prices in between.
    locked_price = None
    if is_paid:
        locked_price = _quoted_base_price(event, ticket_type=ticket_type, seat=seat,
                                          donation_amount=donation_amount)

    # Reserve a promo use atomically (paid only). Invalid codes abort; since
    # we're inside the transaction, any later failure gives the use back.
    promo = None
    if promo_code and is_paid:
        from ..promo import get_valid_promo, reserve_promo, PromoError
        try:
            promo = get_valid_promo(event, promo_code)
            reserve_promo(promo)
        except PromoError as exc:
            raise ValueError(str(exc))

    # Free → confirmed instantly; paid → pending until Stripe succeeds.
    if is_paid:
        new_status = RegistrationStatusChoices.PENDING
        held_until = timezone.now() + timedelta(minutes=SEAT_HOLD_MINUTES)
    else:
        new_status = RegistrationStatusChoices.CONFIRMED
        held_until = None

    # Always a fresh row: a previous cancelled registration keeps its own
    # payment/refund history and its (now void) QR code.
    registration = Registration.objects.create(
        user=user,
        event=event,
        status=new_status,
        notes=notes or '',
        seat=seat,
        seat_held_until=held_until,
        promo_code=promo,
        ticket_type=ticket_type,
        donation_amount=donation_amount,
        affiliate=affiliate,
        locked_price=locked_price,
    )

    # Reserve the seat.
    if seat:
        seat.is_available = False
        seat.save(update_fields=['is_available'])
        transaction.on_commit(lambda: broadcast_seat_update(seat))

    # If this user was on the waitlist, mark their entry converted.
    from ..waitlist import mark_converted
    mark_converted(user=user, event=event)

    # Persist answers to custom checkout questions.
    if answers:
        _save_question_answers(registration, answers)

    # Redis isn't transactional: release the queue token only after commit.
    # (Webhooks below are queued jobs, committed with the registration.)
    event_id, user_id = event.id, user.id
    transaction.on_commit(lambda: _leave_queue(event_id, user_id))

    from ..webhooks import fire
    payload = {
        'registration_id': registration.id,
        'user': user.username,
        'status': registration.status,
        'ticket_type': ticket_type.name if ticket_type else None,
    }
    fire(event, 'registration_created', payload)  # queued in this transaction

    return registration


def _quoted_base_price(event, *, ticket_type, seat, donation_amount) -> Decimal:
    from ..billing import _q
    if ticket_type is not None:
        if donation_amount is not None:
            return _q(donation_amount)
        return _q(ticket_type.price)
    if seat is not None:
        from ..seat_pricing import seat_price
        return _q(seat_price(event, seat))
    from ..pricing import get_dynamic_price
    try:
        return _q(get_dynamic_price(event)['current_price'])
    except Exception:
        logger.exception('Dynamic pricing failed for event %s; using the base price', event.id)
        return _q(event.price)


def _leave_queue(event_id, user_id):
    try:
        from ..queue import leave_queue
        leave_queue(event_id, user_id)
    except Exception:
        logger.warning('Could not release queue token for user %s / event %s', user_id, event_id)


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
            defaults={'answer': '' if value is None else str(value)[:5000]},
        )


def attendee_cancel(*, user, event: Event):
    """Attendee releases a PENDING (unpaid) seat hold only.

    Confirmed tickets cannot be cancelled by the attendee at all: paid ones go
    through the refund-request flow, free ones stay as issued.
    Returns ('cancelled', None).
    """
    registration = get_active_registration(user=user, event=event)
    if registration is None:
        raise Http404('Registration not found')

    if registration.status != RegistrationStatusChoices.PENDING:
        raise ValueError(
            'Tickets cannot be cancelled. Paid tickets can be refunded via a refund request.'
        )
    payment = getattr(registration, 'payment', None)
    if payment and payment.status == PaymentStatusChoices.COMPLETED:
        raise ValueError('This ticket is already paid — request a refund instead.')

    cancel_registration(registration=registration)
    return 'cancelled', None


@transaction.atomic
def cancel_registration(*, registration: Registration):
    """Void a registration: free its seat, give back its promo use and offer
    the spot to the waitlist. Idempotent."""
    registration = Registration.objects.select_for_update(of=('self',)).select_related(
        'seat', 'seat__seat_map', 'event',
    ).get(pk=registration.pk)
    if registration.status in INACTIVE_REGISTRATION_STATUSES:
        return registration

    released_seat = registration.seat
    if released_seat:
        EventSeat.objects.filter(pk=released_seat.pk).update(is_available=True)
        released_seat.is_available = True

    registration.status = RegistrationStatusChoices.CANCELLED
    registration.seat = None
    registration.seat_held_until = None
    registration.save(update_fields=['status', 'seat', 'seat_held_until'])

    from ..promo import release_promo
    release_promo(registration)

    if released_seat:
        transaction.on_commit(lambda: broadcast_seat_update(released_seat))

    # A spot just freed — offer it to the next person on the waitlist.
    from ..waitlist import promote_waitlist
    promote_waitlist(registration.event)

    return registration


@transaction.atomic
def check_in_registration(*, registration: Registration, actor):
    from common.permissions import can_check_in_event
    if not can_check_in_event(registration.event, actor):
        raise PermissionError('You do not have check-in rights for this event.')

    # Row lock: two gates scanning the same QR at once serialise here, and
    # the second one sees is_checked_in=True instead of also letting it in.
    registration = (
        Registration.objects.select_for_update(of=('self',))
        .select_related('event', 'user', 'payment')
        .get(pk=registration.pk)
    )

    # Heal a pending-but-paid registration before judging the status.
    payment = getattr(registration, 'payment', None)
    if (registration.status == RegistrationStatusChoices.PENDING
            and payment is not None and payment.status == PaymentStatusChoices.COMPLETED):
        registration.status = RegistrationStatusChoices.CONFIRMED
        registration.seat_held_until = None
        registration.save(update_fields=['status', 'seat_held_until'])

    if registration.event.status == EventStatusChoices.CANCELLED:
        raise ValueError('This event was cancelled — entry must be refused.')
    if registration.status == RegistrationStatusChoices.PENDING:
        raise ValueError('Ticket is NOT paid — registration is still pending payment.')
    if registration.status in INACTIVE_REGISTRATION_STATUSES:
        raise ValueError('Ticket is cancelled — entry must be refused.')

    if registration.is_checked_in:
        return registration, True

    registration.is_checked_in = True
    registration.checked_in_at = timezone.now()
    registration.save(update_fields=['is_checked_in', 'checked_in_at'])

    from ..webhooks import fire
    payload = {
        'registration_id': registration.id,
        'user': registration.user.username,
        'checked_in_at': registration.checked_in_at.isoformat(),
    }
    event = registration.event
    fire(event, 'attendee_checked_in', payload)  # queued in this transaction

    return registration, False
