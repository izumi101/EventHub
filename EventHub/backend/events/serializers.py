from rest_framework import serializers
from django.contrib.auth.models import User
from .models import (
    Category, Event, Registration, SeatMap, EventSeat, Favorite, Review,
    Notification, PromoCode, EventQuestion, QuestionAnswer, WaitlistEntry,
    TicketType, EventStaff, Webhook, Affiliate, RefundRequest,
    CheckInList, CheckInLog,
)
from common.choices import EventStatusChoices, RegistrationStatusChoices
from .services import create_event, update_event


# ---- ModelSerializer ---- #
class CategorySerializer(serializers.ModelSerializer):
    event_count = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ['id', 'name', 'description', 'icon', 'event_count']

    def get_event_count(self, obj):
        return obj.events.filter(status=EventStatusChoices.PUBLISHED).count()


# ---- Serializer (manual) for event creation ---- #
class EventCreateSerializer(serializers.ModelSerializer):
    category_id = serializers.PrimaryKeyRelatedField(
        source='category',
        queryset=Category.objects.all(),
        write_only=True,
    )
    
    class Meta:
        model = Event
        fields = [
            'id', 'title', 'description', 'category_id', 'date',
            'end_date', 'location', 'address', 'image', 'price',
            'max_participants', 'status', 'is_online', 'online_link',
            'tax_percent', 'service_fee_percent', 'fees_passed_to_buyer', 'currency',
            'refundable', 'seo_title', 'seo_description',
        ]
        read_only_fields = ['id', 'status']
        extra_kwargs = {
            'end_date': {'required': False, 'allow_null': True},
            'address': {'required': False, 'allow_blank': True},
            'image': {'required': False, 'allow_null': True},
            'online_link': {'required': False, 'allow_blank': True},
            'price': {'required': False},
            'max_participants': {'required': False},
            'tax_percent': {'required': False},
            'service_fee_percent': {'required': False},
            'fees_passed_to_buyer': {'required': False},
            'currency': {'required': False},
            'refundable': {'required': False},
        }

    def create(self, validated_data):
        organizer = self.context['request'].user
        return create_event(organizer=organizer, validated_data=validated_data)

    def update(self, instance, validated_data):
        return update_event(event=instance, validated_data=validated_data)


class OrganizerMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name']


# ---- Ticket types ---- #
class TicketTypeSerializer(serializers.ModelSerializer):
    sold = serializers.ReadOnlyField()
    available = serializers.ReadOnlyField()
    is_sold_out = serializers.ReadOnlyField()
    on_sale = serializers.ReadOnlyField()
    sale_state = serializers.ReadOnlyField()

    class Meta:
        model = TicketType
        fields = [
            'id', 'name', 'description', 'kind', 'price', 'quantity',
            'min_per_order', 'max_per_order', 'sale_start', 'sale_end',
            'is_active', 'order', 'sold', 'available', 'is_sold_out',
            'on_sale', 'sale_state',
        ]
        read_only_fields = ['id', 'sold', 'available', 'is_sold_out', 'on_sale', 'sale_state']

    def validate(self, attrs):
        kind = attrs.get('kind', getattr(self.instance, 'kind', TicketType.KIND_PAID))
        price = attrs.get('price', getattr(self.instance, 'price', 0))
        if kind == TicketType.KIND_PAID and (price is None or price <= 0):
            raise serializers.ValidationError({'price': 'Paid tickets need a price above zero.'})
        if kind == TicketType.KIND_FREE:
            attrs['price'] = 0
        return attrs


# ---- ModelSerializer ---- #
class EventListSerializer(serializers.ModelSerializer):
    organizer = OrganizerMiniSerializer(read_only=True)
    category = CategorySerializer(read_only=True)
    available_spots = serializers.ReadOnlyField()
    is_free = serializers.ReadOnlyField()
    has_ticket_types = serializers.ReadOnlyField()
    price_from = serializers.ReadOnlyField()
    ticket_types = TicketTypeSerializer(many=True, read_only=True)
    registered_count = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = [
            'id', 'title', 'description', 'organizer', 'category',
            'date', 'end_date', 'location', 'address', 'image',
            'price', 'max_participants', 'status', 'is_online',
            'online_link', 'available_spots', 'is_free',
            'has_ticket_types', 'price_from', 'ticket_types',
            'tax_percent', 'service_fee_percent', 'fees_passed_to_buyer', 'currency',
            'refundable', 'registered_count', 'created_at',
            'seo_title', 'seo_description',
        ]

    def get_registered_count(self, obj):
        # Derived from available_spots (registrations + group-booking seats),
        # so the "X left / Y registered" capacity bar never contradicts itself.
        return max(obj.max_participants - obj.available_spots, 0)


