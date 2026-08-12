import importlib
import sys
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from types import ModuleType
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest

from tests.caldav_fakes import (
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
)

USER_ID = 101
USER_EMAIL = "user@example.com"


def _module(name: str, **attributes: object) -> ModuleType:
    module = ModuleType(name)
    for attribute, value in attributes.items():
        setattr(module, attribute, value)
    return module


def _ignore(*_args: object, **_kwargs: object) -> None:
    pass


@dataclass(frozen=True)
class TemporalProperty:
    dt: datetime | date
    params: dict[str, object] = field(default_factory=dict)


class RecordingCalendar(FakeCalendar):
    def __init__(self, events: list[FakeEvent] | None = None) -> None:
        super().__init__(events)
        self.searches: list[tuple[datetime, datetime]] = []

    def date_search(
        self,
        *,
        start: datetime,
        end: datetime,
        expand: bool = False,
    ) -> list[FakeEvent]:
        self.searches.append((start, end))
        return super().date_search(
            start=start,
            end=end,
            expand=expand,
        )


@pytest.fixture
def calendar_module(monkeypatch: pytest.MonkeyPatch):
    timezone_getter = Mock(return_value=ZoneInfo("Europe/Warsaw"))
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
        CALDAV_COOLDOWNS={},
    )
    modules = {
        "source.config": config,
        "source.connections.sender": _module(
            "source.connections.sender",
            send_message_limited=_ignore,
        ),
        "source.db.repos.users": _module(
            "source.db.repos.users",
            NEXTCLOUD_FIELD_MISSING=object(),
            get_effective_timezone=timezone_getter,
            get_tg_id_by_email=lambda _email: None,
            update_nextcloud_profile=_ignore,
        ),
        "source.db.repos.caldav_calendar": _module(
            "source.db.repos.caldav_calendar",
            delete_sent_event=_ignore,
            get_sent_event_keys=set,
            save_event_send=_ignore,
        ),
        "source.app_logging": _module(
            "source.app_logging",
            logger=FakeLogger(),
        ),
    }
    telebot_types = _module(
        "telebot.types",
        InlineKeyboardMarkup=FakeInlineKeyboardMarkup,
        InlineKeyboardButton=FakeInlineKeyboardButton,
    )
    modules.update(
        {
            "telebot": _module("telebot", types=telebot_types),
            "telebot.types": telebot_types,
            "caldav": _module("caldav", DAVClient=None, error=Exception),
            "icalendar": _module(
                "icalendar",
                Calendar=FakeCalendarParser,
                vText=lambda value: value,
            ),
            "requests": _module("requests", get=_ignore),
        }
    )
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)

    monkeypatch.delitem(sys.modules, "source.nc_calendar", raising=False)
    module = importlib.import_module("source.nc_calendar")
    yield module, timezone_getter
    sys.modules.pop("source.nc_calendar", None)


def _participant() -> dict[str, object]:
    return {
        "email": USER_EMAIL,
        "name": "User",
        "role": "ATTENDEE",
        "status": "NEEDS-ACTION",
    }


def _event(
    start: datetime | date,
    end: datetime | date,
    *,
    start_tzid: str | None = None,
    end_tzid: str | None = None,
    uid: str = "event-1",
) -> FakeEvent:
    start_params = {} if start_tzid is None else {"TZID": start_tzid}
    end_params = {} if end_tzid is None else {"TZID": end_tzid}
    component = FakeComponent(
        {
            "UID": uid,
            "SUMMARY": "Team sync",
            "DESCRIPTION": "Weekly team sync",
            "LOCATION": "Online",
            "DTSTART": TemporalProperty(start, start_params),
            "DTEND": TemporalProperty(end, end_params),
        },
        participants=[_participant()],
    )
    return FakeEvent(FakeICalendar([component]))


def _wire_calendar(
    module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    calendar: RecordingCalendar,
) -> None:
    principal = FakePrincipal([calendar])
    monkeypatch.setattr(
        module,
        "DAVClient",
        lambda *_args, **_kwargs: FakeClient(principal),
    )
    monkeypatch.setattr(
        module,
        "get_all_participants",
        lambda component: component.participants,
    )
    monkeypatch.setattr(
        module,
        "get_tg_id_by_email",
        lambda email: USER_ID if email == USER_EMAIL else None,
    )


