"""Helper for creating in-app notifications."""
from .models import Notification


def notify(user, type: str, title: str, body: str = '', event=None):
    """Create a notification for a user. Swallows all errors."""
    try:
        Notification.objects.create(
            user=user, type=type, title=title, body=body, event=event
        )
    except Exception:
        pass


def notify_ticket_purchased(user, event):
    notify(user, 'ticket_purchased',
           f'🎫 Ticket confirmed: {event.title}',
           f'Your ticket for {event.title} is confirmed. Check My Tickets for your QR code.',
           event)


def notify_payment_failed(user, event):
    notify(user, 'payment_failed',
           f'⚠️ Payment failed: {event.title}',
           'Your seat hold has expired. Please try booking again.',
           event)


def notify_review_reminder(user, event):
    notify(user, 'review_reminder',
           f'⭐ How was {event.title}?',
           'Share your experience and help others discover great events.',
           event)
