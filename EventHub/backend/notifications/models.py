from django.conf import settings
from django.db import models

from . import types


class NotificationPreference(models.Model):
    """A user's email choices and language. No row means every email is on
    and notifications are written in English.

    Only opt-outs are stored, so a type added later is on by default and a
    type that is not optional can never be switched off by stale data.
    """

    class Language(models.TextChoices):
        EN = 'en', 'English'
        RU = 'ru', 'Русский'
        KK = 'kk', 'Қазақша'

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notification_preference'
    )
    # Keys of notifications.types whose email the user switched off.
    email_disabled = models.JSONField(default=list, blank=True)
    # Language of the in-app notifications and emails; empty means English.
    # The frontend saves the language the user picked in the UI.
    language = models.CharField(max_length=8, choices=Language.choices, blank=True, default='')
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Notification preferences of {self.user_id}'

    def email_enabled(self, type_key: str) -> bool:
        spec = types.get(type_key)
        if not spec.sends_email:
            return False
        if not spec.email_optional:
            return True
        return type_key not in (self.email_disabled or [])

    @property
    def effective_language(self) -> str:
        return self.language or self.Language.EN.value


class SentReminder(models.Model):
    """One reminder sent to one user for one event start.

    The unique constraint makes the periodic passes idempotent: a second
    pass (or a second worker) can't insert the row again, so the
    notification is never sent twice. A rescheduled event has a new start
    and gets new reminders. `review` records the review request sent after
    the event, once per (user, event start).
    """

    KIND_24H = '24h'
    KIND_2H = '2h'
    KIND_REVIEW = 'review'
    KIND_CHOICES = [
        (KIND_24H, '24 hours before'),
        (KIND_2H, '2 hours before'),
        (KIND_REVIEW, 'Review request after the event'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='+')
    event = models.ForeignKey('events.Event', on_delete=models.CASCADE, related_name='sent_reminders')
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default=KIND_24H)
    event_starts_at = models.DateTimeField()
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'event', 'kind', 'event_starts_at'], name='uniq_sent_reminder_per_event_start'
            ),
        ]

    def __str__(self):
        return f'{self.kind} reminder of event {self.event_id} to user {self.user_id}'
