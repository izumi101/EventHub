from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import Booking, BookingSeat


class BookingSeatSerializer(serializers.ModelSerializer):
    row = serializers.IntegerField(source='seat.row', read_only=True)
    col = serializers.IntegerField(source='seat.col', read_only=True)
    zone = serializers.CharField(source='seat.price_zone', read_only=True)
    seat_id = serializers.IntegerField(source='seat.id', read_only=True)
    claimed = serializers.SerializerMethodField()
    ticket_uuid = serializers.SerializerMethodField()
    claimed_by_me = serializers.SerializerMethodField()

    class Meta:
        model = BookingSeat
        fields = [
            'id', 'seat_id', 'row', 'col', 'zone', 'price',
            'attendee_name', 'claimed', 'claimed_by_me', 'ticket_uuid', 'is_checked_in',
        ]

    def get_claimed(self, obj) -> bool:
        return bool(obj.attendee_name or obj.claimed_by_id)

    def _viewer(self):
        return self.context.get('viewer')

    def get_claimed_by_me(self, obj) -> bool:
        viewer = self._viewer()
        return bool(viewer and viewer.is_authenticated and obj.claimed_by_id == viewer.id)

    @extend_schema_field(serializers.UUIDField(allow_null=True))
    def get_ticket_uuid(self, obj):
        # The UUID *is* the QR ticket. Only the buyer and the friend who
        # claimed this seat may see it — never everyone holding the invite link.
        viewer = self._viewer()
        if not (viewer and viewer.is_authenticated):
            return None
        if viewer.id == obj.booking.owner_id or obj.claimed_by_id == viewer.id:
            return str(obj.ticket_uuid)
        return None


class BookingSerializer(serializers.ModelSerializer):
    seats = serializers.SerializerMethodField()
    event_title = serializers.CharField(source='event.title', read_only=True)
    event_id = serializers.IntegerField(source='event.id', read_only=True)
    event_date = serializers.DateTimeField(source='event.date', read_only=True)
    event_location = serializers.CharField(source='event.location', read_only=True)
    owner_username = serializers.CharField(source='owner.username', read_only=True)
    total_price = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    total_due = serializers.SerializerMethodField()
    currency = serializers.SerializerMethodField()
    seat_count = serializers.IntegerField(read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    is_owner = serializers.SerializerMethodField()
    share_token = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = [
            'id', 'status', 'share_token', 'hold_expires_at',
            'event_id', 'event_title', 'event_date', 'event_location',
            'owner_username', 'seats', 'seat_count', 'total_price', 'total_due', 'currency',
            'amount_paid', 'refunded_at', 'is_expired', 'is_owner', 'created_at',
        ]

    def _viewer(self):
        return self.context.get('viewer')

    @extend_schema_field(BookingSeatSerializer(many=True))
    def get_seats(self, obj):
        seats = obj.seats.select_related('seat', 'booking')
        return BookingSeatSerializer(seats, many=True, context=self.context).data

    def get_is_owner(self, obj) -> bool:
        viewer = self._viewer()
        return bool(viewer and viewer.is_authenticated and viewer.id == obj.owner_id)

    @extend_schema_field(serializers.UUIDField(allow_null=True))
    def get_share_token(self, obj):
        # Whoever opened the share link already knows it; everyone else
        # only sees it if they own the booking.
        if self.get_is_owner(obj) or self.context.get('via_share_link'):
            return str(obj.share_token)
        return None

    @extend_schema_field(serializers.DecimalField(max_digits=12, decimal_places=2))
    def get_total_due(self, obj):
        # Seat prices plus tax & service fee — what checkout actually charges.
        from .payments import booking_amount
        return str(booking_amount(obj))

    def get_currency(self, obj) -> str:
        from events.billing import event_currency
        return event_currency(obj.event)


class BookingCreateSerializer(serializers.Serializer):
    event = serializers.IntegerField()
    seat_ids = serializers.ListField(
        child=serializers.IntegerField(), allow_empty=False, max_length=8
    )


class ClaimSeatSerializer(serializers.Serializer):
    seat_id = serializers.IntegerField()
    name = serializers.CharField(max_length=120, allow_blank=True)
