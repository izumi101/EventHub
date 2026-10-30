"""Request/response shapes of event endpoints that don't map onto one model
serializer, for the OpenAPI schema. Documentation only: the views keep
parsing and building these payloads themselves."""

from rest_framework import serializers

from common.choices import EventStatusChoices, RegistrationStatusChoices

from .models import CheckInLog, PromoCode, RefundRequest, WaitlistEntry
from .serializers import AttendeeRegistrationSerializer, EventListSerializer

MONEY = {'max_digits': 12, 'decimal_places': 2}

# Value sets named in SPECTACULAR_SETTINGS['ENUM_NAME_OVERRIDES'].
DEMAND_LEVELS = ['free', 'low', 'medium', 'high', 'surge']
QUEUE_STATUSES = ['queued', 'admitted', 'not_in_queue', 'not_needed']
WAITLIST_STATUSES = [value for value, _ in WaitlistEntry.STATUS_CHOICES] + ['spots_available', 'left', 'not_joined']
SCAN_RESULTS = ['success', 'used']
SCAN_REFUSALS = ['invalid']


# ---- Organizer dashboards ---- #
class EventStatsSerializer(serializers.Serializer):
    total_registrations = serializers.IntegerField()
    checked_in = serializers.IntegerField()
    remaining = serializers.IntegerField()
    check_in_rate = serializers.FloatField(help_text='Percent, 0–100.')
    net_revenue = serializers.DecimalField(**MONEY, help_text='Tickets and group bookings, net of refunds.')
    currency = serializers.CharField(min_length=3, max_length=3)


class AnalyticsKpisSerializer(serializers.Serializer):
    net_revenue = serializers.FloatField()
    gross_revenue = serializers.FloatField()
    refunded = serializers.FloatField()
    tickets_sold = serializers.IntegerField()
    paid_orders = serializers.IntegerField()
    avg_order_value = serializers.FloatField()
    capacity = serializers.IntegerField()
    sold_through_pct = serializers.FloatField()
    checked_in = serializers.IntegerField()
    checkin_rate_pct = serializers.FloatField()
    pending = serializers.IntegerField()
    group_bookings = serializers.IntegerField()
    group_seats = serializers.IntegerField()


class AnalyticsDaySerializer(serializers.Serializer):
    date = serializers.DateField()
    tickets = serializers.IntegerField()
    revenue = serializers.FloatField()


class AnalyticsBreakdownSerializer(serializers.Serializer):
    name = serializers.CharField()
    count = serializers.IntegerField()
    revenue = serializers.FloatField()


class EventAnalyticsSerializer(serializers.Serializer):
    currency = serializers.CharField(min_length=3, max_length=3)
    kpis = AnalyticsKpisSerializer()
    timeline = AnalyticsDaySerializer(many=True, help_text='Last 30 days.')
    by_ticket_type = AnalyticsBreakdownSerializer(many=True)
    by_affiliate = AnalyticsBreakdownSerializer(many=True)


class RevenueAmountSerializer(serializers.Serializer):
    currency = serializers.CharField(min_length=3, max_length=3)
    amount = serializers.DecimalField(**MONEY)


class AdminDashboardSerializer(serializers.Serializer):
    total_users = serializers.IntegerField()
    total_events = serializers.IntegerField()
    published_events = serializers.IntegerField()
    total_registrations = serializers.IntegerField()
    confirmed_registrations = serializers.IntegerField()
    revenue_by_currency = RevenueAmountSerializer(many=True)
    top_events = EventListSerializer(many=True)


class AttendeePageSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = AttendeeRegistrationSerializer(many=True)


# ---- Event lifecycle ---- #
class EventStatusResultSerializer(serializers.Serializer):
    message = serializers.CharField()
    status = serializers.ChoiceField(choices=EventStatusChoices.choices)


class EventCancelResultSerializer(EventStatusResultSerializer):
    notified = serializers.IntegerField()
    refunded = serializers.IntegerField()
    refund_failed = serializers.IntegerField()


class SeatMapCreateRequestSerializer(serializers.Serializer):
    rows = serializers.IntegerField(min_value=1, max_value=26, default=6)
    cols = serializers.IntegerField(min_value=1, max_value=30, default=8)
    vip_rows = serializers.IntegerField(min_value=0, default=0)
    premium_rows = serializers.IntegerField(min_value=0, default=0)
    sync_capacity = serializers.BooleanField(default=True, help_text='Set the event capacity to rows × cols.')


class BroadcastRequestSerializer(serializers.Serializer):
    subject = serializers.CharField()
    body = serializers.CharField()
    audience = serializers.CharField(
        default='all',
        help_text='`all`, `confirmed`, `pending`, `checked_in` or `ticket:<ticket type id>`.',
    )


class BroadcastResultSerializer(serializers.Serializer):
    recipients = serializers.IntegerField()
    notified = serializers.IntegerField()
    emailed = serializers.IntegerField()
    email_enabled = serializers.BooleanField(help_text='False when SMTP is not configured.')


