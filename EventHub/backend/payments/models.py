from django.db import models
from events.models import Registration
from common.choices import PaymentStatusChoices


class Payment(models.Model):
    METHOD_CARD = 'card'
    METHOD_OFFLINE = 'offline'
    METHOD_CHOICES = [
        (METHOD_CARD, 'Card (Stripe)'),
        (METHOD_OFFLINE, 'Offline / manual'),
    ]

    registration = models.OneToOneField(Registration, on_delete=models.CASCADE, related_name='payment')
    stripe_payment_intent_id = models.CharField(max_length=255, blank=True)
    stripe_checkout_session_id = models.CharField(max_length=255, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='usd')
    status = models.CharField(max_length=20, choices=PaymentStatusChoices.choices, default=PaymentStatusChoices.PENDING)
    method = models.CharField(max_length=10, choices=METHOD_CHOICES, default=METHOD_CARD)

    # Refund tracking — supports partial refunds (refunded_amount < amount).
    refunded_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    refunded_at = models.DateTimeField(null=True, blank=True)
    refund_reason = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Payment {self.id} - {self.status} - ${self.amount}'

    @property
    def net_amount(self):
        """Amount the organizer actually keeps after refunds."""
        return self.amount - self.refunded_amount

    @property
    def is_refundable(self):
        return self.status == PaymentStatusChoices.COMPLETED and self.refunded_amount < self.amount
