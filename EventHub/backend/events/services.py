from datetime import timedelta
from decimal import Decimal

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from common.choices import EventStatusChoices, RegistrationStatusChoices

from .models import Event, Registration, EventSeat


def broadcast_seat_update(seat: EventSeat):
    """Push seat availability change to all WebSocket clients watching this event."""
    try:
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return
        group_name = f'seat_map_{seat.seat_map.event_id}'
        async_to_sync(channel_layer.group_send)(group_name, {
            'type': 'seat.update',
            'seat_id': seat.id,
            'is_available': seat.is_available,
            'price_zone': seat.price_zone,
        })
    except Exception:
        pass  # Never let broadcast failure break the purchase flow

# How long a seat / spot is held for an unpaid registration before it is
# automatically released back to the pool.
SEAT_HOLD_MINUTES = 10


def release_expired_seat_holds(event: Event = None):
    """Lazily release seats/spots from unpaid registrations whose hold expired.

    Called on read (seat map) and before a new registration so the pool is
    always accurate without needing a background worker.
    """
    # A paid registration must never be released as an "expired hold" — confirm
    # it first so the loop below only touches genuinely unpaid, expired holds.
    reconcile_paid_registrations(event=event)

    now = timezone.now()
    qs = Registration.objects.filter(
        status=RegistrationStatusChoices.PENDING,
        seat_held_until__isnull=False,
        seat_held_until__lt=now,
    ).exclude(payment__status='completed')
    if event is not None:
        qs = qs.filter(event=event)

    freed_events = set()
    for registration in qs.select_related('seat', 'seat__seat_map'):
        freed_seat = registration.seat
        if freed_seat:
            EventSeat.objects.filter(pk=registration.seat_id).update(is_available=True)
            freed_seat.is_available = True  # reflect in-memory for broadcast
        registration.status = RegistrationStatusChoices.CANCELLED
        registration.seat = None
        registration.seat_held_until = None
        registration.save(update_fields=['status', 'seat', 'seat_held_until'])
        if freed_seat:
            broadcast_seat_update(freed_seat)
        freed_events.add(registration.event_id)

    # Offer the freed spots to anyone waiting.
    if freed_events:
        try:
            from .waitlist import promote_waitlist
            for ev in Event.objects.filter(id__in=freed_events):
                promote_waitlist(ev)
        except Exception:
            pass


