from datetime import tzinfo

from sqlalchemy import delete, select

from source.app_logging import logger
from source.db.db import get_session
from source.migrations.models import NextCloudLogin, User
from source.timezone import (
    TimezoneSettings,
    normalize_tzid,
    resolve_effective_timezone,
)

NEXTCLOUD_FIELD_MISSING = object()


class UserNotFoundError(LookupError):
    """Raised when a Telegram user has no linked Nextcloud profile."""


def _normalize_email(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    return normalized or None


def _apply_nextcloud_timezone(user: User, value: object) -> None:
    if value is NEXTCLOUD_FIELD_MISSING:
        return

    normalized = normalize_tzid(value)
    if normalized is not None:
        user.nc_timezone = normalized
        return

    if value is None or (isinstance(value, str) and not value.strip()):
        user.nc_timezone = None
        return

    logger.warning(
        "NEXTCLOUD: ignoring invalid timezone for user %s",
        user.nc_login,
    )


def get_login_by_tg_id(tg_id: int) -> str | None:
    """Return a Nextcloud login for a Telegram user."""
    with get_session() as session:
        user = session.get(User, tg_id)
        return user.nc_login if user else None


def get_email_by_tg_id(tg_id: int) -> str | None:
    """Return a Nextcloud email for a Telegram user."""
    with get_session() as session:
        user = session.get(User, tg_id)
        return user.nc_email if user else None


def get_tg_id_by_email(email: str) -> int | None:
    """Return a Telegram ID for a Nextcloud email."""
    with get_session() as session:
        stmt = select(User).where(User.nc_email == email)
        user = session.execute(stmt).scalar_one_or_none()
        return user.tg_id if user else None


def get_user_credentials_from_db(email: str) -> tuple[str, str] | None:
    """Return a user's Nextcloud login and app password."""
    with get_session() as session:
        stmt = select(User).where(User.nc_email == email)
        user = session.execute(stmt).scalar_one_or_none()
        if user is None or user.nc_token is None:
            return None
        return user.nc_login, user.nc_token


def save_login_to_db(tg_id: int, nc_login: str) -> None:
    """Save or update a Telegram-to-Nextcloud login mapping."""
    with get_session() as session:
        user = session.get(User, tg_id)
        if user:
            user.nc_login = nc_login
        else:
            session.add(User(tg_id=tg_id, nc_login=nc_login))


def save_login_profile(
    tg_id: int,
    nc_login: str,
    email: object,
    nc_token: str,
    *,
    timezone_value: object = NEXTCLOUD_FIELD_MISSING,
) -> None:
    """Atomically save Login Flow credentials and profile fields."""
    with get_session() as session:
        user = session.get(User, tg_id)
        if user is None:
            user = User(tg_id=tg_id, nc_login=nc_login)
            session.add(user)

        user.nc_login = nc_login
        user.nc_email = _normalize_email(email)
        user.nc_token = nc_token
        _apply_nextcloud_timezone(user, timezone_value)
        session.execute(
            delete(NextCloudLogin).where(NextCloudLogin.tg_id == tg_id)
        )


def save_login_to_db_with_token(
    tg_id: int,
    nc_login: str,
    email: str,
    nc_token: str,
) -> None:
    """Backward-compatible wrapper for the previous repository API."""
    save_login_profile(tg_id, nc_login, email, nc_token)


def update_nextcloud_profile(
    nc_login: str,
    *,
    email: object = NEXTCLOUD_FIELD_MISSING,
    timezone_value: object = NEXTCLOUD_FIELD_MISSING,
) -> bool:
    """Atomically update fields returned by an admin profile read."""
    with get_session() as session:
        stmt = select(User).where(User.nc_login == nc_login)
        user = session.execute(stmt).scalar_one_or_none()
        if user is None:
            return False

        if email is not NEXTCLOUD_FIELD_MISSING:
            normalized_email = _normalize_email(email)
            if normalized_email is not None:
                user.nc_email = normalized_email
        _apply_nextcloud_timezone(user, timezone_value)
        return True


def save_email_by_username(nc_email: str, nc_login: str) -> None:
    """Backward-compatible email-only profile update."""
    update_nextcloud_profile(nc_login, email=nc_email)


def get_timezone_settings(tg_id: int | None) -> TimezoneSettings:
    """Return stored timezone inputs for a Telegram user."""
    if tg_id is None:
        return TimezoneSettings(None, None)

    with get_session() as session:
        user = session.get(User, tg_id)
        if user is None:
            return TimezoneSettings(None, None)
        return TimezoneSettings(
            nextcloud_tzid=user.nc_timezone,
            override_tzid=user.timezone_override,
        )


def get_effective_timezone(
    tg_id: int | None,
    *,
    default_tzid: str,
) -> tzinfo:
    """Resolve a user's effective timezone as a real tzinfo object."""
    return resolve_effective_timezone(
        get_timezone_settings(tg_id),
        default_tzid=default_tzid,
    )


def set_timezone_override(tg_id: int, tzid: str) -> None:
    """Validate and save a user's explicit timezone override."""
    normalized = normalize_tzid(tzid)
    if normalized is None:
        raise ValueError("Unknown IANA timezone")

    with get_session() as session:
        user = session.get(User, tg_id)
        if user is None:
            raise UserNotFoundError(tg_id)
        user.timezone_override = normalized


def clear_timezone_override(tg_id: int) -> None:
    """Clear a user's override and restore automatic resolution."""
    with get_session() as session:
        user = session.get(User, tg_id)
        if user is None:
            raise UserNotFoundError(tg_id)
        user.timezone_override = None


def save_timezone(tg_id: int, timezone: int) -> None:
    """Save a legacy integer offset for rollback compatibility."""
    with get_session() as session:
        user = session.get(User, tg_id)
        if user:
            user.nc_time_zone = timezone


def get_timezone(tg_id: int) -> int:
    """Return a legacy integer offset for rollback compatibility."""
    with get_session() as session:
        user = session.get(User, tg_id)
        return user.nc_time_zone if user else 3


def get_user_list() -> list[tuple[int, str]]:
    """Return all Telegram ID and Nextcloud login pairs."""
    with get_session() as session:
        stmt = select(User.tg_id, User.nc_login)
        rows = session.execute(stmt).all()
        return [(row.tg_id, row.nc_login) for row in rows]


def get_user_map() -> dict[str, int]:
    """Return a Nextcloud-login-to-Telegram-ID mapping."""
    with get_session() as session:
        stmt = select(User.tg_id, User.nc_login)
        rows = session.execute(stmt).all()
        return {row.nc_login: row.tg_id for row in rows}


def get_users() -> list[dict[str, str | None]]:
    """Return stored Nextcloud credentials for background consumers."""
    with get_session() as session:
        stmt = select(User.nc_login, User.nc_token)
        rows = session.execute(stmt).all()
        return [
            {"username": row.nc_login, "password": row.nc_token}
            for row in rows
        ]


def save_login_token(tg_id: int, token: str) -> None:
    """Save a temporary Login Flow polling token."""
    with get_session() as session:
        session.add(NextCloudLogin(tg_id=tg_id, token=token))


def delete_login_token(tg_id: int) -> None:
    """Delete a temporary Login Flow polling token."""
    with get_session() as session:
        stmt = delete(NextCloudLogin).where(NextCloudLogin.tg_id == tg_id)
        session.execute(stmt)


def get_token(tg_id: int) -> str | None:
    """Return a temporary Login Flow polling token."""
    with get_session() as session:
        login_token = session.get(NextCloudLogin, tg_id)
        return login_token.token if login_token else None


def get_nc_token(tg_id: int) -> str | None:
    """Return a user's Nextcloud app password."""
    with get_session() as session:
        user = session.get(User, tg_id)
        return user.nc_token if user else None
