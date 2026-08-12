from datetime import UTC, date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from source.calendar_time import (
    UnknownSourceTimezoneError,
    local_day_window,
    local_week_window,
    localize_ical_value,
)


def test_utc_event_is_converted_to_recipient_timezone() -> None:
    result = localize_ical_value(
        datetime(2026, 8, 10, 22, 30, tzinfo=UTC),
        target_timezone=ZoneInfo("Europe/Warsaw"),
        source_tzid=None,
    )

    assert result.isoformat() == "2026-08-11T00:30:00+02:00"


def test_offset_event_preserves_absolute_instant() -> None:
    source = datetime(
        2026,
        1,
        15,
        8,
        tzinfo=timezone(timedelta(hours=-5)),
    )

    result = localize_ical_value(
        source,
        target_timezone=ZoneInfo("Asia/Kolkata"),
        source_tzid="Europe/Warsaw",
    )

    assert result.astimezone(UTC) == source.astimezone(UTC)
    assert result.isoformat() == "2026-01-15T18:30:00+05:30"


def test_aware_event_is_not_reinterpreted_from_tzid() -> None:
    source = datetime(2026, 8, 10, 22, 30, tzinfo=UTC)

    result = localize_ical_value(
        source,
        target_timezone=ZoneInfo("Europe/Warsaw"),
        source_tzid="Asia/Kolkata",
    )

    assert result.astimezone(UTC) == source


def test_tzid_event_preserves_absolute_instant() -> None:
    result = localize_ical_value(
        datetime(2026, 7, 15, 9),
        target_timezone=ZoneInfo("Europe/Moscow"),
        source_tzid="Europe/Warsaw",
    )

    assert result.isoformat() == "2026-07-15T10:00:00+03:00"
    assert result.astimezone(UTC).hour == 7


def test_floating_event_uses_recipient_wall_time() -> None:
    result = localize_ical_value(
        datetime(2026, 10, 25, 9),
        target_timezone=ZoneInfo("Europe/Warsaw"),
        source_tzid=None,
    )

    assert result.isoformat() == "2026-10-25T09:00:00+01:00"


def test_floating_event_is_not_treated_as_utc() -> None:
    source = datetime(2026, 10, 25, 9)
    warsaw = localize_ical_value(
        source,
        target_timezone=ZoneInfo("Europe/Warsaw"),
        source_tzid=None,
    )
    moscow = localize_ical_value(
        source,
        target_timezone=ZoneInfo("Europe/Moscow"),
        source_tzid=None,
    )

    assert warsaw.hour == moscow.hour == 9
    assert warsaw.astimezone(UTC) != moscow.astimezone(UTC)


def test_all_day_event_remains_date() -> None:
    source = date(2026, 8, 11)

    result = localize_ical_value(
        source,
        target_timezone=ZoneInfo("Europe/Warsaw"),
        source_tzid="Unknown/Still-Ignored-For-Date",
    )

    assert result is source


def test_unknown_tzid_does_not_fall_back_to_utc() -> None:
    with pytest.raises(UnknownSourceTimezoneError) as error:
        localize_ical_value(
            datetime(2026, 8, 11, 9),
            target_timezone=ZoneInfo("Europe/Warsaw"),
            source_tzid="Unknown/Nowhere",
        )

    assert error.value.tzid == "Unknown/Nowhere"


def test_warsaw_winter_and_summer_offsets_are_different() -> None:
    winter = localize_ical_value(
        datetime(2026, 1, 15, 9),
        target_timezone=ZoneInfo("Europe/Warsaw"),
        source_tzid="Europe/Warsaw",
    )
    summer = localize_ical_value(
        datetime(2026, 7, 15, 9),
        target_timezone=ZoneInfo("Europe/Warsaw"),
        source_tzid="Europe/Warsaw",
    )

    assert winter.utcoffset() == timedelta(hours=1)
    assert summer.utcoffset() == timedelta(hours=2)


def test_dst_overlap_uses_first_occurrence() -> None:
    result = localize_ical_value(
        datetime(2026, 10, 25, 2, 30),
        target_timezone=ZoneInfo("Europe/Warsaw"),
        source_tzid="Europe/Warsaw",
    )

    assert result.fold == 0
    assert result.utcoffset() == timedelta(hours=2)
    assert result.astimezone(UTC).isoformat() == "2026-10-25T00:30:00+00:00"


def test_dst_gap_uses_pre_gap_offset() -> None:
    result = localize_ical_value(
        datetime(2026, 3, 29, 2, 30),
        target_timezone=ZoneInfo("Europe/Warsaw"),
        source_tzid="Europe/Warsaw",
    )

    assert result.isoformat() == "2026-03-29T03:30:00+02:00"
    assert result.astimezone(UTC).isoformat() == "2026-03-29T01:30:00+00:00"


def test_local_day_window_uses_dst_safe_midnights() -> None:
    start, end = local_day_window(
        datetime(2026, 3, 29, 10, tzinfo=UTC),
        ZoneInfo("Europe/Warsaw"),
    )

    assert start.isoformat() == "2026-03-29T00:00:00+01:00"
    assert end.isoformat() == "2026-03-30T00:00:00+02:00"
    assert end.astimezone(UTC) - start.astimezone(UTC) == timedelta(hours=23)


def test_local_week_window_keeps_local_midnight_across_dst() -> None:
    start, end = local_week_window(
        datetime(2026, 10, 22, 10, tzinfo=UTC),
        ZoneInfo("Europe/Warsaw"),
    )

    assert start.isoformat() == "2026-10-22T00:00:00+02:00"
    assert end.isoformat() == "2026-10-29T00:00:00+01:00"
    assert end.astimezone(UTC) - start.astimezone(UTC) == timedelta(hours=169)