# ---- ModelSerializer ---- #
class RegistrationSerializer(serializers.ModelSerializer):
    event = EventListSerializer(read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    full_name = serializers.SerializerMethodField()
    seat = serializers.SerializerMethodField()
    payment = serializers.SerializerMethodField()
    promo = serializers.SerializerMethodField()

    class Meta:
        model = Registration
        fields = [
            'id', 'event', 'username', 'email', 'full_name', 'status', 'registered_at',
            'notes', 'ticket_uuid', 'is_checked_in', 'checked_in_at', 'seat',
            'payment', 'promo', 'ticket_type', 'answers', 'breakdown', 'refund_request',
        ]
        read_only_fields = ['id', 'registered_at', 'status', 'ticket_uuid', 'is_checked_in', 'checked_in_at']

    def get_full_name(self, obj):
        name = f'{obj.user.first_name} {obj.user.last_name}'.strip()
        return name or obj.user.username

    def get_seat(self, obj):
        if obj.seat:
            return {'id': obj.seat.id, 'row': obj.seat.row, 'col': obj.seat.col, 'zone': obj.seat.price_zone}
        return None

    def get_payment(self, obj):
        pay = getattr(obj, 'payment', None)
        if not pay:
            return None
        return {
            'amount': str(pay.amount),
            'status': pay.status,
            'method': pay.method,
            'refunded_amount': str(pay.refunded_amount),
            'net_amount': str(pay.net_amount),
            'is_refundable': pay.is_refundable,
        }

    def get_promo(self, obj):
        if obj.promo_code_id and obj.promo_code:
            return {'code': obj.promo_code.code}
        return None

    ticket_type = serializers.SerializerMethodField()

    def get_ticket_type(self, obj):
        if obj.ticket_type_id and obj.ticket_type:
            return {'id': obj.ticket_type.id, 'name': obj.ticket_type.name, 'kind': obj.ticket_type.kind}
        return None

    answers = serializers.SerializerMethodField()

    def get_answers(self, obj):
        rows = obj.answers.select_related('question').all()
        return [
            {'label': a.question.label, 'answer': a.answer, 'type': a.question.question_type}
            for a in rows
        ]

    breakdown = serializers.SerializerMethodField()

    def get_breakdown(self, obj):
        if obj.event.is_free and not obj.ticket_type_id:
            return None
        try:
            from .billing import price_breakdown
            return price_breakdown(obj)
        except Exception:
            return None

    refund_request = serializers.SerializerMethodField()

    def get_refund_request(self, obj):
        rr = getattr(obj, 'refund_request', None)
        if not rr:
            return None
        return {
            'status': rr.status,
            'reason': rr.reason,
            'organizer_note': rr.organizer_note,
            'created_at': rr.created_at,
        }


# ---- Seat Serializers ---- #
class EventSeatSerializer(serializers.ModelSerializer):
    price = serializers.SerializerMethodField()

    class Meta:
        model = EventSeat
        fields = ['id', 'row', 'col', 'price_zone', 'is_available', 'price']

    def get_price(self, obj):
        event = self.context.get('event')
        if event is None:
            return None
        from .seat_pricing import seat_price
        try:
            return str(seat_price(event, obj))
        except Exception:
            return None


class SeatMapSerializer(serializers.ModelSerializer):
    seats = serializers.SerializerMethodField()
    zone_prices = serializers.SerializerMethodField()

    class Meta:
        model = SeatMap
        fields = ['id', 'rows', 'cols', 'layout', 'seats', 'zone_prices']

    def get_seats(self, obj):
        seats_qs = obj.seats.all()
        return EventSeatSerializer(seats_qs, many=True, context={'event': obj.event}).data

    def get_zone_prices(self, obj):
        from .seat_pricing import zone_price_table
        return zone_price_table(obj.event)


# ---- Favorites ---- #
class FavoriteSerializer(serializers.ModelSerializer):
    event = EventListSerializer(read_only=True)

    class Meta:
        model = Favorite
        fields = ['id', 'event', 'created_at']
        read_only_fields = ['id', 'created_at']


# ---- Reviews ---- #
class ReviewSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    avatar = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = ['id', 'username', 'avatar', 'rating', 'comment', 'created_at']
        read_only_fields = ['id', 'username', 'avatar', 'created_at']

    def get_avatar(self, obj):
        try:
            avatar = obj.user.profile.avatar
            return avatar.url if avatar else None
        except Exception:
            return None


class ReviewCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = ['rating', 'comment']

    def validate(self, attrs):
        """Only confirmed attendees may review, and only once the event started."""
        from django.utils import timezone

        request = self.context.get('request')
        event_id = self.context.get('event_id')
        if request is None or event_id is None:
            return attrs

        event = Event.objects.filter(pk=event_id).first()
        if event is None:
            raise serializers.ValidationError('Event not found.')
        if event.date > timezone.now():
            raise serializers.ValidationError('You can review an event after it has taken place.')

        attended = Registration.objects.filter(
            event_id=event_id, user=request.user,
            status=RegistrationStatusChoices.CONFIRMED,
        ).exists()
        if not attended:
            raise serializers.ValidationError('Only attendees with a confirmed ticket can leave a review.')
        return attrs


# ---- Notifications ---- #
class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['id', 'type', 'title', 'body', 'event', 'is_read', 'created_at']
        read_only_fields = ['id', 'type', 'title', 'body', 'event', 'created_at']


# ---- Refund requests ---- #
class RefundRequestSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='registration.user.username', read_only=True)
    full_name = serializers.SerializerMethodField()
    amount = serializers.SerializerMethodField()
    ticket_type = serializers.SerializerMethodField()

    class Meta:
        model = RefundRequest
        fields = ['id', 'username', 'full_name', 'amount', 'ticket_type',
                  'status', 'reason', 'organizer_note', 'created_at', 'resolved_at']
        read_only_fields = fields

    def get_full_name(self, obj):
        u = obj.registration.user
        return f'{u.first_name} {u.last_name}'.strip() or u.username

    def get_amount(self, obj):
        pay = getattr(obj.registration, 'payment', None)
        return str(pay.net_amount) if pay else '0.00'

    def get_ticket_type(self, obj):
        tt = obj.registration.ticket_type
        return tt.name if tt else None


