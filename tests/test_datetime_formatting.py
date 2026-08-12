from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from source.datetime_formatting import (
    format_calendar_time,
    format_task_due_date,
)
from source.scheduler import _format_changes_for_timezone
from source.timezone import TimezoneSettings, resolve_effective_timezone


def test_aware_calendar_datetime_uses_effective_timezone() -> None:
    instant = datetime(2026, 7, 15, 12, tzinfo=UTC)

    assert (
        format_calendar_time(
            instant,
            ZoneInfo("Europe/Warsaw"),
        )
        == "14:00"
    )


def test_task_due_date_uses_effective_timezone() -> None:
    instant = datetime(2026, 1, 15, 12, tzinfo=UTC)

    assert (
        format_task_due_date(
            instant,
            ZoneInfo("Asia/Kolkata"),
        )
        == "26-01-15 17:30"
    )


def test_task_utc_naive_datetime_remains_an_absolute_utc_instant() -> None:
    utc_naive = datetime(2026, 1, 15, 12)

    assert (
        format_task_due_date(
            utc_naive,
            ZoneInfo("Asia/Kolkata"),
        )
        == "26-01-15 17:30"
    )


def test_invalid_stored_timezone_does_not_raise_type_error() -> None:
    resolved = resolve_effective_timezone(
        TimezoneSettings(
            nextcloud_tzid="Invalid/Timezone",
            override_tzid="Also/Invalid",
        ),
        default_tzid="Invalid/Default",
    )

    assert (
        format_calendar_time(
            datetime(2026, 1, 15, 12, tzinfo=UTC),
            resolved,
        )
        == "12:00"
    )


def test_task_change_formatting_is_per_recipient() -> None:
    old_due = datetime(2026, 1, 15, 12)
    new_due = datetime(2026, 1, 15, 13)
    changes = [[old_due, new_due]]

    warsaw = _format_changes_for_timezone(
        changes,
        ZoneInfo("Europe/Warsaw"),
    )
    kolkata = _format_changes_for_timezone(
        changes,
        ZoneInfo("Asia/Kolkata"),
    )

    assert warsaw == ["Due: `26-01-15 13:00` → `26-01-15 14:00`"]
    assert kolkata == ["Due: `26-01-15 17:30` → `26-01-15 18:30`"]
    assert changes == [[old_due, new_due]]
