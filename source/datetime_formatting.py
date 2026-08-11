"""Timezone-safe formatting for calendar and task datetimes."""

from datetime import UTC, datetime, tzinfo


def format_datetime(
    value: datetime,
    target_timezone: tzinfo,
    *,
    date_format: str,
) -> str:
    """Format an instant in a timezone, treating naive input as UTC."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)

    if not isinstance(target_timezone, tzinfo):
        target_timezone = UTC

    return value.astimezone(target_timezone).strftime(date_format)


def format_calendar_time(value: datetime, target_timezone: tzinfo) -> str:
    """Format a CalDAV datetime as local hours and minutes."""
    return format_datetime(
        value,
        target_timezone,
        date_format="%H:%M",
    )


def format_task_due_date(value: datetime, target_timezone: tzinfo) -> str:
    """Format a Deck due instant in a user's local timezone."""
    return format_datetime(
        value,
        target_timezone,
        date_format="%y-%m-%d %H:%M",
    )