def test_calendar_message_uses_localized_weekday_and_time(
    calendar_module,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, timezone_getter = calendar_module
    timezone_getter.return_value = ZoneInfo("Europe/Moscow")
    calendar = RecordingCalendar(
        [
            _event(
                datetime(2026, 8, 12, 9),
                datetime(2026, 8, 12, 10),
                start_tzid="Europe/Warsaw",
                end_tzid="Europe/Warsaw",
            )
        ]
    )
    _wire_calendar(module, monkeypatch, calendar)
    FrozenDateTime.current = FrozenDateTime(
        2026,
        8,
        11,
        12,
        tzinfo=UTC,
    )
    monkeypatch.setattr(module, "datetime", FrozenDateTime)

    result = module.get_calendar(USER_ID, 7)

    message, markup = result[0]
    assert module.WEEKDAY_RU[2] in message
    assert "Начало: 2026-08-12 10:00" in message
    assert "Конец: 2026-08-12 11:00" in message
    assert [button.text for button in markup.rows[0]] == [
        "Принять",
        "🔄",
        "Отклонить",
    ]
    assert [button.callback_data for button in markup.rows[0]] == [
        "c_ACCEPTED_event-1_NEEDS-ACTION_1",
        "update_event-1_1",
        "c_DECLINED_event-1_NEEDS-ACTION_1",
    ]
    timezone_getter.assert_called_once_with(
        USER_ID,
        default_tzid=module.TIMEZONE,
    )


def test_localized_weekday_changes_after_midnight(
    calendar_module,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, timezone_getter = calendar_module
    calendar = RecordingCalendar(
        [
            _event(
                datetime(2026, 8, 10, 22, 30, tzinfo=UTC),
                datetime(2026, 8, 10, 23, 30, tzinfo=UTC),
            )
        ]
    )
    _wire_calendar(module, monkeypatch, calendar)
    FrozenDateTime.current = FrozenDateTime(
        2026,
        8,
        10,
        12,
        tzinfo=UTC,
    )
    monkeypatch.setattr(module, "datetime", FrozenDateTime)

    result = module.get_calendar(USER_ID, 7)

    message = result[0][0]
    assert module.WEEKDAY_RU[1] in message
    assert "Начало: 2026-08-11 00:30" in message
    assert "Конец: 2026-08-11 01:30" in message
    timezone_getter.assert_called_once()


@pytest.mark.parametrize("tzid", ["Europe/Warsaw", "Europe/Moscow"])
def test_floating_refresh_message_uses_recipient_wall_time(
    calendar_module,
    monkeypatch: pytest.MonkeyPatch,
    tzid: str,
) -> None:
    module, timezone_getter = calendar_module
    timezone_getter.return_value = ZoneInfo(tzid)
    calendar = RecordingCalendar(
        [
            _event(
                datetime(2026, 10, 25, 9),
                datetime(2026, 10, 25, 10),
            )
        ]
    )
    _wire_calendar(module, monkeypatch, calendar)
    FrozenDateTime.current = FrozenDateTime(
        2026,
        10,
        24,
        12,
        tzinfo=UTC,
    )
    monkeypatch.setattr(module, "datetime", FrozenDateTime)

    message, _status = module.msg_design_from_button(
        "event-1",
        USER_ID,
        1,
    )

    assert module.WEEKDAY_RU[6] in message
    assert "Начало: 2026-10-25 09:00" in message
    assert "Конец: 2026-10-25 10:00" in message
    timezone_getter.assert_called_once()


def test_today_window_uses_recipient_local_midnight(
    calendar_module,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, timezone_getter = calendar_module
    calendar = RecordingCalendar()
    _wire_calendar(module, monkeypatch, calendar)
    FrozenDateTime.current = FrozenDateTime(
        2026,
        3,
        29,
        10,
        tzinfo=UTC,
    )
    monkeypatch.setattr(module, "datetime", FrozenDateTime)

    assert module.get_calendar(USER_ID, 1) == []

    start, end = calendar.searches[0]
    assert start.isoformat() == "2026-03-29T00:00:00+01:00"
    assert end.isoformat() == "2026-03-30T00:00:00+02:00"
    assert end.astimezone(UTC) - start.astimezone(UTC) == timedelta(hours=23)
    timezone_getter.assert_called_once()


@pytest.mark.parametrize("cooldown", [6, 7])
def test_week_window_uses_recipient_timezone(
    calendar_module,
    monkeypatch: pytest.MonkeyPatch,
    cooldown: int,
) -> None:
    module, timezone_getter = calendar_module
    calendar = RecordingCalendar()
    _wire_calendar(module, monkeypatch, calendar)
    FrozenDateTime.current = FrozenDateTime(
        2026,
        10,
        22,
        10,
        tzinfo=UTC,
    )
    monkeypatch.setattr(module, "datetime", FrozenDateTime)

    assert module.get_calendar(USER_ID, cooldown) == []

    start, end = calendar.searches[0]
    assert start.isoformat() == "2026-10-22T00:00:00+02:00"
    assert end.isoformat() == "2026-10-29T00:00:00+01:00"
    assert end.astimezone(UTC) - start.astimezone(UTC) == timedelta(hours=169)
    timezone_getter.assert_called_once()