# ---- Event staff / roles ---- #
class EventStaffSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    # Write: invite by username.
    invite_username = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = EventStaff
        fields = ['id', 'username', 'email', 'role', 'invite_username', 'created_at']
        read_only_fields = ['id', 'username', 'email', 'created_at']

    def validate_invite_username(self, value):
        from django.contrib.auth.models import User
        user = User.objects.filter(username__iexact=value.strip()).first()
        if user is None:
            raise serializers.ValidationError('No user with that username.')
        self._invited_user = user
        return value

    def create(self, validated_data):
        validated_data.pop('invite_username', None)
        event = self.context['event']
        user = self._invited_user
        if event.organizer_id == user.id:
            raise serializers.ValidationError('The organizer already has full access.')
        staff, _ = EventStaff.objects.update_or_create(
            event=event, user=user, defaults={'role': validated_data.get('role', EventStaff.ROLE_CHECK_IN)},
        )
        return staff


# ---- Webhooks ---- #
class WebhookSerializer(serializers.ModelSerializer):
    deliveries_count = serializers.SerializerMethodField()

    class Meta:
        model = Webhook
        fields = ['id', 'url', 'secret', 'triggers', 'is_active', 'created_at',
                  'last_triggered_at', 'last_status', 'deliveries_count']
        read_only_fields = ['id', 'created_at', 'last_triggered_at', 'last_status', 'deliveries_count']

    def get_deliveries_count(self, obj):
        return obj.deliveries.count()

    def validate_triggers(self, value):
        valid = {c[0] for c in Webhook.TRIGGER_CHOICES}
        bad = [t for t in (value or []) if t not in valid]
        if bad:
            raise serializers.ValidationError(f'Unknown triggers: {", ".join(bad)}')
        return value


# ---- Affiliates ---- #
class AffiliateSerializer(serializers.ModelSerializer):
    sales = serializers.ReadOnlyField()
    revenue = serializers.SerializerMethodField()

    class Meta:
        model = Affiliate
        fields = ['id', 'name', 'code', 'clicks', 'sales', 'revenue', 'is_active', 'created_at']
        read_only_fields = ['id', 'clicks', 'sales', 'revenue', 'created_at']

    def validate_code(self, value):
        return value.strip().upper()

    def get_revenue(self, obj):
        from decimal import Decimal
        total = Decimal('0')
        for r in obj.registrations.select_related('payment').all():
            pay = getattr(r, 'payment', None)
            if pay and pay.status == 'completed':
                total += pay.net_amount
        return str(total)


