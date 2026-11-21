"""Shapes of the organizer dashboard API (docs/ORGANIZER_DASHBOARD.md)."""

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .dashboard import ORDERINGS, SEARCH_MAX_LENGTH, TAB_UPCOMING, TABS, decode_cursor
from .serializers import EventListSerializer

MONEY = {'max_digits': 12, 'decimal_places': 2}
ACTIVITY_TYPES = ['registration', 'group_booking', 'check_in', 'refund']


class OrganizerEventsQuerySerializer(serializers.Serializer):
    """Query string of `GET organizer/events/` (`page` / `page_size` belong to the paginator)."""

    tab = serializers.ChoiceField(choices=TABS, default=TAB_UPCOMING)
    search = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=SEARCH_MAX_LENGTH,
        help_text='Case-insensitive match on title or location.',
    )
    ordering = serializers.ChoiceField(
        choices=ORDERINGS,
        required=False,
        help_text='Default depends on the tab: `date` for upcoming, `-date` for the others.',
    )


class ActivityCursorField(serializers.CharField):
    """An opaque paging cursor; a malformed or tampered one is a field error."""

    def to_internal_value(self, data):
        try:
            return decode_cursor(super().to_internal_value(data))
        except ValueError:
            raise serializers.ValidationError('Invalid cursor.') from None


class ActivityQuerySerializer(serializers.Serializer):
    limit = serializers.IntegerField(min_value=1, max_value=50, default=20)
    cursor = ActivityCursorField(
        required=False,
        help_text='Opaque `next_cursor` of the previous page; returns the items after it. Treat it as a black box.',
    )


class DashboardTabsSerializer(serializers.Serializer):
    upcoming = serializers.IntegerField()
    past = serializers.IntegerField()
    drafts = serializers.IntegerField()
    inactive = serializers.IntegerField()


class DashboardRevenueSerializer(serializers.Serializer):
    currency = serializers.CharField(min_length=3, max_length=3)
    net_revenue = serializers.DecimalField(**MONEY)


class DashboardSummarySerializer(serializers.Serializer):
    tabs = DashboardTabsSerializer(help_text='Number of managed events in each tab.')
    pending_approval = serializers.IntegerField(
        help_text='Events waiting for admin review that can still be published.'
    )
    upcoming_next_7_days = serializers.IntegerField(help_text='Upcoming-tab events that start within 7 days.')
    tickets_sold = serializers.IntegerField()
    checked_in = serializers.IntegerField()
    checkin_rate_pct = serializers.FloatField(help_text='Percent, one decimal; 0 when nothing is sold.')
    revenue = DashboardRevenueSerializer(
        many=True, help_text='Net revenue per currency, never summed across currencies.'
    )
    sales_last_7_days = serializers.IntegerField(help_text='Tickets confirmed in [now-7d, now).')
    sales_previous_7_days = serializers.IntegerField(help_text='Tickets confirmed in [now-14d, now-7d).')


class OrganizerEventStatsSerializer(serializers.Serializer):
    tickets_sold = serializers.IntegerField()
    checked_in = serializers.IntegerField()
    checkin_rate_pct = serializers.FloatField()
    capacity = serializers.IntegerField()
    sold_through_pct = serializers.FloatField(help_text='Not clamped: an overbooked event is above 100.')
    pending = serializers.IntegerField()
    net_revenue = serializers.DecimalField(**MONEY)
    currency = serializers.CharField(min_length=3, max_length=3)


class OrganizerEventSerializer(EventListSerializer):
    """An event of the dashboard list: the public list payload plus the
    caller's relation to it and its sales numbers (`context['stats']` maps
    event id to `dashboard.bulk_event_stats`)."""

    is_owner = serializers.SerializerMethodField()
    stats = serializers.SerializerMethodField()

    class Meta(EventListSerializer.Meta):
        fields = [*EventListSerializer.Meta.fields, 'is_owner', 'stats']

    def get_online_link(self, obj) -> str:
        # Everything in this list is managed by the caller, who may see the link.
        return obj.online_link

    def get_is_owner(self, obj) -> bool:
        return obj.organizer_id == self.context['request'].user.id

    @extend_schema_field(OrganizerEventStatsSerializer)
    def get_stats(self, obj):
        return self.context['stats'][obj.pk]


class OrganizerEventPageSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = OrganizerEventSerializer(many=True)


class ActivityItemSerializer(serializers.Serializer):
    id = serializers.CharField(help_text='Stable id, e.g. `registration:812`.')
    type = serializers.ChoiceField(choices=ACTIVITY_TYPES)
    occurred_at = serializers.DateTimeField()
    event_id = serializers.IntegerField()
    event_title = serializers.CharField()
    attendee_name = serializers.CharField(help_text='Never an email address.')
    quantity = serializers.IntegerField(help_text='Seats for a group booking, otherwise 1.')
    amount = serializers.DecimalField(**MONEY, allow_null=True, help_text='Refunds only.')
    currency = serializers.CharField(allow_null=True, help_text='Refunds only.')


class ActivityFeedSerializer(serializers.Serializer):
    results = ActivityItemSerializer(many=True)
    next_cursor = serializers.CharField(
        allow_null=True, help_text='Pass as `cursor` to load the next page; null when there is nothing older.'
    )


class CloneEventRequestSerializer(serializers.Serializer):
    title = serializers.CharField(
        required=False,
        min_length=1,
        max_length=200,
        help_text='Title of the copy (trimmed). Default: the original title plus " (Copy)".',
    )
