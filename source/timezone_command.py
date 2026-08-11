"""Application logic for the Telegram /timezone command."""

from collections.abc import Callable

from source.timezone import normalize_tzid

TIMEZONE_HELP = (
    "Формат: /timezone <IANA timezone|auto>\n"
    "Примеры: /timezone Europe/Warsaw, "
    "/timezone Europe/Moscow, /timezone auto"
)


class InvalidTimezoneInput(ValueError):
    """Raised when a command argument is not a valid IANA timezone."""


def apply_timezone_argument(
    argument: str,
    *,
    save_override: Callable[[str], None],
    clear_override: Callable[[], None],
) -> str:
    """Apply a validated command argument through local DB callbacks."""
    value = argument.strip()
    if value.casefold() == "auto":
        clear_override()
        return "Автоматическая timezone из Nextcloud снова включена."

    tzid = normalize_tzid(value)
    if tzid is None:
        raise InvalidTimezoneInput(value)

    save_override(tzid)
    return f"Timezone изменена на {tzid}."
