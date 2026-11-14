"""The catalogue of notification types.

Every notification a user can receive is one of these. The key is stored in
`events_notification.type`; the flags decide whether an email is sent and
whether the user may switch that email off. In-app notifications are always
created. Security emails (sign-up codes, password reset, 2FA) are not
notifications: they are sent directly by `accounts` and can't be disabled.

This module imports no models, so `events.models` can use it for choices.
"""

from dataclasses import dataclass

from django.utils.translation import gettext_lazy as _


@dataclass(frozen=True)
class NotificationType:
    key: str
    label: str
    description: str
    # False: the email is always sent (the user can't switch it off).
    email_optional: bool = True
    # Whether an email is sent at all (some types are in-app only).
    sends_email: bool = True


TICKET_PURCHASED = 'ticket_purchased'
REGISTRATION_CONFIRMED = 'registration_confirmed'
PAYMENT_FAILED = 'payment_failed'
PAYMENT_REFUNDED = 'payment_refunded'
REFUND_REQUESTED = 'refund_requested'
REFUND_APPROVED = 'refund_approved'
REFUND_REJECTED = 'refund_rejected'
EVENT_UPDATED = 'event_updated'
EVENT_CANCELLED = 'event_cancelled'
SEAT_AVAILABLE = 'seat_available'
GROUP_BOOKING_CONFIRMED = 'group_booking_confirmed'
GROUP_BOOKING_CLAIMED = 'group_booking_claimed'
EVENT_REMINDER = 'event_reminder'
REVIEW_REMINDER = 'review_reminder'
ORGANIZER_MESSAGE = 'organizer_message'
SECURITY_ALERT = 'security_alert'

TYPES: dict[str, NotificationType] = {
    t.key: t
    for t in (
        NotificationType(
            TICKET_PURCHASED,
            _('Ticket purchased'),
            _('Your e-ticket with the QR code after a successful payment.'),
        ),
        NotificationType(
            REGISTRATION_CONFIRMED,
            _('Free registration confirmed'),
            _('Your e-ticket after registering for a free event.'),
        ),
        NotificationType(
            PAYMENT_FAILED,
            _('Payment failed'),
            _('A payment did not go through or arrived too late.'),
        ),
        NotificationType(
            PAYMENT_REFUNDED,
            _('Payment refunded'),
            _('Money was returned to you. Always emailed: it is a record of the refund.'),
            email_optional=False,
        ),
        NotificationType(
            REFUND_REQUESTED,
            _('Refund requested'),
            _('Organizers: an attendee asked for a refund.'),
        ),
        NotificationType(
            REFUND_APPROVED,
            _('Refund request approved'),
            _('The organizer approved your refund request.'),
        ),
        NotificationType(
            REFUND_REJECTED,
            _('Refund request rejected'),
            _('The organizer declined your refund request.'),
        ),
        NotificationType(
            EVENT_UPDATED,
            _('Event changed'),
            _('The date or venue of an event you have a ticket for changed.'),
        ),
        NotificationType(
            EVENT_CANCELLED,
            _('Event cancelled'),
            _('An event you have a ticket for was cancelled. Always emailed.'),
            email_optional=False,
        ),
        NotificationType(
            SEAT_AVAILABLE,
            _('Waitlist spot available'),
            _('A spot opened up for an event you are waiting for.'),
        ),
        NotificationType(
            GROUP_BOOKING_CONFIRMED,
            _('Group booking confirmed'),
            _('Your group booking is paid, with the tickets for every seat.'),
        ),
        NotificationType(
            GROUP_BOOKING_CLAIMED,
            _('Group booking seat claimed'),
            _('You claimed a seat in a friend’s group booking.'),
        ),
        NotificationType(
            EVENT_REMINDER,
            _('Event reminder'),
            _('A reminder 24 hours before an event you have a ticket for.'),
        ),
        NotificationType(
            REVIEW_REMINDER,
            _('Review reminder'),
            _('An invitation to review an event you attended.'),
            sends_email=False,
        ),
        NotificationType(
            ORGANIZER_MESSAGE,
            _('Messages from organizers'),
            _('Announcements an organizer sends to the attendees of an event.'),
        ),
        NotificationType(
            SECURITY_ALERT,
            _('Security alert'),
            _('A change to your sign-in or two-factor settings. Always emailed.'),
            email_optional=False,
        ),
    )
}

# For the `type` column of events.Notification (and the OpenAPI enum).
CHOICES = [(t.key, t.label) for t in TYPES.values()]
# Types whose email the user can switch off (the preferences page).
EMAIL_OPTIONAL_TYPES = [t.key for t in TYPES.values() if t.sends_email and t.email_optional]


def get(key: str) -> NotificationType:
    try:
        return TYPES[key]
    except KeyError:
        raise ValueError(f'Unknown notification type: {key}') from None