# ---- Buying ---- #
class RegisterRequestSerializer(serializers.Serializer):
    ticket_type_id = serializers.IntegerField(required=False, allow_null=True)
    seat_id = serializers.IntegerField(required=False, allow_null=True)
    promo_code = serializers.CharField(required=False, allow_blank=True)
    donation_amount = serializers.DecimalField(
        required=False, allow_null=True, **MONEY, help_text='Pay-what-you-want amount for donation tiers.'
    )
    answers = serializers.DictField(
        child=serializers.JSONField(),
        required=False,
        help_text="Answers to the organizer's questions: question id → answer.",
    )
    affiliate_code = serializers.CharField(required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)


class DynamicPriceSerializer(serializers.Serializer):
    base_price = serializers.DecimalField(**MONEY)
    current_price = serializers.DecimalField(**MONEY)
    multiplier = serializers.FloatField()
    fill_rate = serializers.FloatField(help_text='Percent of capacity taken, 0–100.')
    demand_level = serializers.ChoiceField(choices=DEMAND_LEVELS)
    registered = serializers.IntegerField(required=False)
    capacity = serializers.IntegerField(required=False)


class PromoValidateRequestSerializer(serializers.Serializer):
    code = serializers.CharField()
    ticket_type_id = serializers.IntegerField(required=False, allow_null=True)
    seat_id = serializers.IntegerField(required=False, allow_null=True)


class PromoQuoteSerializer(serializers.Serializer):
    code = serializers.CharField()
    discount_type = serializers.ChoiceField(choices=PromoCode.DISCOUNT_TYPES)
    discount_value = serializers.DecimalField(**MONEY)
    base_price = serializers.DecimalField(**MONEY)
    final_price = serializers.DecimalField(**MONEY)
    savings = serializers.DecimalField(**MONEY)


class RefundRequestCreateSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True)


class RefundRequestCreatedSerializer(serializers.Serializer):
    message = serializers.CharField()
    status = serializers.ChoiceField(choices=RefundRequest.STATUS_CHOICES)


class RefundResolutionRequestSerializer(serializers.Serializer):
    approve = serializers.BooleanField(help_text='true refunds the ticket, false rejects the request.')
    note = serializers.CharField(required=False, allow_blank=True, max_length=300)


class RefundResolutionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=RefundRequest.STATUS_CHOICES)


class QueueStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=QUEUE_STATUSES)
    position = serializers.IntegerField(required=False, help_text='1-based, while queued.')
    total = serializers.IntegerField(required=False)
    wait_minutes = serializers.IntegerField(required=False)
    token = serializers.CharField(required=False, help_text='Admission token, once admitted.')
    expires_in = serializers.IntegerField(required=False, help_text='Seconds the admission stays valid.')
    message = serializers.CharField(required=False)


class WaitlistStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=WAITLIST_STATUSES)
    position = serializers.IntegerField(
        required=False, allow_null=True, help_text='1-based while waiting; 0 once a spot is offered.'
    )
    offer_expires_at = serializers.DateTimeField(required=False)
    message = serializers.CharField(required=False)


# ---- Check-in ---- #
class TicketCheckInResultSerializer(serializers.Serializer):
    message = serializers.CharField()
    status = serializers.ChoiceField(choices=SCAN_RESULTS)
    attendee = serializers.CharField()
    event = serializers.CharField(required=False)
    checked_in_at = serializers.DateTimeField(required=False, allow_null=True)


class TicketRefusedSerializer(serializers.Serializer):
    error = serializers.CharField()
    status = serializers.ChoiceField(choices=SCAN_REFUSALS, required=False)


class CheckInListAttendeeSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    ticket_uuid = serializers.UUIDField()
    username = serializers.CharField()
    full_name = serializers.CharField()
    email = serializers.EmailField()
    status = serializers.ChoiceField(choices=RegistrationStatusChoices.choices)
    is_checked_in = serializers.BooleanField(help_text='On this list.')
    checked_in_at = serializers.DateTimeField(allow_null=True)
    scanned_by = serializers.CharField(allow_null=True)


class CheckInScanRequestSerializer(serializers.Serializer):
    ticket_uuid = serializers.UUIDField()
    action = serializers.ChoiceField(choices=CheckInLog.ACTION_CHOICES, default=CheckInLog.ACTION_CHECK_IN)
    note = serializers.CharField(required=False, allow_blank=True, max_length=200)


class CheckInScanResultSerializer(serializers.Serializer):
    message = serializers.CharField()
    status = serializers.ChoiceField(choices=SCAN_RESULTS)
    attendee = serializers.CharField()
    action = serializers.ChoiceField(choices=CheckInLog.ACTION_CHOICES)
    log_id = serializers.IntegerField(required=False)


# ---- Engagement ---- #
class FavoriteStateSerializer(serializers.Serializer):
    favorited = serializers.BooleanField()


class OkSerializer(serializers.Serializer):
    ok = serializers.BooleanField()


class AffiliateClickRequestSerializer(serializers.Serializer):
    code = serializers.CharField()
