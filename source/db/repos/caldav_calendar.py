from sqlalchemy import delete, select

from source.caldav_notification_state import SentEventKey
from source.db.db import get_session
from source.migrations.models import CalDavSendData


def get_sent_event_keys() -> set[SentEventKey]:
    """Возвращает ключи отправленных уведомлений из базы данных."""
    with get_session() as session:
        stmt = select(
            CalDavSendData.tg_id,
            CalDavSendData.cooldown,
            CalDavSendData.event_name,
        )
        rows = session.execute(stmt).all()
        return {
            SentEventKey(
                telegram_id=row.tg_id,
                cooldown_minutes=row.cooldown,
                event_uid=row.event_name,
            )
            for row in rows
        }


def get_url_by_id(t_id: int) -> str | None:
    """Возвращает URL события по ID."""
    with get_session() as session:
        event = session.get(CalDavSendData, t_id)
        return event.url if event else None


def get_name_by_id(t_id: int) -> str | None:
    """Возвращает event_name по ID."""
    with get_session() as session:
        event = session.get(CalDavSendData, t_id)
        return event.event_name if event else None


def get_id_by_name(name: str) -> int | None:
    """Возвращает ID события по event_name."""
    with get_session() as session:
        stmt = select(CalDavSendData).where(
            CalDavSendData.event_name == name,
        )
        event = session.execute(stmt).scalar_one_or_none()
        return event.id if event else None


def save_event_send(
    name: str,
    key: SentEventKey,
    url: str,
) -> None:
    """Сохраняет новое событие (игнорирует дубликаты)."""
    with get_session() as session:
        stmt = select(CalDavSendData).where(
            CalDavSendData.event_name == key.event_uid,
            CalDavSendData.tg_id == key.telegram_id,
            CalDavSendData.cooldown == key.cooldown_minutes,
        )
        existing = session.execute(stmt).scalar_one_or_none()
        if not existing:
            event = CalDavSendData(
                name=name,
                tg_id=key.telegram_id,
                cooldown=key.cooldown_minutes,
                event_name=key.event_uid,
                url=url,
            )
            session.add(event)


def delete_sent_event(key: SentEventKey) -> None:
    """Удаляет точную запись отправленного уведомления."""
    with get_session() as session:
        stmt = delete(CalDavSendData).where(
            CalDavSendData.tg_id == key.telegram_id,
            CalDavSendData.cooldown == key.cooldown_minutes,
            CalDavSendData.event_name == key.event_uid,
        )
        session.execute(stmt)
