"""Request/response shapes of the payment endpoints, for the OpenAPI schema."""
from rest_framework import serializers

from common.choices import PaymentStatusChoices

from .models import Payment

MONEY = {'max_digits': 12, 'decimal_places': 2}


class CheckoutSessionResponseSerializer(serializers.Serializer):
    checkout_url = serializers.URLField(help_text='Redirect the buyer here to pay.')
    session_id = serializers.CharField(help_text='Payment provider session id.')
    mock = serializers.BooleanField(required=False, help_text='Present (true) in local mock mode.')


class PaymentVerificationSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=PaymentStatusChoices.choices)
    event_title = serializers.CharField()
    amount = serializers.DecimalField(**MONEY)
    currency = serializers.CharField(min_length=3, max_length=3)


class RefundRequestSerializer(serializers.Serializer):
    amount = serializers.DecimalField(
        required=False, allow_null=True, **MONEY,
        help_text='Amount to refund; omit for a full refund of what is left.',
    )
    reason = serializers.CharField(required=False, allow_blank=True)


class RefundResultSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=PaymentStatusChoices.choices)
    refunded_amount = serializers.DecimalField(**MONEY)
    net_amount = serializers.DecimalField(**MONEY)


class OfflinePaymentRequestSerializer(serializers.Serializer):
    amount = serializers.DecimalField(
        required=False, allow_null=True, **MONEY,
        help_text='Amount received; defaults to the ticket price.',
    )


class OfflinePaymentResultSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=PaymentStatusChoices.choices)
    amount = serializers.DecimalField(**MONEY)
    method = serializers.ChoiceField(choices=Payment.METHOD_CHOICES)
