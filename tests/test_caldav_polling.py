import ast
import importlib
import inspect
import sys
import textwrap
from datetime import timedelta, timezone
from types import ModuleType
from unittest.mock import Mock

import pytest

from source.caldav_notification_state import SentEventKey
from tests.caldav_fakes import (
    FakeAttendee,
    FakeCalendar,
    FakeCalendarParser,
    FakeClient,
    FakeComponent,
    FakeEvent,
    FakeICalendar,
    FakeInlineKeyboardButton,
    FakeInlineKeyboardMarkup,
    FakeLogger,
    FakePrincipal,
    FrozenDateTime,
    InMemoryNotificationState,
    StopPolling,
    make_poll_event,
)

EVENT_UID = "team_sync_2026"
USER_EMAIL = "user@example.com"
USER_ID = 101
COOLDOWN = 60


def _module(name: str, **attributes: object) -> ModuleType:
    module = ModuleType(name)
    for attribute, value in attributes.items():
        setattr(module, attribute, value)
    return module


def _empty_keys() -> set[SentEventKey]:
    return set()


def _ignore(*_args: object, **_kwargs: object) -> None:
    pass


@pytest.fixture
def nc_calendar(monkeypatch: pytest.MonkeyPatch):
    config = _module(
        "source.config",
        WEB_CALDAV_URL="https://calendar.test/caldav",
        USERNAME="nextcloud-user",
        PASSWORD="nextcloud-password",
        COOLDOWN_TUESDAY=2,
        COOLDOWN_SUNDAY=10,
        COOLDOWN_DEFAULT=2,
        POLL_INTERVAL=60,
        WEB_APP_URL="https://nextcloud.test",
        UPDATE_INTERVAL=1,
        TIMEZONE="Europe/Moscow",
        CALDAV_USERNAME="caldav-user",
        CALDAV_PASSWORD="caldav-password",
        CALDAV_COOLDOWNS={"Team": [COOLDOWN]},
        TIMEZONES={3: timezone(timedelta(hours=3))},
    )
    sender = _module(
        "source.connections.sender",
        send_message_limited=_ignore,
    )
    users = _module(
        "source.db.repos.users",
        get_tg_id_by_email=lambda _email: None,
        save_email_by_username=_ignore,
        get_timezone=lambda _telegram_id: 3,
    )
    repository = _module(
        "source.db.repos.caldav_calendar",
        delete_sent_event=_ignore,
        get_sent_event_keys=_empty_keys,
        save_event_send=_ignore,
    )
    app_logging = _module("source.app_logging", logger=FakeLogger())
    telebot_types = _module(
        "telebot.types",
        InlineKeyboardMarkup=FakeInlineKeyboardMarkup,
        InlineKeyboardButton=FakeInlineKeyboardButton,
    )
    telebot = _module("telebot", types=telebot_types)
    caldav = _module("caldav", DAVClient=None, error=Exception)
    icalendar = _module(
        "icalendar",
        Calendar=FakeCalendarParser,
        vText=lambda value: value,
    )

    modules = {
        "source.config": config,
        "source.connections.sender": sender,
        "source.db.repos.users": users,
        "source.db.repos.caldav_calendar": repository,
        "source.app_logging": app_logging,
        "telebot": telebot,
        "telebot.types": telebot_types,
        "caldav": caldav,
        "icalendar": icalendar,
        "requests": ModuleType("requests"),
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)

    monkeypatch.delitem(sys.modules, "source.nc_calendar", raising=False)
    module = importlib.import_module("source.nc_calendar")
    yield module
    sys.modules.pop("source.nc_calendar", None)


def _key(
    telegram_id: int = USER_ID,
    cooldown: int = COOLDOWN,
    event_uid: str = EVENT_UID,
) -> SentEventKey:
    return SentEventKey(
        telegram_id=telegram_id,
        cooldown_minutes=cooldown,
        event_uid=event_uid,
    )


def _participant(
    email: str = USER_EMAIL,
    *,
    status: str = "NEEDS-ACTION",
) -> dict[str, object]:
    return {
        "email": email,
        "name": email.split("@", maxsplit=1)[0],
        "role": "ATTENDEE",
        "status": status,
    }


