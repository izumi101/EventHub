import logging
import re

from rest_framework import serializers
from django.contrib.auth.models import User
from django.utils import timezone
from .models import (
    Category, Event, Registration, SeatMap, EventSeat, Favorite, Review,
    Notification, PromoCode, EventQuestion, QuestionAnswer, WaitlistEntry,
    TicketType, EventStaff, Webhook, Affiliate, RefundRequest,
    CheckInList, CheckInLog,
)
from common.choices import EventStatusChoices, RegistrationStatusChoices
from .services import create_event, update_event

CURRENCY_RE = re.compile(r'^[A-Z]{3}$')
logger = logging.getLogger(__name__)


# ---- ModelSerializer ---- #
class CategorySerializer(serializers.ModelSerializer):
    event_count = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ['id', 'name', 'description', 'icon', 'event_count']

    def get_event_count(self, obj):
        cached = getattr(obj, '_event_count', None)  # annotated by the list view
        if cached is not None:
            return cached
        return obj.events.filter(status=EventStatusChoices.PUBLISHED).count()


class CategoryMiniSerializer(serializers.ModelSerializer):
    """Nested in every event card — no per-event count query."""
    class Meta:
        model = Category
        fields = ['id', 'name', 'description', 'icon']


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

    def validate_price(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError('Price cannot be negative.')
        return value

    def validate_tax_percent(self, value):
        return self._percent(value)

    def validate_service_fee_percent(self, value):
        return self._percent(value)

    @staticmethod
    def _percent(value):
        if value is not None and not (0 <= value <= 100):
            raise serializers.ValidationError('Must be between 0 and 100.')
        return value

    def validate_currency(self, value):
        value = (value or '').strip().upper()
        if not CURRENCY_RE.match(value):
            raise serializers.ValidationError('Use a 3-letter ISO 4217 currency code, e.g. USD or KZT.')
        return value

    def validate_max_participants(self, value):
        if value is not None and value < 1:
            raise serializers.ValidationError('Capacity must be at least 1.')
        if self.instance is not None and value is not None:
            sold = self.instance.active_registration_count + self.instance.booked_seat_count
            if value < sold:
                raise serializers.ValidationError(
                    f'{sold} tickets are already sold or held — capacity cannot go below that.'
                )
        return value

    def validate(self, attrs):
        date = attrs.get('date', getattr(self.instance, 'date', None))
        end_date = attrs.get('end_date', getattr(self.instance, 'end_date', None))
        if date and end_date and end_date < date:
            raise serializers.ValidationError({'end_date': 'The event cannot end before it starts.'})
        if self.instance is None and date and date < timezone.now():
            raise serializers.ValidationError({'date': 'The event date must be in the future.'})
        is_online = attrs.get('is_online', getattr(self.instance, 'is_online', False))
        online_link = attrs.get('online_link', getattr(self.instance, 'online_link', ''))
        if is_online and not online_link:
            raise serializers.ValidationError({'online_link': 'Online events need a link.'})
        return attrs

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
        if price is not None and price < 0:
            raise serializers.ValidationError({'price': 'Price cannot be negative.'})
        if kind == TicketType.KIND_FREE:
            attrs['price'] = 0
        start = attrs.get('sale_start', getattr(self.instance, 'sale_start', None))
        end = attrs.get('sale_end', getattr(self.instance, 'sale_end', None))
        if start and end and end <= start:
            raise serializers.ValidationError({'sale_end': 'Sales must end after they start.'})
        lo = attrs.get('min_per_order', getattr(self.instance, 'min_per_order', 1))
        hi = attrs.get('max_per_order', getattr(self.instance, 'max_per_order', 10))
        if lo and hi and lo > hi:
            raise serializers.ValidationError({'max_per_order': 'Must be at least min_per_order.'})
        return attrs


# ---- ModelSerializer ---- #
class EventListSerializer(serializers.ModelSerializer):
    organizer = OrganizerMiniSerializer(read_only=True)
    category = CategoryMiniSerializer(read_only=True)
    online_link = serializers.SerializerMethodField()
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

    def get_online_link(self, obj):
        # The join link is what an online ticket buys — only the event team
        # and people holding a confirmed ticket get it.
        if not obj.online_link:
            return ''
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if user is None or not user.is_authenticated:
            return ''
        if user.is_superuser or obj.organizer_id == user.id:
            return obj.online_link
        from common.permissions import can_manage_event
        if can_manage_event(obj, user) or obj.registrations.filter(
            user=user, status=RegistrationStatusChoices.CONFIRMED,
        ).exists():
            return obj.online_link
        return ''


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

    def get_fields(self):
        fields = super().get_fields()
        if self.context.get('omit_event'):
            fields.pop('event', None)
        return fields

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
        rows = obj.answers.all()  # prefetch_related('answers__question') upstream
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
            # Don't break the ticket list over one bad row, but a pricing
            # error is a bug — make it visible in the logs.
            logger.exception('Price breakdown failed for registration %s', obj.pk)
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
        if Review.objects.filter(event_id=event_id, user=request.user).exists():
            raise serializers.ValidationError('You have already reviewed this event.')
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
    # Write: invite by username (create only; updates change the role).
    invite_username = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = EventStaff
        fields = ['id', 'username', 'email', 'role', 'invite_username', 'created_at']
        read_only_fields = ['id', 'username', 'email', 'created_at']

    def validate(self, attrs):
        if self.instance is None:
            name = (attrs.get('invite_username') or '').strip()
            if not name:
                raise serializers.ValidationError({'invite_username': 'Enter the username to invite.'})
            user = User.objects.filter(username__iexact=name).first()
            if user is None:
                raise serializers.ValidationError({'invite_username': 'No user with that username.'})
            if self.context['event'].organizer_id == user.id:
                raise serializers.ValidationError({'invite_username': 'The organizer already has full access.'})
            attrs['_invited_user'] = user
        attrs.pop('invite_username', None)
        return attrs

    def create(self, validated_data):
        event = self.context['event']
        user = validated_data.pop('_invited_user')
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

    def validate_url(self, value):
        from .webhooks import is_public_url
        if not is_public_url(value):
            raise serializers.ValidationError(
                'Webhook URLs must be http(s) and resolve to a public internet address.'
            )
        return value

    def validate_secret(self, value):
        # Every delivery is signed: generate a secret when none is given.
        if not (value or '').strip():
            import secrets
            return secrets.token_hex(32)
        return value.strip()

    def create(self, validated_data):
        if not validated_data.get('secret'):
            import secrets
            validated_data['secret'] = secrets.token_hex(32)
        return super().create(validated_data)

    def validate_triggers(self, value):
        valid = {c[0] for c in Webhook.TRIGGER_CHOICES}
        bad = [t for t in (value or []) if t not in valid]
        if bad:
            raise serializers.ValidationError(f'Unknown triggers: {", ".join(bad)}')
        return value


# ---- Affiliates ---- #
def _validate_unique_code(serializer, model, value, label):
    """Case-insensitive per-event uniqueness → a 400 instead of an IntegrityError."""
    code = value.strip().upper()
    event = serializer.instance.event if serializer.instance else serializer.context.get('event')
    if event is not None:
        clash = model.objects.filter(event=event, code__iexact=code)
        if serializer.instance is not None:
            clash = clash.exclude(pk=serializer.instance.pk)
        if clash.exists():
            raise serializers.ValidationError(f'This event already has a {label} with that code.')
    return code


class AffiliateSerializer(serializers.ModelSerializer):
    sales = serializers.ReadOnlyField()
    revenue = serializers.SerializerMethodField()

    class Meta:
        model = Affiliate
        fields = ['id', 'name', 'code', 'clicks', 'sales', 'revenue', 'is_active', 'created_at']
        read_only_fields = ['id', 'clicks', 'sales', 'revenue', 'created_at']

    def validate_code(self, value):
        return _validate_unique_code(self, Affiliate, value, 'referral link')

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
        return _validate_unique_code(self, PromoCode, value, 'promo code')

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
