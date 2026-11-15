"""Who may review an event — one rule for the review API and the review
request email (notifications.reminders)."""

from django.contrib.auth.models import User
from django.utils import timezone

from common.choices import RegistrationStatusChoices

from ..models import Registration, Review


def review_refusal(event, user, now=None) -> str | None:
    """Why `user` can't review `event` (None: they can).

    Only attendees with a confirmed ticket may review, once, and only after
    the event has started."""
    now = now or timezone.now()
    if event.date > now:
        return 'You can review an event after it has taken place.'
    attended = Registration.objects.filter(event=event, user=user, status=RegistrationStatusChoices.CONFIRMED).exists()
    if not attended:
        return 'Only attendees with a confirmed ticket can leave a review.'
    if Review.objects.filter(event=event, user=user).exists():
        return 'You have already reviewed this event.'
    return None


def users_who_can_review(event, now=None):
    """Every user `review_refusal` would let review `event`, by id."""
    now = now or timezone.now()
    if event.date > now:
        return User.objects.none()
    attendee_ids = Registration.objects.filter(event=event, status=RegistrationStatusChoices.CONFIRMED).values(
        'user_id'
    )
    reviewer_ids = Review.objects.filter(event=event).values('user_id')
    return (
        User.objects.filter(pk__in=attendee_ids)
        .exclude(pk__in=reviewer_ids)
        .select_related('notification_preference')
        .order_by('pk')
    )