def _run_poll_cycle(
    nc_calendar: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    *,
    state: InMemoryNotificationState,
    calendars: list[FakeCalendar],
    now: FrozenDateTime,
    identities: dict[str, int] | None = None,
    cooldowns: list[int] | None = None,
    sender: Mock | None = None,
    mutator: Mock | None = None,
    timezone_getter: Mock | None = None,
) -> tuple[Mock, Mock]:
    FrozenDateTime.current = now
    principal = FakePrincipal(calendars)
    sender = sender or Mock()
    mutator = mutator or Mock()
    timezone_getter = timezone_getter or Mock(return_value=3)

    def stop_polling(_seconds: int) -> None:
        raise StopPolling

    monkeypatch.setattr(nc_calendar, "datetime", FrozenDateTime)
    monkeypatch.setattr(
        nc_calendar,
        "DAVClient",
        lambda *_args, **_kwargs: FakeClient(principal),
    )
    monkeypatch.setattr(nc_calendar, "get_sent_event_keys", state.load)
    monkeypatch.setattr(nc_calendar, "save_event_send", state.save)
    monkeypatch.setattr(nc_calendar, "delete_sent_event", state.delete)
    monkeypatch.setattr(
        nc_calendar,
        "get_tg_id_by_email",
        (identities or {}).get,
    )
    monkeypatch.setattr(nc_calendar, "get_timezone", timezone_getter)
    monkeypatch.setattr(
        nc_calendar,
        "format_to_timezone",
        lambda _value, tz: "19:00",
    )
    monkeypatch.setattr(
        nc_calendar,
        "get_all_participants",
        lambda component: component.participants,
    )
    monkeypatch.setattr(nc_calendar, "send_message_limited", sender)
    monkeypatch.setattr(nc_calendar, "sleep", stop_polling)
    monkeypatch.setattr(
        nc_calendar,
        "CALDAV_COOLDOWNS",
        {"Team": cooldowns or [COOLDOWN]},
    )
    monkeypatch.setattr(
        nc_calendar,
        "set_all_attendees_needs_action",
        mutator,
        raising=False,
    )

    with pytest.raises(StopPolling):
        nc_calendar.poll_events()

    return sender, mutator


def _weekly_event(
    now: FrozenDateTime,
    *,
    event_uid: str = EVENT_UID,
    email: str = USER_EMAIL,
) -> FakeEvent:
    return make_poll_event(
        event_uid=event_uid,
        summary="Team sync",
        start=now + timedelta(minutes=30),
        end=now + timedelta(minutes=90),
        participants=[_participant(email)],
    )


