"""Request/response shapes of the booking endpoints, for the OpenAPI schema."""

from rest_framework import serializers

from .models import Booking


class BookingCheckoutResponseSerializer(serializers.Serializer):
    checkout_url = serializers.URLField(help_text='Redirect the buyer here to pay.')
    mock = serializers.BooleanField(help_text='True when payments run in local mock mode.')
    session_id = serializers.CharField(required=False, help_text='Payment provider session id.')


class BookingStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Booking.Status.choices)


class BookingRefundRequestSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=255)
