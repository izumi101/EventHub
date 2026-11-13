"""What each notification type says.

A builder turns (user, event, data) into a `Message`: the in-app title/body
and the structured content of the email (headline, paragraphs, details,
tickets with QR codes, a call-to-action). Every user-facing string goes
through gettext, so the copy can be translated without touching the layout
templates.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import dateformat, timezone
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from . import types


@dataclass
class Ticket:
    """One e-ticket shown in an email, with its QR code."""

    ticket_uuid: str
    label: str
    details: list[tuple[str, str]] = field(default_factory=list)

    @property
    def short_id(self) -> str:
        # The same short id the frontend prints under the QR code.
        return str(self.ticket_uuid)[:8].upper()


@dataclass
class Message:
    title: str
    body: str
    subject: str
    headline: str
    paragraphs: list[str] = field(default_factory=list)
    details: list[tuple[str, str]] = field(default_factory=list)
    tickets: list[Ticket] = field(default_factory=list)
    cta_label: str = ''
    cta_url: str = ''


# ───────────────────────── formatting helpers ─────────────────────────


def frontend_url(path: str = '') -> str:
    return f'{settings.FRONTEND_URL}{path}'


def ticket_validation_url(ticket_uuid) -> str:
    """What a ticket QR code encodes — the same URL the frontend's QR codes
    use (`<origin>/validate/<uuid>`), so the door scanner reads both."""
    return frontend_url(f'/validate/{ticket_uuid}')


def format_datetime(value) -> str:
    if value is None:
        return ''
    tz_name = getattr(settings, 'NOTIFICATION_TIME_ZONE', '') or settings.TIME_ZONE
    local = timezone.localtime(value, ZoneInfo(tz_name))
    return f'{dateformat.format(local, "D, j M Y, H:i")} ({tz_name})'


def venue_of(event) -> str:
    if event.is_online:
        return _('Online')
    parts = [event.location, event.address]
    return ', '.join(p.strip() for p in parts if p and p.strip())


def seat_label(seat) -> str:
    if seat is None:
        return ''
    return _('Row %(row)s · Seat %(col)s (%(zone)s)') % {
        'row': seat.row,
        'col': seat.col,
        'zone': seat.get_price_zone_display(),
    }


def event_details(event) -> list[tuple[str, str]]:
    details = [(_('Event'), event.title), (_('Date'), format_datetime(event.date))]
    if event.end_date:
        details.append((_('Ends'), format_datetime(event.end_date)))
    details.append((_('Venue'), venue_of(event)))
    return details


def money(amount, currency) -> str:
    return f'{amount} {(currency or "").upper()}'.strip()


def registration_ticket(registration) -> Ticket:
    details = []
    if registration.seat_id:
        details.append((_('Seat'), seat_label(registration.seat)))
    if registration.ticket_type_id:
        details.append((_('Ticket type'), registration.ticket_type.name))
    return Ticket(ticket_uuid=str(registration.ticket_uuid), label=registration.event.title, details=details)


def booking_seat_ticket(booking_seat) -> Ticket:
    details = [(_('Seat'), seat_label(booking_seat.seat))]
    if booking_seat.attendee_name:
        details.append((_('Name'), booking_seat.attendee_name))
    return Ticket(ticket_uuid=str(booking_seat.ticket_uuid), label=seat_label(booking_seat.seat), details=details)


# ───────────────────────── builders ─────────────────────────


def _ticket_purchased(user, event, data) -> Message:
    registration = data['registration']
    return Message(
        title=_('🎫 Ticket confirmed: %(event)s') % {'event': event.title},
        body=_('Your ticket for %(event)s is confirmed. Check My Tickets for your QR code.') % {'event': event.title},
        subject=_('Your ticket for %(event)s') % {'event': event.title},
        headline=_('Your ticket is confirmed'),
        paragraphs=[
            _('Thank you for your purchase. Show the QR code below at the entrance.'),
        ],
        details=[
            *event_details(event),
            *([(_('Paid'), money(data['amount'], data.get('currency')))] if data.get('amount') is not None else []),
        ],
        tickets=[registration_ticket(registration)],
        cta_label=_('Open My Tickets'),
        cta_url=frontend_url('/my-registrations'),
    )


def _registration_confirmed(user, event, data) -> Message:
    registration = data['registration']
    return Message(
        title=_('✅ Registration confirmed: %(event)s') % {'event': event.title},
        body=_('You are registered for %(event)s. Check My Tickets for your QR code.') % {'event': event.title},
        subject=_('You are registered for %(event)s') % {'event': event.title},
        headline=_('You are registered'),
        paragraphs=[_('Your free ticket is ready. Show the QR code below at the entrance.')],
        details=event_details(event),
        tickets=[registration_ticket(registration)],
        cta_label=_('Open My Tickets'),
        cta_url=frontend_url('/my-registrations'),
    )


def _payment_failed(user, event, data) -> Message:
    reason = data.get('reason') or _('Your payment did not go through. You were not charged.')
    return Message(
        title=_('⚠️ Payment failed: %(event)s') % {'event': event.title},
        body=reason,
        subject=_('Payment failed: %(event)s') % {'event': event.title},
        headline=_('Your payment did not go through'),
        paragraphs=[reason, _('You can try again from the event page while tickets are available.')],
        details=event_details(event),
        cta_label=_('Back to the event'),
        cta_url=frontend_url(f'/events/{event.pk}'),
    )


def _payment_refunded(user, event, data) -> Message:
    amount = money(data['amount'], data.get('currency'))
    reason = data.get('reason') or ''
    body = _('You were refunded %(amount)s.') % {'amount': amount}
    if reason:
        body += ' ' + _('Reason: %(reason)s') % {'reason': reason}
    return Message(
        title=_('💸 Refund issued: %(event)s') % {'event': event.title},
        body=body,
        subject=_('Refund of %(amount)s: %(event)s') % {'amount': amount, 'event': event.title},
        headline=_('Your money is on its way back'),
        paragraphs=[
            body,
            _('It goes back to the card or account you paid with. Banks usually take a few business days.'),
        ],
        details=[*event_details(event), (_('Refunded'), amount)],
    )


def _refund_requested(user, event, data) -> Message:
    reason = data.get('reason') or ''
    body = _('%(attendee)s requested a refund of %(amount)s.') % {
        'attendee': data['attendee'],
        'amount': money(data['amount'], data.get('currency')),
    }
    if reason:
        body += ' ' + _('Reason: %(reason)s') % {'reason': reason}
    return Message(
        title=_('💸 Refund requested: %(event)s') % {'event': event.title},
        body=body,
        subject=_('Refund requested: %(event)s') % {'event': event.title},
        headline=_('An attendee asked for a refund'),
        paragraphs=[body, _('Approve or reject it in the attendee list of the event.')],
        details=event_details(event),
        cta_label=_('Review the request'),
        cta_url=frontend_url(f'/organizer/events/{event.pk}/attendees'),
    )


def _with_note(text: str, note: str) -> str:
    return text + (' ' + _('Note: %(note)s') % {'note': note} if note else '')


def _refund_approved(user, event, data) -> Message:
    body = _with_note(_('Your refund has been approved and processed.'), data.get('note') or '')
    return Message(
        title=_('✅ Refund approved: %(event)s') % {'event': event.title},
        body=body,
        subject=_('Refund approved: %(event)s') % {'event': event.title},
        headline=_('Your refund was approved'),
        paragraphs=[body, _('Your ticket for this event is no longer valid.')],
        details=event_details(event),
    )


def _refund_rejected(user, event, data) -> Message:
    body = _with_note(_('Your refund request was declined — your ticket remains valid.'), data.get('note') or '')
    return Message(
        title=_('❌ Refund rejected: %(event)s') % {'event': event.title},
        body=body,
        subject=_('Refund request declined: %(event)s') % {'event': event.title},
        headline=_('Your refund request was declined'),
        paragraphs=[body],
        details=event_details(event),
        cta_label=_('Open My Tickets'),
        cta_url=frontend_url('/my-registrations'),
    )


def _event_updated(user, event, data) -> Message:
    changes = data.get('changes') or []
    body = _('The organizer changed %(fields)s of %(event)s. Please check the new details.') % {
        'fields': ', '.join(label for label, _old, _new in changes) or _('the details'),
        'event': event.title,
    }
    details = [(_('Event'), event.title)]
    for label, old, new in changes:
        details.append((label, _('%(new)s (was %(old)s)') % {'new': new or '—', 'old': old or '—'}))
    return Message(
        title=_('📝 Event updated: %(event)s') % {'event': event.title},
        body=body,
        subject=_('Changed: %(event)s') % {'event': event.title},
        headline=_('Your event has changed'),
        paragraphs=[body, _('Your ticket stays valid.')],
        details=details,
        cta_label=_('View the event'),
        cta_url=frontend_url(f'/events/{event.pk}'),
    )


def _event_cancelled(user, event, data) -> Message:
    refund = data.get('refund')
    body = _('The organizer has cancelled this event.')
    if refund == 'refunded':
        body += ' ' + _('Your payment has been refunded.')
    elif refund == 'failed':
        body += ' ' + _('We could not refund your payment automatically — the organizer will contact you.')
    return Message(
        title=_('❌ Event cancelled: %(event)s') % {'event': event.title},
        body=body,
        subject=_('Cancelled: %(event)s') % {'event': event.title},
        headline=_('This event was cancelled'),
        paragraphs=[body, _('Your tickets for it are no longer valid.')],
        details=event_details(event),
    )


def _seat_available(user, event, data) -> Message:
    minutes = data['minutes']
    body = ngettext(
        'You have %(minutes)d minute to grab your ticket before it passes to the next person.',
        'You have %(minutes)d minutes to grab your ticket before it passes to the next person.',
        minutes,
    ) % {'minutes': minutes}
    return Message(
        title=_('🎉 A spot opened up: %(event)s') % {'event': event.title},
        body=body,
        subject=_('A spot opened up: %(event)s') % {'event': event.title},
        headline=_('A spot is waiting for you'),
        paragraphs=[_('Someone gave up their place and you are next on the waitlist.'), body],
        details=event_details(event),
        cta_label=_('Get my ticket'),
        cta_url=frontend_url(f'/events/{event.pk}'),
    )


def _group_booking_confirmed(user, event, data) -> Message:
    booking = data['booking']
    seats = list(booking.seats.select_related('seat').order_by('seat__row', 'seat__col'))
    count = len(seats)
    body = ngettext(
        'Your group booking of %(count)d seat is confirmed. Tickets are in My Bookings.',
        'Your group booking of %(count)d seats is confirmed. Tickets are in My Bookings.',
        count,
    ) % {'count': count}
    details = [*event_details(event)]
    if data.get('amount') is not None:
        details.append((_('Paid'), money(data['amount'], data.get('currency'))))
    return Message(
        title=ngettext(
            '🎫 %(count)d ticket confirmed: %(event)s',
            '🎫 %(count)d tickets confirmed: %(event)s',
            count,
        )
        % {'count': count, 'event': event.title},
        body=body,
        subject=_('Your group booking for %(event)s') % {'event': event.title},
        headline=_('Your group booking is confirmed'),
        paragraphs=[
            body,
            _('Share the booking link with your friends so they can put their names on their seats.'),
        ],
        details=details,
        tickets=[booking_seat_ticket(bs) for bs in seats],
        cta_label=_('Open My Bookings'),
        cta_url=frontend_url('/my-bookings'),
    )


def _group_booking_claimed(user, event, data) -> Message:
    booking_seat = data['booking_seat']
    owner = data.get('owner_name') or ''
    body = _('You claimed %(seat)s in %(owner)s’s group booking for %(event)s.') % {
        'seat': seat_label(booking_seat.seat),
        'owner': owner,
        'event': event.title,
    }
    return Message(
        title=_('💺 Seat claimed: %(event)s') % {'event': event.title},
        body=body,
        subject=_('Your seat for %(event)s') % {'event': event.title},
        headline=_('Your seat is yours'),
        paragraphs=[body, _('Show the QR code below at the entrance.')],
        details=event_details(event),
        tickets=[booking_seat_ticket(booking_seat)],
    )


def _event_reminder(user, event, data) -> Message:
    when = format_datetime(event.date)
    body = _('%(event)s starts on %(when)s.') % {'event': event.title, 'when': when}
    paragraphs = [body, _('Have your ticket QR code ready at the entrance.')]
    if event.is_online and event.online_link:
        paragraphs.append(_('Join online: %(link)s') % {'link': event.online_link})
    return Message(
        title=_('⏰ Coming up: %(event)s') % {'event': event.title},
        body=body,
        subject=_('Reminder: %(event)s starts soon') % {'event': event.title},
        headline=_('Your event is coming up'),
        paragraphs=paragraphs,
        details=event_details(event),
        cta_label=_('Open My Tickets'),
        cta_url=frontend_url('/my-registrations'),
    )


def _review_reminder(user, event, data) -> Message:
    return Message(
        title=_('⭐ How was %(event)s?') % {'event': event.title},
        body=_('Share your experience and help others discover great events.'),
        subject=_('How was %(event)s?') % {'event': event.title},
        headline=_('How was it?'),
        paragraphs=[_('Share your experience and help others discover great events.')],
        cta_label=_('Leave a review'),
        cta_url=frontend_url(f'/events/{event.pk}'),
    )


def _organizer_message(user, event, data) -> Message:
    subject = data['subject']
    return Message(
        title=f'📣 {event.title}: {subject}',
        body=data['text'],
        subject=f'{event.title}: {subject}',
        headline=subject,
        paragraphs=[p for p in data['text'].split('\n\n') if p.strip()] or [data['text']],
        details=event_details(event),
        cta_label=_('View the event'),
        cta_url=frontend_url(f'/events/{event.pk}'),
    )


BUILDERS: dict[str, Callable] = {
    types.TICKET_PURCHASED: _ticket_purchased,
    types.REGISTRATION_CONFIRMED: _registration_confirmed,
    types.PAYMENT_FAILED: _payment_failed,
    types.PAYMENT_REFUNDED: _payment_refunded,
    types.REFUND_REQUESTED: _refund_requested,
    types.REFUND_APPROVED: _refund_approved,
    types.REFUND_REJECTED: _refund_rejected,
    types.EVENT_UPDATED: _event_updated,
    types.EVENT_CANCELLED: _event_cancelled,
    types.SEAT_AVAILABLE: _seat_available,
    types.GROUP_BOOKING_CONFIRMED: _group_booking_confirmed,
    types.GROUP_BOOKING_CLAIMED: _group_booking_claimed,
    types.EVENT_REMINDER: _event_reminder,
    types.REVIEW_REMINDER: _review_reminder,
    types.ORGANIZER_MESSAGE: _organizer_message,
}


def build_message(type_key: str, user, event, data: dict) -> Message:
    types.get(type_key)
    return BUILDERS[type_key](user, event, data)