def test_stale_cleanup_does_not_mutate_caldav(
    nc_calendar: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = InMemoryNotificationState({_key()})
    now = FrozenDateTime(
        2026,
        8,
        6,
        18,
        tzinfo=nc_calendar.TEAM_TZ,
    )
    attendee = FakeAttendee(USER_EMAIL)
    original_params = {
        name: list(values) for name, values in attendee.params.items()
    }
    unrelated_event = make_poll_event(
        event_uid="unrelated-event",
        summary="Other event",
        start=now + timedelta(minutes=30),
        end=now + timedelta(minutes=90),
        participants=[],
        ical_attendees=attendee,
    )
    calendar = FakeCalendar([unrelated_event])
    mutator = Mock()

    _run_poll_cycle(
        nc_calendar,
        monkeypatch,
        state=state,
        calendars=[calendar],
        now=now,
        mutator=mutator,
    )

    assert state.deleted == [_key()]
    mutator.assert_not_called()
    unrelated_event.save.assert_not_called()
    assert attendee.params == original_params
    assert calendar.expand_calls == [False]


def test_stale_notification_is_deleted_from_local_state(
    nc_calendar: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = _key()
    state = InMemoryNotificationState({key})
    now = FrozenDateTime(
        2026,
        8,
        6,
        18,
        tzinfo=nc_calendar.TEAM_TZ,
    )

    _run_poll_cycle(
        nc_calendar,
        monkeypatch,
        state=state,
        calendars=[FakeCalendar()],
        now=now,
    )

    assert state.keys == set()
    assert state.deleted == [key]


def test_observed_notification_is_not_deleted(
    nc_calendar: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = _key()
    state = InMemoryNotificationState({key})
    now = FrozenDateTime(
        2026,
        8,
        6,
        18,
        tzinfo=nc_calendar.TEAM_TZ,
    )
    event = _weekly_event(now)
    sender = Mock()
    timezone_getter = Mock(return_value=3)

    _run_poll_cycle(
        nc_calendar,
        monkeypatch,
        state=state,
        calendars=[FakeCalendar([event])],
        now=now,
        identities={USER_EMAIL: USER_ID},
        sender=sender,
        timezone_getter=timezone_getter,
    )

    assert state.keys == {key}
    assert state.deleted == []
    sender.assert_not_called()
    timezone_getter.assert_not_called()
    event.save.assert_not_called()


def test_participant_without_telegram_id_is_skipped(
    nc_calendar: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = InMemoryNotificationState()
    now = FrozenDateTime(
        2026,
        8,
        6,
        18,
        tzinfo=nc_calendar.TEAM_TZ,
    )
    event = _weekly_event(now, email="unknown@example.com")
    sender = Mock()
    timezone_getter = Mock(return_value=3)

    _run_poll_cycle(
        nc_calendar,
        monkeypatch,
        state=state,
        calendars=[FakeCalendar([event])],
        now=now,
        sender=sender,
        timezone_getter=timezone_getter,
    )

    assert state.keys == set()
    assert state.saved == []
    sender.assert_not_called()
    timezone_getter.assert_not_called()
    event.save.assert_not_called()


def test_incomplete_caldav_scan_preserves_local_state(
    nc_calendar: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = _key()
    state = InMemoryNotificationState({key})
    now = FrozenDateTime(
        2026,
        8,
        6,
        18,
        tzinfo=nc_calendar.TEAM_TZ,
    )
    mutator = Mock()

    _run_poll_cycle(
        nc_calendar,
        monkeypatch,
        state=state,
        calendars=[
            FakeCalendar(),
            FakeCalendar(error=RuntimeError("calendar unavailable")),
        ],
        now=now,
        mutator=mutator,
    )

    assert state.keys == {key}
    assert state.deleted == []
    mutator.assert_not_called()


def test_cleanup_deletes_only_stale_user_record(
    nc_calendar: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stale_key = _key(telegram_id=101)
    newly_sent_key = _key(telegram_id=202)
    other_cooldown_key = _key(telegram_id=202, cooldown=15)
    state = InMemoryNotificationState({stale_key, other_cooldown_key})
    now = FrozenDateTime(
        2026,
        8,
        6,
        18,
        tzinfo=nc_calendar.TEAM_TZ,
    )
    event = _weekly_event(now, email="second@example.com")

    _run_poll_cycle(
        nc_calendar,
        monkeypatch,
        state=state,
        calendars=[FakeCalendar([event])],
        now=now,
        identities={"second@example.com": 202},
        cooldowns=[COOLDOWN, 15],
    )

    assert state.deleted == [stale_key]
    assert state.saved == [newly_sent_key]
    assert state.keys == {newly_sent_key, other_cooldown_key}


def test_event_uid_with_underscores_is_not_truncated(
    nc_calendar: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = _key(event_uid="team_sync_2026_instance")
    state = InMemoryNotificationState({key})
    now = FrozenDateTime(
        2026,
        8,
        6,
        18,
        tzinfo=nc_calendar.TEAM_TZ,
    )

    _run_poll_cycle(
        nc_calendar,
        monkeypatch,
        state=state,
        calendars=[FakeCalendar()],
        now=now,
    )

    assert state.deleted == [key]
    assert state.deleted[0].event_uid == "team_sync_2026_instance"


def test_next_weekly_occurrence_can_be_notified_after_cleanup(
    nc_calendar: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = InMemoryNotificationState()
    sender = Mock()
    mutator = Mock()
    first_week = FrozenDateTime(
        2026,
        8,
        6,
        18,
        tzinfo=nc_calendar.TEAM_TZ,
    )
    first_event = _weekly_event(first_week)

    _run_poll_cycle(
        nc_calendar,
        monkeypatch,
        state=state,
        calendars=[FakeCalendar([first_event])],
        now=first_week,
        identities={USER_EMAIL: USER_ID},
        sender=sender,
        mutator=mutator,
    )

    assert sender.call_count == 1
    assert state.saved == [_key()]
    assert state.deleted == []
    assert state.keys == {_key()}

    _run_poll_cycle(
        nc_calendar,
        monkeypatch,
        state=state,
        calendars=[FakeCalendar()],
        now=first_week + timedelta(days=1),
        sender=sender,
        mutator=mutator,
    )

    assert sender.call_count == 1
    assert state.saved == [_key()]
    assert state.deleted == [_key()]
    assert state.keys == set()

    second_week = first_week + timedelta(days=7)
    second_event = _weekly_event(second_week)
    _run_poll_cycle(
        nc_calendar,
        monkeypatch,
        state=state,
        calendars=[FakeCalendar([second_event])],
        now=second_week,
        identities={USER_EMAIL: USER_ID},
        sender=sender,
        mutator=mutator,
    )

    assert sender.call_count == 2
    assert state.saved == [_key(), _key()]
    assert state.deleted == [_key()]
    assert state.keys == {_key()}
    mutator.assert_not_called()
    first_event.save.assert_not_called()
    second_event.save.assert_not_called()


def test_explicit_partstat_update_still_saves_event(
    nc_calendar: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = FrozenDateTime(
        2026,
        8,
        6,
        18,
        tzinfo=nc_calendar.TEAM_TZ,
    )
    FrozenDateTime.current = now
    attendee = FakeAttendee(USER_EMAIL)
    component = FakeComponent(
        {
            "UID": EVENT_UID,
            "ATTENDEE": attendee,
        }
    )
    event = FakeEvent(FakeICalendar([component]))
    calendar = FakeCalendar([event])
    principal = FakePrincipal([calendar])

    monkeypatch.setattr(nc_calendar, "datetime", FrozenDateTime)
    monkeypatch.setattr(
        nc_calendar,
        "DAVClient",
        lambda *_args, **_kwargs: FakeClient(principal),
    )

    result = nc_calendar.update_event_partstat(
        EVENT_UID,
        USER_EMAIL,
        "accepted",
    )

    assert result is True
    assert attendee.params["PARTSTAT"] == ["ACCEPTED"]
    assert attendee.params["RSVP"] == ["FALSE"]
    event.save.assert_called_once_with()
    assert calendar.expand_calls == [True]


def test_periodic_poller_has_no_caldav_write_calls(
    nc_calendar: ModuleType,
) -> None:
    source = textwrap.dedent(inspect.getsource(nc_calendar.poll_events))
    tree = ast.parse(source)
    called_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    called_attributes = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }

    assert "set_all_attendees_needs_action" not in called_names
    assert called_attributes.isdisjoint({"put", "save"})
