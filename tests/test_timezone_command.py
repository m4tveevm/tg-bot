import pytest

from source.timezone_command import (
    InvalidTimezoneInput,
    apply_timezone_argument,
)


def test_timezone_command_sets_valid_override() -> None:
    saved: list[str] = []

    result = apply_timezone_argument(
        " Europe/Warsaw ",
        save_override=saved.append,
        clear_override=lambda: None,
    )

    assert saved == ["Europe/Warsaw"]
    assert "Europe/Warsaw" in result


def test_timezone_auto_clears_override() -> None:
    cleared: list[bool] = []

    result = apply_timezone_argument(
        "AUTO",
        save_override=lambda value: None,
        clear_override=lambda: cleared.append(True),
    )

    assert cleared == [True]
    assert "Nextcloud" in result


def test_timezone_command_rejects_integer_offset() -> None:
    with pytest.raises(InvalidTimezoneInput):
        apply_timezone_argument(
            "+3",
            save_override=lambda value: None,
            clear_override=lambda: None,
        )


def test_timezone_command_rejects_unknown_zone() -> None:
    with pytest.raises(InvalidTimezoneInput):
        apply_timezone_argument(
            "Mars/Olympus",
            save_override=lambda value: None,
            clear_override=lambda: None,
        )


def test_timezone_command_does_not_report_success_after_repository_error() -> (
    None
):
    def fail(_value: str) -> None:
        raise RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="database unavailable"):
        apply_timezone_argument(
            "Europe/Warsaw",
            save_override=fail,
            clear_override=lambda: None,
        )


def test_timezone_command_never_writes_to_nextcloud() -> None:
    local_writes: list[str] = []
    nextcloud_writes: list[str] = []

    apply_timezone_argument(
        "Europe/Moscow",
        save_override=local_writes.append,
        clear_override=lambda: None,
    )

    assert local_writes == ["Europe/Moscow"]
    assert nextcloud_writes == []