# ---- Promo codes ---- #
class PromoCodeSerializer(serializers.ModelSerializer):
    is_valid = serializers.ReadOnlyField()
    is_expired = serializers.ReadOnlyField()
    is_exhausted = serializers.ReadOnlyField()

    class Meta:
        model = PromoCode
        fields = [
            'id', 'code', 'discount_type', 'discount_value', 'max_uses',
            'times_used', 'expires_at', 'is_active', 'created_at',
            'is_valid', 'is_expired', 'is_exhausted',
        ]
        read_only_fields = ['id', 'times_used', 'created_at']

    def validate_code(self, value):
        return value.strip().upper()

    def validate_discount_value(self, value):
        if value <= 0:
            raise serializers.ValidationError('Discount must be greater than zero.')
        return value

    def validate(self, attrs):
        dtype = attrs.get('discount_type', getattr(self.instance, 'discount_type', None))
        dval = attrs.get('discount_value', getattr(self.instance, 'discount_value', None))
        if dtype == PromoCode.DISCOUNT_PERCENT and dval and dval > 100:
            raise serializers.ValidationError({'discount_value': 'Percentage cannot exceed 100.'})
        return attrs


# ---- Custom checkout questions ---- #
class EventQuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = EventQuestion
        fields = ['id', 'label', 'question_type', 'options', 'is_required', 'order']
        read_only_fields = ['id']

    def validate(self, attrs):
        qtype = attrs.get('question_type', getattr(self.instance, 'question_type', None))
        options = attrs.get('options', getattr(self.instance, 'options', []))
        if qtype == EventQuestion.TYPE_DROPDOWN and not options:
            raise serializers.ValidationError({'options': 'Dropdown questions need at least one option.'})
        return attrs


# ---- Check-in lists ---- #
class CheckInLogSerializer(serializers.ModelSerializer):
    scanned_by_username = serializers.CharField(source='scanned_by.username', read_only=True, default='')
    attendee = serializers.SerializerMethodField()

    class Meta:
        model = CheckInLog
        fields = ['id', 'action', 'attendee', 'scanned_by_username', 'note', 'created_at']
        read_only_fields = fields

    def get_attendee(self, obj):
        u = obj.registration.user
        return {
            'id': obj.registration.id,
            'username': u.username,
            'full_name': f'{u.first_name} {u.last_name}'.strip() or u.username,
        }


class CheckInListSerializer(serializers.ModelSerializer):
    log_count = serializers.SerializerMethodField()
    checked_in_count = serializers.SerializerMethodField()

    class Meta:
        model = CheckInList
        fields = ['id', 'name', 'description', 'color', 'is_default',
                  'log_count', 'checked_in_count', 'created_at']
        read_only_fields = ['id', 'log_count', 'checked_in_count', 'created_at']

    def get_log_count(self, obj):
        return obj.logs.filter(action=CheckInLog.ACTION_CHECK_IN).count()

    def get_checked_in_count(self, obj):
        # Currently-checked-in = registrations whose most-recent action in this
        # list is a check-in (an 'undo' afterwards cancels it).
        latest = {}
        for reg_id, action in obj.logs.order_by('registration_id', '-created_at').values_list('registration_id', 'action'):
            if reg_id not in latest:
                latest[reg_id] = action
        return sum(1 for a in latest.values() if a == CheckInLog.ACTION_CHECK_IN)


class QuestionAnswerSerializer(serializers.ModelSerializer):
    label = serializers.CharField(source='question.label', read_only=True)
    question_type = serializers.CharField(source='question.question_type', read_only=True)

    class Meta:
        model = QuestionAnswer
        fields = ['question', 'label', 'question_type', 'answer']


# ---- Waitlist ---- #
class WaitlistEntrySerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    event_title = serializers.CharField(source='event.title', read_only=True)
    position = serializers.SerializerMethodField()

    class Meta:
        model = WaitlistEntry
        fields = ['id', 'username', 'event', 'event_title', 'status', 'position',
                  'offer_expires_at', 'created_at']
        read_only_fields = fields

    def get_position(self, obj):
        if obj.status != WaitlistEntry.STATUS_WAITING:
            return 0
        return WaitlistEntry.objects.filter(
            event=obj.event, status=WaitlistEntry.STATUS_WAITING, created_at__lt=obj.created_at,
        ).count() + 1
