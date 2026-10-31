"""Money records (ADR 0001, docs/adr/0001-payment-provider-layer.md).

`Payment` is the provider-neutral record of one payable thing: a ticket
registration or a group booking. `Refund` is the per-refund ledger and
`PaymentEvent` the log of provider callbacks.

Expand step of the migration plan: the provider-neutral columns exist next
to the legacy `stripe_*` columns, which the current services still read and
write. The switch to the new columns and the removal of the old ones happen
in a later work package.
"""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q, Value

from common.choices import PaymentCallbackKind, PaymentProviderChoices, PaymentStatusChoices
from events.models import Registration

MONEY = {'max_digits': 12, 'decimal_places': 2}


class Payment(models.Model):
    METHOD_CARD = 'card'
    METHOD_OFFLINE = 'offline'
    METHOD_CHOICES = [
        (METHOD_CARD, 'Card (Stripe)'),
        (METHOD_OFFLINE, 'Offline / manual'),
    ]

    # Exactly one of `registration` / `booking` is set (constraint below).
    # PROTECT: money records must never disappear with an event or a user.
    registration = models.OneToOneField(
        Registration, on_delete=models.PROTECT, related_name='payment', null=True, blank=True
    )
    booking = models.OneToOneField(
        'bookings.Booking', on_delete=models.PROTECT, related_name='payment', null=True, blank=True
    )

    # Legacy Stripe columns: still written by the current services.
    stripe_payment_intent_id = models.CharField(max_length=255, blank=True)
    stripe_checkout_session_id = models.CharField(max_length=255, blank=True)

    # Provider-neutral columns. `provider` is empty only while no provider
    # attempt was made. The database defaults let code that predates these
    # columns keep inserting rows while a release is rolled out.
    provider = models.CharField(
        max_length=20, choices=PaymentProviderChoices.choices, blank=True, default='', db_default=''
    )
    # Checkout session / init_payment id of the current attempt.
    provider_session_id = models.CharField(max_length=255, blank=True, default='', db_default='')
    # Payment intent / pg_payment_id: what refunds and reconciliation use.
    provider_payment_id = models.CharField(max_length=255, blank=True, default='', db_default='', db_index=True)
    # Provider-specific details. Never secrets or card data.
    provider_payload = models.JSONField(default=dict, db_default=Value({}, output_field=models.JSONField()), blank=True)
    # Incremented for every new provider session on this payment; part of
    # the provider idempotency key (`payment-<id>-attempt-<n>`).
    attempt = models.PositiveIntegerField(default=0, db_default=0)

    amount = models.DecimalField(**MONEY)
    currency = models.CharField(max_length=3, default='usd')
    status = models.CharField(max_length=20, choices=PaymentStatusChoices.choices, default=PaymentStatusChoices.PENDING)
    method = models.CharField(max_length=10, choices=METHOD_CHOICES, default=METHOD_CARD)

    # Refund tracking — supports partial refunds (refunded_amount < amount).
    refunded_amount = models.DecimalField(**MONEY, default=0)
    refunded_at = models.DateTimeField(null=True, blank=True)
    refund_reason = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(registration__isnull=False, booking__isnull=True)
                    | Q(registration__isnull=True, booking__isnull=False)
                ),
                name='payment_exactly_one_target',
            ),
            # One provider session belongs to one payment. Empty ids (no
            # attempt yet, or offline) are not unique.
            models.UniqueConstraint(
                fields=['provider', 'provider_session_id'],
                condition=~Q(provider_session_id=''),
                name='uniq_payment_provider_session',
            ),
        ]
        indexes = [
            # Reconciliation scans payments that stay pending too long.
            models.Index(fields=['status', 'created_at'], name='payment_status_created_idx'),
        ]

    def __str__(self):
        return f'Payment {self.id} - {self.status} - ${self.amount}'

    @property
    def net_amount(self):
        """Amount the organizer actually keeps after refunds."""
        return self.amount - self.refunded_amount

    @property
    def is_refundable(self):
        return self.status == PaymentStatusChoices.COMPLETED and self.refunded_amount < self.amount


