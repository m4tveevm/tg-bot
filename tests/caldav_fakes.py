from dataclasses import dataclass, field
from datetime import date, datetime
from typing import ClassVar
from unittest.mock import Mock

from source.caldav_notification_state import SentEventKey


class StopPolling(Exception):
    pass


class FrozenDateTime(datetime):
    current: ClassVar["FrozenDateTime"]

    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return cls.current.replace(tzinfo=None)

        return cls.current.astimezone(tz)


@dataclass(frozen=True)
class DateProperty:
    dt: datetime | date
    params: dict[str, object] = field(default_factory=dict)


class FakeComponent:
    name = "VEVENT"

    def __init__(
        self,
        values: dict[str, object],
        *,
        participants: list[dict[str, object]] | None = None,
    ) -> None:
        self._values = {key.upper(): value for key, value in values.items()}
        self.participants = participants or []

    def get(self, key: str, default=None):
        return self._values.get(key.upper(), default)


class FakeICalendar:
    def __init__(self, components: list[FakeComponent]) -> None:
        self.components = components

    def walk(self, name: str | None = None) -> list[FakeComponent]:
        if name is None:
            return list(self.components)

        return [
            component
            for component in self.components
            if component.name == name.upper()
        ]


class FakeEvent:
    def __init__(
        self,
        calendar_data: FakeICalendar,
        *,
        url: str = "https://calendar.test/event.ics",
    ) -> None:
        self.data = calendar_data
        self.url = url
        self.icalendar_instance = calendar_data
        self.save = Mock()


class FakeCalendar:
    def __init__(
        self,
        events: list[FakeEvent] | None = None,
        *,
        error: Exception | None = None,
        name: str = "Team",
    ) -> None:
        self.events = events or []
        self.error = error
        self.name = name
        self.expand_calls: list[bool] = []
        self.search_calls: list[tuple[object, object]] = []

    def date_search(
        self,
        *,
        start: object,
        end: object,
        expand: bool = False,
    ) -> list[FakeEvent]:
        self.expand_calls.append(expand)
        self.search_calls.append((start, end))
        if self.error is not None:
            raise self.error

        return list(self.events)


class FakePrincipal:
    def __init__(self, calendars: list[FakeCalendar]) -> None:
        self._calendars = calendars

    def calendars(self) -> list[FakeCalendar]:
        return list(self._calendars)


class FakeClient:
    def __init__(self, principal: FakePrincipal) -> None:
        self._principal = principal

    def principal(self) -> FakePrincipal:
        return self._principal


class FakeCalendarParser:
    @staticmethod
    def from_ical(data: FakeICalendar) -> FakeICalendar:
        return data


class FakeInlineKeyboardButton:
    def __init__(
        self,
        text: str,
        *,
        style: str | None = None,
        callback_data: str | None = None,
    ) -> None:
        self.text = text
        self.style = style
        self.callback_data = callback_data


class FakeInlineKeyboardMarkup:
    def __init__(self) -> None:
        self.rows: list[tuple[FakeInlineKeyboardButton, ...]] = []

    def row(self, *buttons: FakeInlineKeyboardButton) -> None:
        self.rows.append(buttons)


class FakeLogger:
    def _ignore(self, *_args: object, **_kwargs: object) -> None:
        pass

    debug = _ignore
    error = _ignore
    exception = _ignore
    info = _ignore
    warning = _ignore


class FakeAttendee:
    def __init__(self, email: str) -> None:
        self.email = email
        self.params = {
            "PARTSTAT": ["NEEDS-ACTION"],
            "RSVP": ["TRUE"],
        }

    def __str__(self) -> str:
        return f"mailto:{self.email}"


@dataclass
class InMemoryNotificationState:
    keys: set[SentEventKey] = field(default_factory=set)
    saved: list[SentEventKey] = field(default_factory=list)
    deleted: list[SentEventKey] = field(default_factory=list)

    def load(self) -> set[SentEventKey]:
        return set(self.keys)

    def save(
        self,
        _name: str,
        key: SentEventKey,
        _url: str,
    ) -> None:
        self.keys.add(key)
        self.saved.append(key)

    def delete(self, key: SentEventKey) -> None:
        self.keys.discard(key)
        self.deleted.append(key)


def make_poll_event(
    *,
    event_uid: str,
    summary: str,
    start: datetime | date,
    end: datetime | date,
    participants: list[dict[str, object]],
    ical_attendees: FakeAttendee | list[FakeAttendee] | None = None,
    start_tzid: str | None = None,
    end_tzid: str | None = None,
) -> FakeEvent:
    start_params = {"TZID": start_tzid} if start_tzid is not None else {}
    end_params = {"TZID": end_tzid} if end_tzid is not None else {}
    values = {
        "UID": event_uid,
        "SUMMARY": summary,
        "DESCRIPTION": "Weekly team sync",
        "LOCATION": "Online",
        "DTSTART": DateProperty(start, start_params),
        "DTEND": DateProperty(end, end_params),
    }
    if ical_attendees is not None:
        values["ATTENDEE"] = ical_attendees

    component = FakeComponent(values, participants=participants)
    return FakeEvent(FakeICalendar([component]))
