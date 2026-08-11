from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SentEventKey:
    telegram_id: int
    cooldown_minutes: int
    event_uid: str


def find_stale_keys(
    saved_keys: set[SentEventKey],
    observed_keys: set[SentEventKey],
    *,
    scan_complete: bool,
) -> set[SentEventKey]:
    if not scan_complete:
        return set()

    return saved_keys - observed_keys