def reconcile_paid_registrations(*, user=None, event=None):
    """Confirm any pending registration whose payment already completed.

    Guards against a stuck state where the payment succeeded (Stripe webhook or
    mock checkout) but the registration status was never advanced to confirmed.
    Such a registration is broken from the attendee's side: 'Complete payment'
    is refused ("already completed") and 'Release seat' is refused ("paid
    tickets need a refund"), so the seat stays held forever. Idempotent and
    cheap — safe to call on read paths (my-registrations, event detail).
    """
    from common.choices import PaymentStatusChoices

    qs = Registration.objects.filter(
        status=RegistrationStatusChoices.PENDING,
        payment__status=PaymentStatusChoices.COMPLETED,
    )
    if user is not None:
        qs = qs.filter(user=user)
    if event is not None:
        qs = qs.filter(event=event)

    for registration in qs:
        registration.status = RegistrationStatusChoices.CONFIRMED
        registration.seat_held_until = None
        registration.save(update_fields=['status', 'seat_held_until'])


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
    from .models import SeatMap, EventSeat, PromoCode

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
    from .models import TicketType
    TicketType.objects.bulk_create([
        TicketType(
            event=clone, name=t.name, description=t.description, kind=t.kind,
            price=t.price, quantity=t.quantity, min_per_order=t.min_per_order,
            max_per_order=t.max_per_order, sale_start=t.sale_start,
            sale_end=t.sale_end, is_active=t.is_active, order=t.order,
        ) for t in event.ticket_types.all()
    ])

    # Copy custom questions.
    from .models import EventQuestion
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
    from .models import WaitlistEntry
    has_offer = WaitlistEntry.objects.filter(
        event=event, user=user, status=WaitlistEntry.STATUS_OFFERED,
    ).exists()

    # High-demand events run a virtual waiting room: without an admission
    # token you must queue first. Fails open if Redis is unavailable.
    if not has_offer:
        try:
            from .queue import is_queue_active, validate_queue_token
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
            from .waitlist import promote_waitlist
            promote_waitlist(event)  # expires stale offers first
        except Exception:
            pass
        outstanding = WaitlistEntry.objects.filter(
            event=event, status=WaitlistEntry.STATUS_OFFERED,
        ).exclude(user=user).count()
        if free - outstanding <= 0:
            raise ValueError('The remaining spots are reserved for people on the waitlist.')

    # ── Resolve ticket tier (if the event uses them) ──
    from .models import TicketType
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
        from .promo import get_valid_promo, PromoError
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
        from .models import Affiliate
        affiliate = Affiliate.objects.filter(
            event=event, code__iexact=affiliate_code.strip(), is_active=True,
        ).first()

    # Server-side enforcement of required checkout questions (the client
    # validates too, but the API must not accept incomplete registrations).
    from .models import EventQuestion
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
            from .pricing import get_dynamic_price
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
        from .waitlist import mark_converted
        mark_converted(user=user, event=event)
    except Exception:
        pass

    # Done with the waiting room — release the admission token.
    try:
        from .queue import leave_queue
        leave_queue(event.id, user.id)
    except Exception:
        pass

    # Persist answers to custom checkout questions.
    if answers:
        _save_question_answers(registration, answers)

    # Fire the registration_created webhook (free → also a completed sale).
    try:
        from .webhooks import fire
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
    from .models import EventQuestion, QuestionAnswer
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
def request_refund(*, user, event: Event, reason: str = ''):
    """Attendee asks the organizer to refund their paid ticket."""
    from .models import RefundRequest

    registration = get_object_or_404(Registration, user=user, event=event)

    if not event.refundable:
        raise ValueError('Tickets for this event are non-refundable.')

    payment = getattr(registration, 'payment', None)
    if not payment or not payment.is_refundable:
        raise ValueError('No refundable payment found for this ticket.')

    existing = getattr(registration, 'refund_request', None)
    if existing and existing.status == RefundRequest.STATUS_PENDING:
        raise ValueError('You already have a pending refund request.')
    if existing and existing.status == RefundRequest.STATUS_APPROVED:
        raise ValueError('This ticket has already been refunded.')

    if existing:
        # Allow re-requesting after a rejection.
        existing.status = RefundRequest.STATUS_PENDING
        existing.reason = reason
        existing.organizer_note = ''
        existing.resolved_at = None
        existing.save()
        req = existing
    else:
        req = RefundRequest.objects.create(registration=registration, reason=reason)

    # Notify the organizer in-app.
    try:
        from .notify import notify
        notify(
            event.organizer, 'event_updated',
            f'💸 Refund requested: {event.title}',
            f'{user.username} requested a refund of ${payment.net_amount}.'
            + (f' Reason: {reason}' if reason else ''),
            event=event,
        )
    except Exception:
        pass

    return req


@transaction.atomic
def resolve_refund_request(*, refund_request, actor, approve: bool, note: str = ''):
    """Organizer approves or rejects a refund request."""
    from django.utils import timezone as _tz
    from .models import RefundRequest

    registration = refund_request.registration
    event = registration.event

    from common.permissions import can_manage_event
    if not can_manage_event(event, actor):
        raise PermissionError('Only the organizer can resolve refund requests.')

    if refund_request.status != RefundRequest.STATUS_PENDING:
        raise ValueError('This request has already been resolved.')

    if approve:
        payment = getattr(registration, 'payment', None)
        if payment and payment.is_refundable:
            from payments.services import refund_payment
            # Suppress the low-level "Refund issued" notice — we send the
            # user-facing "Refund approved" message below, avoiding duplicates.
            refund_payment(
                payment=payment,
                reason=f'Refund request approved: {note}'.strip(': '),
                notify_user=False,
            )
        refund_request.status = RefundRequest.STATUS_APPROVED
        notify_type, title = 'ticket_purchased', f'✅ Refund approved: {event.title}'
        body = 'Your refund has been approved and processed.'
    else:
        # Rejection means "no refund" — the attendee keeps their paid ticket,
        # so the registration stays confirmed.
        refund_request.status = RefundRequest.STATUS_REJECTED
        notify_type, title = 'payment_failed', f'❌ Refund rejected: {event.title}'
        body = 'Your refund request was declined — your ticket remains valid.'

    refund_request.organizer_note = note
    refund_request.resolved_at = _tz.now()
    refund_request.save(update_fields=['status', 'organizer_note', 'resolved_at'])

    try:
        from .notify import notify
        notify(registration.user, notify_type, title,
               body + (f' Note: {note}' if note else ''), event=event)
    except Exception:
        pass

    return refund_request


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
        from .waitlist import promote_waitlist
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
        from .webhooks import fire
        fire(registration.event, 'attendee_checked_in', {
            'registration_id': registration.id,
            'user': registration.user.username,
            'checked_in_at': registration.checked_in_at.isoformat(),
        })
    except Exception:
        pass

    return registration, False


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

    from .notify import notify
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

