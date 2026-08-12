from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from source.db.repos import users
from source.migrations.models import NextCloudLogin, User


@pytest.fixture
def session_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> sessionmaker[Session]:
    engine = create_engine("sqlite:///:memory:")
    User.__table__.create(engine)
    NextCloudLogin.__table__.create(engine)
    factory = sessionmaker(bind=engine)

    @contextmanager
    def test_session() -> Iterator[Session]:
        session = factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    monkeypatch.setattr(users, "get_session", test_session)
    return factory


def _add_user(
    factory: sessionmaker[Session],
    *,
    tg_id: int = 1,
    timezone: str | None = "Europe/Berlin",
) -> None:
    with factory.begin() as session:
        session.add(
            User(
                tg_id=tg_id,
                nc_login=f"user-{tg_id}",
                nc_email="old@example.test",
                nc_timezone=timezone,
            )
        )


def _user(factory: sessionmaker[Session], tg_id: int = 1) -> User:
    with factory() as session:
        return session.execute(
            select(User).where(User.tg_id == tg_id)
        ).scalar_one()


def test_login_flow_saves_nextcloud_timezone(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory.begin() as session:
        session.add(NextCloudLogin(tg_id=1, token="poll-token"))

    users.save_login_profile(
        1,
        "alice",
        "Alice@Example.test",
        "app-password",
        timezone_value=" Europe/Warsaw ",
    )

    stored = _user(session_factory)
    assert stored.nc_login == "alice"
    assert stored.nc_email == "alice@example.test"
    assert stored.nc_token == "app-password"
    assert stored.nc_timezone == "Europe/Warsaw"
    with session_factory() as session:
        assert session.get(NextCloudLogin, 1) is None


def test_login_flow_accepts_missing_timezone_from_nextcloud_31(
    session_factory: sessionmaker[Session],
) -> None:
    _add_user(session_factory)

    users.save_login_profile(
        1,
        "user-1",
        "new@example.test",
        "new-token",
        timezone_value=users.NEXTCLOUD_FIELD_MISSING,
    )

    assert _user(session_factory).nc_timezone == "Europe/Berlin"


def test_login_flow_stores_empty_timezone_as_none(
    session_factory: sessionmaker[Session],
) -> None:
    _add_user(session_factory)

    users.save_login_profile(
        1,
        "user-1",
        "new@example.test",
        "new-token",
        timezone_value="   ",
    )

    assert _user(session_factory).nc_timezone is None


def test_login_flow_ignores_invalid_timezone(
    session_factory: sessionmaker[Session],
) -> None:
    _add_user(session_factory)

    users.save_login_profile(
        1,
        "user-1",
        "new@example.test",
        "new-token",
        timezone_value="Invalid/Timezone",
    )

    assert _user(session_factory).nc_timezone == "Europe/Berlin"


def test_admin_sync_updates_email_and_timezone_atomically(
    session_factory: sessionmaker[Session],
) -> None:
    _add_user(session_factory)

    assert users.update_nextcloud_profile(
        "user-1",
        email="new@example.test",
        timezone_value="Asia/Kolkata",
    )

    stored = _user(session_factory)
    assert stored.nc_email == "new@example.test"
    assert stored.nc_timezone == "Asia/Kolkata"


def test_admin_sync_rolls_back_profile_after_timezone_error(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _add_user(session_factory)

    def fail_timezone_update(_user: User, _value: object) -> None:
        raise RuntimeError("timezone update failed")

    monkeypatch.setattr(
        users,
        "_apply_nextcloud_timezone",
        fail_timezone_update,
    )

    with pytest.raises(RuntimeError, match="timezone update failed"):
        users.update_nextcloud_profile(
            "user-1",
            email="new@example.test",
            timezone_value="Asia/Kolkata",
        )

    stored = _user(session_factory)
    assert stored.nc_email == "old@example.test"
    assert stored.nc_timezone == "Europe/Berlin"


def test_admin_sync_updates_timezone_without_email(
    session_factory: sessionmaker[Session],
) -> None:
    _add_user(session_factory)

    users.update_nextcloud_profile(
        "user-1",
        timezone_value="Europe/Warsaw",
    )

    stored = _user(session_factory)
    assert stored.nc_email == "old@example.test"
    assert stored.nc_timezone == "Europe/Warsaw"


def test_admin_sync_clears_explicit_empty_timezone(
    session_factory: sessionmaker[Session],
) -> None:
    _add_user(session_factory)

    users.update_nextcloud_profile("user-1", timezone_value=None)

    assert _user(session_factory).nc_timezone is None


def test_admin_sync_preserves_timezone_when_field_is_missing(
    session_factory: sessionmaker[Session],
) -> None:
    _add_user(session_factory)

    users.update_nextcloud_profile(
        "user-1",
        email="new@example.test",
    )

    assert _user(session_factory).nc_timezone == "Europe/Berlin"


def test_admin_sync_preserves_timezone_when_value_is_invalid(
    session_factory: sessionmaker[Session],
) -> None:
    _add_user(session_factory)

    users.update_nextcloud_profile(
        "user-1",
        timezone_value="Mars/Olympus",
    )

    assert _user(session_factory).nc_timezone == "Europe/Berlin"


def test_timezone_override_round_trip(
    session_factory: sessionmaker[Session],
) -> None:
    _add_user(session_factory)

    users.set_timezone_override(1, " Europe/Warsaw ")
    assert _user(session_factory).timezone_override == "Europe/Warsaw"

    users.clear_timezone_override(1)
    assert _user(session_factory).timezone_override is None
