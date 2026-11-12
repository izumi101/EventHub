"""Request/response shapes of the booking endpoints, for the OpenAPI schema."""

from rest_framework import serializers

from payments.schema import CheckoutSessionResponseSerializer

from .models import Booking


class BookingCheckoutResponseSerializer(CheckoutSessionResponseSerializer):
    """Same shape as the single-ticket checkout (a Freedom Pay answer carries
    the QR code of the payment page); the group's payment record exists only
    on the Freedom Pay path."""

    mock = serializers.BooleanField(help_text='True when payments run in local mock mode.')
    session_id = serializers.CharField(required=False, help_text='Payment provider session id.')
    payment_id = serializers.IntegerField(
        allow_null=True,
        help_text='Our payment reference for GET /payments/status/{payment_id}/; null on the mock and Stripe paths.',
    )


class BookingStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Booking.Status.choices)


class BookingRefundRequestSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=255)
