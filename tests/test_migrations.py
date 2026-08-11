from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from source.migrations.init_db import init_db
from source.migrations.migration import auto_migrate


def _database_url(tmp_path: Path, name: str) -> str:
    return f"sqlite:///{tmp_path / name}"


def _create_legacy_users(
    database_url: str,
    offsets: list[int],
) -> Engine:
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE users ("
                "tg_id BIGINT PRIMARY KEY, "
                "nc_login VARCHAR(100) NOT NULL, "
                "nc_time_zone INTEGER NOT NULL DEFAULT 3"
                ")"
            )
        )
        for tg_id, offset in enumerate(offsets, start=1):
            connection.execute(
                text(
                    "INSERT INTO users "
                    "(tg_id, nc_login, nc_time_zone) "
                    "VALUES (:tg_id, :nc_login, :offset)"
                ),
                {
                    "nc_login": f"user-{tg_id}",
                    "offset": offset,
                    "tg_id": tg_id,
                },
            )
    return engine


def _overrides(engine: Engine) -> list[str | None]:
    with engine.connect() as connection:
        result = connection.execute(
            text("SELECT timezone_override FROM users ORDER BY tg_id")
        )
        return list(result.scalars())


def test_migration_adds_timezone_columns_to_legacy_schema(
    tmp_path: Path,
) -> None:
    database_url = _database_url(tmp_path, "legacy-columns.db")
    engine = _create_legacy_users(database_url, [3])

    auto_migrate(database_url)

    column_names = {
        column["name"] for column in inspect(engine).get_columns("users")
    }
    assert {"nc_timezone", "timezone_override"} <= column_names


def test_migration_adapts_original_init_sql_user_schema(
    tmp_path: Path,
) -> None:
    database_url = _database_url(tmp_path, "init-sql-users.db")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE users ("
                "tg_id BIGINT PRIMARY KEY, "
                "nc_login VARCHAR(100) NOT NULL"
                ")"
            )
        )
        connection.execute(
            text(
                "INSERT INTO users (tg_id, nc_login) VALUES (1, 'legacy-user')"
            )
        )

    auto_migrate(database_url)

    column_names = {
        column["name"] for column in inspect(engine).get_columns("users")
    }
    assert {
        "nc_email",
        "nc_time_zone",
        "nc_timezone",
        "timezone_override",
        "nc_token",
    } <= column_names
    with engine.connect() as connection:
        offset = connection.execute(
            text("SELECT nc_time_zone FROM users WHERE tg_id = 1")
        ).scalar_one()
    assert offset == 3


def test_migration_backfills_non_default_legacy_offset(
    tmp_path: Path,
) -> None:
    database_url = _database_url(tmp_path, "legacy-offsets.db")
    engine = _create_legacy_users(database_url, [-12, 0, 4, -5, 14])

    auto_migrate(database_url)

    assert _overrides(engine) == [
        "Etc/GMT+12",
        "Etc/UTC",
        "Etc/GMT-4",
        "Etc/GMT+5",
        "Etc/GMT-14",
    ]


def test_migration_does_not_treat_legacy_default_as_override(
    tmp_path: Path,
) -> None:
    database_url = _database_url(tmp_path, "legacy-default.db")
    engine = _create_legacy_users(database_url, [3])

    auto_migrate(database_url)

    assert _overrides(engine) == [None]


def test_migration_ignores_out_of_range_legacy_offset(
    tmp_path: Path,
) -> None:
    database_url = _database_url(tmp_path, "legacy-out-of-range.db")
    engine = _create_legacy_users(database_url, [-13, 15])

    auto_migrate(database_url)

    assert _overrides(engine) == [None, None]


def test_migration_is_safe_on_fresh_database(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path, "fresh.db")
    engine = create_engine(database_url)
    init_db(engine)

    auto_migrate(database_url)

    column_names = {
        column["name"] for column in inspect(engine).get_columns("users")
    }
    assert {"nc_timezone", "timezone_override"} <= column_names


def test_migration_is_idempotent_across_application_restarts(
    tmp_path: Path,
) -> None:
    database_url = _database_url(tmp_path, "repeated.db")
    engine = _create_legacy_users(database_url, [4])

    auto_migrate(database_url)
    auto_migrate(database_url)

    assert _overrides(engine) == ["Etc/GMT-4"]
    with engine.connect() as connection:
        revisions = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalars()
        assert list(revisions) == ["0001_user_timezones"]


def test_migration_replaces_orphaned_runtime_revision(
    tmp_path: Path,
) -> None:
    database_url = _database_url(tmp_path, "orphaned-revision.db")
    engine = _create_legacy_users(database_url, [4])
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE alembic_version ("
                "version_num VARCHAR(32) NOT NULL PRIMARY KEY"
                ")"
            )
        )
        connection.execute(
            text(
                "INSERT INTO alembic_version (version_num) "
                "VALUES ('runtime_generated')"
            )
        )

    auto_migrate(database_url)

    assert _overrides(engine) == ["Etc/GMT-4"]
    with engine.connect() as connection:
        revisions = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalars()
        assert list(revisions) == ["0001_user_timezones"]
