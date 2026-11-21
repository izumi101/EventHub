"""The platform's business day (docs/ORGANIZER_DASHBOARD_PHASE2.md, "Time zone").

Every "per day" number of the organizer dashboard and of the per-event
analytics is bucketed in `settings.NOTIFICATION_TIME_ZONE` (falling back to
`TIME_ZONE`), the zone the organizers and attendees live in, never in UTC.
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db.models.functions import TruncDate
from django.utils import timezone

from notifications.messages import notification_time_zone


def business_tz() -> ZoneInfo:
    return ZoneInfo(notification_time_zone())


def local_date(value: datetime, tz: ZoneInfo | None = None) -> date:
    """The calendar day of the instant `value` in the business time zone."""
    return timezone.localtime(value, tz or business_tz()).date()


def local_today(now: datetime | None = None, tz: ZoneInfo | None = None) -> date:
    return local_date(now or timezone.now(), tz)


def day_start(day: date, tz: ZoneInfo | None = None) -> datetime:
    """Midnight at the start of `day` in the business time zone (aware)."""
    return datetime.combine(day, time.min).replace(tzinfo=tz or business_tz())


def window_bounds(start: date, end: date, tz: ZoneInfo | None = None) -> tuple[datetime, datetime]:
    """[lower, upper) instants covering the days `start`..`end` inclusive."""
    tz = tz or business_tz()
    return day_start(start, tz), day_start(end + timedelta(days=1), tz)


def days_between(start: date, end: date) -> list[date]:
    """Every date of `start`..`end` inclusive, in order."""
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def trunc_day(field: str, tz: ZoneInfo | None = None) -> TruncDate:
    """DB-side bucketing of a datetime column into business-time-zone days."""
    return TruncDate(field, tzinfo=tz or business_tz())
