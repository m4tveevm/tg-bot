from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Connection

from alembic import command
from source.app_logging import logger
from source.db.db import DATABASE_URL


def get_alembic_config(database_url: str = DATABASE_URL) -> Config:
    base_dir = Path(__file__).resolve().parent.parent.parent
    ini_path = base_dir / "alembic.ini"

    cfg = Config(str(ini_path))

    cfg.attributes["configure_logger"] = False
    cfg.set_main_option("sqlalchemy.url", database_url)
    cfg.set_main_option("script_location", str(base_dir / "alembic"))
    return cfg


def _discard_orphaned_revisions(
    connection: Connection,
    cfg: Config,
) -> None:
    if not inspect(connection).has_table("alembic_version"):
        return

    current_revisions = set(
        connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalars()
    )
    known_revisions = {
        item.revision
        for item in ScriptDirectory.from_config(cfg).walk_revisions()
    }
    orphaned_revisions = current_revisions - known_revisions
    if not orphaned_revisions:
        return

    logger.warning(
        "Обнаружены legacy runtime-ревизии Alembic; "
        "они будут заменены через committed upgrade."
    )
    for revision in orphaned_revisions:
        connection.execute(
            text("DELETE FROM alembic_version WHERE version_num = :revision"),
            {"revision": revision},
        )


def auto_migrate(database_url: str = DATABASE_URL) -> None:
    """Apply committed migrations without changing migration history."""
    logger.info("Применение миграций базы данных...")
    cfg = get_alembic_config(database_url)
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            _discard_orphaned_revisions(connection, cfg)
            cfg.attributes["connection"] = connection
            command.upgrade(cfg, "head")
    finally:
        engine.dispose()
    logger.info("Миграции базы данных применены.")
