from types import SimpleNamespace
from typing import NoReturn

import pytest

from source import app


class _StopRun(BaseException):
    pass


class _WorkerThread:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    def start(self) -> None:
        self._events.append("worker")


def test_migrations_finish_before_background_workers_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    monkeypatch.setattr(app, "init_db", lambda: events.append("init"))
    monkeypatch.setattr(
        app,
        "auto_migrate",
        lambda: events.append("migrate"),
    )
    monkeypatch.setattr(app, "is_debug", lambda: False)
    monkeypatch.setattr(app, "_notify_startup", lambda: None)
    monkeypatch.setattr(app, "CALDAV_PASSWORD", None)
    monkeypatch.setattr(app, "CALDAV_USERNAME", None)
    monkeypatch.setattr(
        app.threading,
        "Thread",
        lambda **_kwargs: _WorkerThread(events),
    )
    monkeypatch.setattr(
        app.bot,
        "remove_webhook",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        app.bot,
        "get_me",
        lambda: SimpleNamespace(username="test", id=1),
    )

    def stop_polling(**_kwargs: object) -> NoReturn:
        events.append("polling")
        raise _StopRun

    monkeypatch.setattr(app.bot, "infinity_polling", stop_polling)

    with pytest.raises(_StopRun):
        app.run()

    assert events[:2] == ["init", "migrate"]
    assert events.count("worker") == 3
    assert events[-1] == "polling"
