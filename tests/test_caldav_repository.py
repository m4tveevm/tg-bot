import importlib.util
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

import pytest

from source.caldav_notification_state import SentEventKey


@dataclass(frozen=True)
class Condition:
    field_name: str
    value: object


class Field:
    def __init__(self, name: str) -> None:
        self.name = name

    def __eq__(self, value: object) -> Condition:
        return Condition(self.name, value)


class Statement:
    def __init__(self, operation: str) -> None:
        self.operation = operation
        self.conditions: tuple[Condition, ...] = ()

    def where(self, *conditions: Condition) -> "Statement":
        self.conditions = conditions
        return self


class FakeCalDavSendData:
    tg_id = Field("tg_id")
    cooldown = Field("cooldown")
    event_name = Field("event_name")


class FakeSession:
    def __init__(self) -> None:
        self.executed: list[Statement] = []

    def execute(self, statement: Statement) -> None:
        self.executed.append(statement)


@pytest.fixture
def repository_module(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[ModuleType, FakeSession]:
    session = FakeSession()

    @contextmanager
    def get_session() -> Iterator[FakeSession]:
        yield session

    sqlalchemy = ModuleType("sqlalchemy")
    sqlalchemy.delete = lambda model: Statement("delete")
    sqlalchemy.select = lambda *fields: Statement("select")

    db_module = ModuleType("source.db.db")
    db_module.get_session = get_session

    models_module = ModuleType("source.migrations.models")
    models_module.CalDavSendData = FakeCalDavSendData

    monkeypatch.setitem(sys.modules, "sqlalchemy", sqlalchemy)
    monkeypatch.setitem(sys.modules, "source.db.db", db_module)
    monkeypatch.setitem(
        sys.modules,
        "source.migrations.models",
        models_module,
    )

    module_path = (
        Path(__file__).parents[1]
        / "source"
        / "db"
        / "repos"
        / "caldav_calendar.py"
    )
    spec = importlib.util.spec_from_file_location(
        "caldav_repository_under_test",
        module_path,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return module, session


def test_delete_sent_event_uses_exact_composite_key(
    repository_module: tuple[ModuleType, FakeSession],
) -> None:
    repository, session = repository_module
    key = SentEventKey(
        telegram_id=101,
        cooldown_minutes=60,
        event_uid="team_sync_2026_instance",
    )

    repository.delete_sent_event(key)

    assert len(session.executed) == 1
    statement = session.executed[0]
    assert statement.operation == "delete"
    assert statement.conditions == (
        Condition("tg_id", 101),
        Condition("cooldown", 60),
        Condition("event_name", "team_sync_2026_instance"),
    )
