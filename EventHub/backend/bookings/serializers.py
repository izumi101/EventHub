from rest_framework import serializers

from .models import Booking, BookingSeat


class BookingSeatSerializer(serializers.ModelSerializer):
    row = serializers.IntegerField(source='seat.row', read_only=True)
    col = serializers.IntegerField(source='seat.col', read_only=True)
    zone = serializers.CharField(source='seat.price_zone', read_only=True)
    seat_id = serializers.IntegerField(source='seat.id', read_only=True)
    claimed = serializers.SerializerMethodField()

    class Meta:
        model = BookingSeat
        fields = [
            'id', 'seat_id', 'row', 'col', 'zone', 'price',
            'attendee_name', 'claimed', 'ticket_uuid', 'is_checked_in',
        ]

    def get_claimed(self, obj):
        return bool(obj.attendee_name or obj.claimed_by_id)


class BookingSerializer(serializers.ModelSerializer):
    seats = BookingSeatSerializer(many=True, read_only=True)
    event_title = serializers.CharField(source='event.title', read_only=True)
    event_id = serializers.IntegerField(source='event.id', read_only=True)
    event_date = serializers.DateTimeField(source='event.date', read_only=True)
    event_location = serializers.CharField(source='event.location', read_only=True)
    owner_username = serializers.CharField(source='owner.username', read_only=True)
    total_price = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    seat_count = serializers.IntegerField(read_only=True)
    is_expired = serializers.BooleanField(read_only=True)

    class Meta:
        model = Booking
        fields = [
            'id', 'status', 'share_token', 'hold_expires_at',
            'event_id', 'event_title', 'event_date', 'event_location',
            'owner_username', 'seats', 'seat_count', 'total_price',
            'is_expired', 'created_at',
        ]


class BookingCreateSerializer(serializers.Serializer):
    event = serializers.IntegerField()
    seat_ids = serializers.ListField(
        child=serializers.IntegerField(), allow_empty=False, max_length=8
    )


class ClaimSeatSerializer(serializers.Serializer):
    seat_id = serializers.IntegerField()
    name = serializers.CharField(max_length=120, allow_blank=True)
