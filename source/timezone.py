"""Resolve application timezones from IANA timezone identifiers."""

from dataclasses import dataclass
from datetime import UTC, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True, slots=True)
class TimezoneSettings:
    """Timezone values supplied by Nextcloud and the user."""

    nextcloud_tzid: str | None = None
    override_tzid: str | None = None


def normalize_tzid(value: object) -> str | None:
    """Return a trimmed IANA identifier or None for invalid input."""

    if not isinstance(value, str):
        return None

    tzid = value.strip()
    if not tzid:
        return None

    try:
        ZoneInfo(tzid)
    except (OSError, ValueError, ZoneInfoNotFoundError):
        return None

    return tzid


def _load_timezone(value: object) -> ZoneInfo | None:
    normalized = normalize_tzid(value)
    return ZoneInfo(normalized) if normalized is not None else None


def resolve_effective_timezone(
    settings: TimezoneSettings,
    *,
    default_tzid: str,
) -> tzinfo:
    """Resolve override, Nextcloud, default, then UTC in that order."""

    candidates = (
        settings.override_tzid,
        settings.nextcloud_tzid,
        default_tzid,
    )
    for candidate in candidates:
        resolved = _load_timezone(candidate)
        if resolved is not None:
            return resolved

    return UTC
