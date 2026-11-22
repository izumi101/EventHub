"""Shapes of the organizer dashboard API (docs/ORGANIZER_DASHBOARD.md)."""

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from common.choices import EventStatusChoices

from .dashboard import ORDERINGS, SEARCH_MAX_LENGTH, TAB_UPCOMING, TABS, decode_cursor
from .sales_chart import DEFAULT_RANGE, RANGES
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


class SalesQuerySerializer(serializers.Serializer):
    range = serializers.ChoiceField(
        choices=list(RANGES),
        default=DEFAULT_RANGE,
        help_text='Window ending today (business time zone): the last 7, 30 or 90 days, today included.',
    )


class SalesDaySerializer(serializers.Serializer):
    date = serializers.DateField()
    tickets = serializers.IntegerField(
        help_text='Confirmed registrations plus seats of confirmed group bookings, on the day they were made.'
    )


class SalesRevenueDaySerializer(serializers.Serializer):
    date = serializers.DateField()
    net_revenue = serializers.DecimalField(
        **MONEY, help_text='Payments of the day minus refunds of the day; negative when refunds exceed sales.'
    )


class SalesRevenueSeriesSerializer(serializers.Serializer):
    currency = serializers.CharField(min_length=3, max_length=3)
    days = SalesRevenueDaySerializer(many=True, help_text='Every day of the range, zero-filled.')


class SalesMarkerSerializer(serializers.Serializer):
    date = serializers.DateField(help_text='Business-time-zone day the event was published.')
    event_id = serializers.IntegerField()
    title = serializers.CharField()
    kind = serializers.ChoiceField(choices=['published'])


class SalesSerializer(serializers.Serializer):
    time_zone = serializers.CharField(help_text='IANA name of the zone the days are bucketed in.')
    start = serializers.DateField(help_text='First day of the range.')
    end = serializers.DateField(help_text='Last day of the range: today in `time_zone`.')
    days = SalesDaySerializer(many=True, help_text='Every day of [start, end], zero-filled.')
    revenue = SalesRevenueSeriesSerializer(
        many=True,
        help_text='One series per currency with money movement in the range; never summed across currencies.',
    )
    markers = SalesMarkerSerializer(
        many=True,
        help_text='Events published in the range. Empty until `Event.published_at` exists (moderation batch).',
    )


class TodayStatsSerializer(serializers.Serializer):
    tickets_sold = serializers.IntegerField()
    checked_in = serializers.IntegerField()
    capacity = serializers.IntegerField()


class TodayEventSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    date = serializers.DateTimeField()
    end_date = serializers.DateTimeField(allow_null=True)
    location = serializers.CharField()
    status = serializers.ChoiceField(choices=EventStatusChoices.choices)
    is_owner = serializers.BooleanField()
    in_progress = serializers.BooleanField(help_text='Started and not yet over (the end is `end_date`, else `date`).')
    stats = TodayStatsSerializer()


class TodaySerializer(serializers.Serializer):
    results = TodayEventSerializer(many=True, help_text='At most 10, by start.')
    more = serializers.IntegerField(help_text='How many further events there are beyond `results`.')


# Reviews per star rating. The keys are the digits 1-5, which are not valid
# attribute names, so the class is built from them.
ReviewDistributionSerializer = type(
    'ReviewDistributionSerializer',
    (serializers.Serializer,),
    {
        '__doc__': 'Reviews per star rating; all five keys are always present.',
        **{stars: serializers.IntegerField() for stars in '12345'},
    },
)


class RecentReviewSerializer(serializers.Serializer):
    event_id = serializers.IntegerField()
    event_title = serializers.CharField()
    rating = serializers.IntegerField(min_value=1, max_value=5)
    comment = serializers.CharField(allow_blank=True)
    created_at = serializers.DateTimeField()
    author = serializers.CharField(help_text='Name of the reviewer; never an email address.')


class ReviewsSummarySerializer(serializers.Serializer):
    count = serializers.IntegerField()
    average = serializers.FloatField(allow_null=True, help_text='Two decimals; null when there are no reviews.')
    distribution = ReviewDistributionSerializer()
    recent = RecentReviewSerializer(many=True, help_text='The 5 latest reviews.')
