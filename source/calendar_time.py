"""RFC 5545 localization helpers for iCalendar temporal values."""

from datetime import UTC, date, datetime, time, timedelta, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class UnknownSourceTimezoneError(ValueError):
    """Raised when an iCalendar property declares an unknown TZID."""

    def __init__(self, tzid: str) -> None:
        self.tzid = tzid
        super().__init__(f"Unknown iCalendar source timezone: {tzid}")


def localize_ical_value(
    value: datetime | date,
    *,
    target_timezone: tzinfo,
    source_tzid: str | None,
) -> datetime | date:
    """Localize one iCalendar DATE or DATE-TIME without guessing."""
    if not isinstance(value, datetime):
        return value

    if value.tzinfo is not None:
        return value.astimezone(UTC).astimezone(target_timezone)

    if source_tzid is None:
        return value.replace(tzinfo=target_timezone, fold=0)

    try:
        source_timezone = ZoneInfo(source_tzid)
    except (OSError, ValueError, ZoneInfoNotFoundError) as error:
        raise UnknownSourceTimezoneError(source_tzid) from error

    source_value = value.replace(tzinfo=source_timezone, fold=0)
    return source_value.astimezone(UTC).astimezone(target_timezone)


def local_day_window(
    now_utc: datetime,
    target_timezone: tzinfo,
) -> tuple[datetime, datetime]:
    """Return recipient-local midnight bounds for the current day."""
    local_date = now_utc.astimezone(target_timezone).date()
    start = datetime.combine(local_date, time.min, target_timezone)
    end = datetime.combine(
        local_date + timedelta(days=1),
        time.min,
        target_timezone,
    )
    return start, end


def local_week_window(
    now_utc: datetime,
    target_timezone: tzinfo,
) -> tuple[datetime, datetime]:
    """Return seven recipient-local calendar days."""
    local_date = now_utc.astimezone(target_timezone).date()
    start = datetime.combine(local_date, time.min, target_timezone)
    end_date = local_date + timedelta(days=7)
    end = datetime.combine(end_date, time.min, target_timezone)
    return start, end