class Refund(models.Model):
    """One refund of (part of) a payment.

    Rows are inserted `pending` under the Payment lock and finalised by the
    refund job after the provider call. Invariant kept by the service layer:
    the sum of `succeeded` and `pending` refunds of a payment never exceeds
    `payment.amount`.

    The primary key is a UUID so that `idempotency_key` can be derived from
    the row id before the row is inserted, and never from mutable balances.
    """

    class Kind(models.TextChoices):
        CUSTOMER = 'customer', 'Customer request'
        ORGANIZER = 'organizer', 'Organizer'
        EVENT_CANCELLED = 'event_cancelled', 'Event cancelled'
        LATE_PAYMENT = 'late_payment', 'Late payment'
        DUPLICATE = 'duplicate', 'Duplicate payment'
        ORPHAN = 'orphan', 'Orphan payment'
        AMOUNT_MISMATCH = 'amount_mismatch', 'Amount mismatch'
        CHARGEBACK = 'chargeback', 'Chargeback'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        SUCCEEDED = 'succeeded', 'Succeeded'
        FAILED = 'failed', 'Failed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Null only for an orphan refund: money arrived for a payment we do not
    # know, so the refund names the provider and its payment id directly.
    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name='refunds', null=True, blank=True)
    amount = models.DecimalField(**MONEY)
    currency = models.CharField(max_length=3)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    reason = models.CharField(max_length=255, blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+'
    )
    # The refund always goes through the provider that took the money; both
    # values are a snapshot taken when the refund is requested.
    provider = models.CharField(max_length=20, choices=PaymentProviderChoices.choices, blank=True)
    provider_payment_id = models.CharField(max_length=255, blank=True)
    provider_refund_id = models.CharField(max_length=255, blank=True, db_index=True)
    idempotency_key = models.CharField(max_length=80, unique=True, editable=False)
    error = models.TextField(blank=True)
    attempts = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['created_at']
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name='refund_amount_positive'),
            models.CheckConstraint(condition=Q(currency__regex=r'^[A-Z]{3}$'), name='refund_currency_iso_upper'),
            models.CheckConstraint(condition=~Q(idempotency_key=''), name='refund_idempotency_key_set'),
            # A finished refund records when it finished.
            models.CheckConstraint(
                condition=Q(status='pending') | Q(processed_at__isnull=False),
                name='refund_processed_at_when_final',
            ),
            models.CheckConstraint(
                condition=(
                    Q(payment__isnull=False) | (Q(kind='orphan') & ~Q(provider='') & ~Q(provider_payment_id=''))
                ),
                name='refund_payment_or_orphan_target',
            ),
        ]
        indexes = [
            models.Index(fields=['payment', 'status'], name='refund_payment_status_idx'),
            # The refund job and the alerting scan unfinished refunds.
            models.Index(fields=['status', 'created_at'], name='refund_status_created_idx'),
        ]

    def __str__(self):
        return f'Refund {self.id} - {self.kind} - {self.amount} {self.currency} - {self.status}'

    def save(self, *args, **kwargs):
        if not self.idempotency_key:
            self.idempotency_key = f'refund-{self.pk}'
        super().save(*args, **kwargs)


class PaymentEvent(models.Model):
    """A provider callback, stored once per (`provider`, `event_id`).

    The row is inserted in the same transaction that applies the callback,
    so a re-delivered callback hits the unique constraint and is answered
    with the acknowledgement again instead of being applied twice.
    """

    class Outcome(models.TextChoices):
        PROCESSED = 'processed', 'Processed'
        IGNORED = 'ignored', 'Ignored'
        ORPHAN = 'orphan', 'No matching payment'
        DUPLICATE_PAYMENT = 'duplicate_payment', 'Duplicate payment'
        LATE_PAYMENT = 'late_payment', 'Late payment'
        AMOUNT_MISMATCH = 'amount_mismatch', 'Amount or currency mismatch'
        REJECTED = 'rejected', 'Rejected (not allowed in the payment state)'

    provider = models.CharField(max_length=20, choices=PaymentProviderChoices.choices)
    # The provider's event id, or a stable hash of the callback for
    # providers without one.
    event_id = models.CharField(max_length=255)
    kind = models.CharField(max_length=20, choices=PaymentCallbackKind.choices)
    # Null for orphans: the callback matched no payment.
    payment = models.ForeignKey(
        Payment, on_delete=models.PROTECT, related_name='provider_events', null=True, blank=True
    )
    # Sanitised: never secrets or card data.
    payload = models.JSONField(default=dict, blank=True)
    outcome = models.CharField(max_length=20, choices=Outcome.choices, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['received_at']
        constraints = [
            models.UniqueConstraint(fields=['provider', 'event_id'], name='uniq_payment_event_provider_event'),
            models.CheckConstraint(condition=~Q(event_id=''), name='payment_event_id_set'),
        ]
        indexes = [
            models.Index(fields=['payment', 'received_at'], name='payment_event_payment_idx'),
            # Orphans and mismatches are reviewed by operators.
            models.Index(fields=['outcome', 'received_at'], name='payment_event_outcome_idx'),
        ]

    def __str__(self):
        return f'{self.provider} {self.kind} {self.event_id}'
