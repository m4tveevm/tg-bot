from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from source.timezone import (
    TimezoneSettings,
    normalize_tzid,
    resolve_effective_timezone,
)


def test_timezone_settings_are_frozen_and_slotted() -> None:
    settings = TimezoneSettings(
        nextcloud_tzid="Europe/Berlin",
        override_tzid=None,
    )

    with pytest.raises(FrozenInstanceError):
        settings.override_tzid = "UTC"  # type: ignore[misc]

    assert not hasattr(settings, "__dict__")


def test_normalize_tzid_trims_valid_iana_identifier() -> None:
    assert normalize_tzid("  Europe/Berlin  ") == "Europe/Berlin"


def test_normalize_tzid_rejects_empty_value() -> None:
    assert normalize_tzid("") is None
    assert normalize_tzid("  \t\n") is None


def test_normalize_tzid_rejects_non_string() -> None:
    assert normalize_tzid(None) is None
    assert normalize_tzid(3) is None
    assert normalize_tzid(object()) is None


def test_normalize_tzid_rejects_unknown_identifier() -> None:
    assert normalize_tzid("Mars/Olympus_Mons") is None


def test_normalize_tzid_rejects_invalid_zoneinfo_key() -> None:
    assert normalize_tzid("../Europe/Warsaw") is None
    assert normalize_tzid("A" * 256) is None


def test_override_has_highest_priority() -> None:
    settings = TimezoneSettings(
        nextcloud_tzid="Europe/Berlin",
        override_tzid="Asia/Kolkata",
    )

    resolved = resolve_effective_timezone(
        settings,
        default_tzid="Europe/Moscow",
    )

    assert isinstance(resolved, ZoneInfo)
    assert resolved.key == "Asia/Kolkata"


def test_invalid_override_does_not_block_nextcloud_timezone() -> None:
    settings = TimezoneSettings(
        nextcloud_tzid="Europe/Berlin",
        override_tzid="Invalid/Override",
    )

    resolved = resolve_effective_timezone(
        settings,
        default_tzid="Europe/Moscow",
    )

    assert isinstance(resolved, ZoneInfo)
    assert resolved.key == "Europe/Berlin"


def test_default_is_used_when_user_timezones_are_unavailable() -> None:
    settings = TimezoneSettings(
        nextcloud_tzid="Invalid/Nextcloud",
        override_tzid=None,
    )

    resolved = resolve_effective_timezone(
        settings,
        default_tzid="Europe/Moscow",
    )

    assert isinstance(resolved, ZoneInfo)
    assert resolved.key == "Europe/Moscow"


def test_utc_is_used_when_all_configured_timezones_are_invalid() -> None:
    settings = TimezoneSettings(
        nextcloud_tzid="Invalid/Nextcloud",
        override_tzid="Invalid/Override",
    )

    resolved = resolve_effective_timezone(
        settings,
        default_tzid="Invalid/Default",
    )

    assert resolved is UTC


def test_european_timezone_observes_dst() -> None:
    resolved = resolve_effective_timezone(
        TimezoneSettings(nextcloud_tzid="Europe/Berlin"),
        default_tzid="UTC",
    )

    winter = datetime(2026, 1, 15, tzinfo=UTC)
    summer = datetime(2026, 7, 15, tzinfo=UTC)

    assert winter.astimezone(resolved).utcoffset() == timedelta(hours=1)
    assert summer.astimezone(resolved).utcoffset() == timedelta(hours=2)


def test_asia_kolkata_keeps_half_hour_offset() -> None:
    resolved = resolve_effective_timezone(
        TimezoneSettings(override_tzid="Asia/Kolkata"),
        default_tzid="UTC",
    )
    instant = datetime(2026, 1, 15, tzinfo=UTC)

    assert instant.astimezone(resolved).utcoffset() == timedelta(
        hours=5,
        minutes=30,
    )
