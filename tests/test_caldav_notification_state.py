from source.caldav_notification_state import SentEventKey, find_stale_keys


def test_find_stale_keys_returns_unobserved_keys() -> None:
    stale_key = SentEventKey(
        telegram_id=101,
        cooldown_minutes=60,
        event_uid="team_sync_2026_instance",
    )
    observed_key = SentEventKey(
        telegram_id=202,
        cooldown_minutes=60,
        event_uid="team_sync_2026_instance",
    )

    result = find_stale_keys(
        {stale_key, observed_key},
        {observed_key},
        scan_complete=True,
    )

    assert result == {stale_key}


def test_find_stale_keys_preserves_state_after_incomplete_scan() -> None:
    saved_key = SentEventKey(
        telegram_id=101,
        cooldown_minutes=60,
        event_uid="team_sync_2026_instance",
    )

    result = find_stale_keys(
        {saved_key},
        set(),
        scan_complete=False,
    )

    assert result == set()
