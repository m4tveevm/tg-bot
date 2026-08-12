"""Add Nextcloud and override timezone fields.

Revision ID: 0001_user_timezones
Revises:
Create Date: 2026-08-11
"""

from collections.abc import Iterable

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from alembic import op

revision = "0001_user_timezones"
down_revision = None
branch_labels = None
depends_on = None


def _column_names(connection: Connection) -> set[str]:
    inspector = sa.inspect(connection)
    if not inspector.has_table("users"):
        return set()
    return {column["name"] for column in inspector.get_columns("users")}


def _legacy_offset_to_tzid(value: object) -> str | None:
    if not isinstance(value, int) or isinstance(value, bool):
        return None
    if value == 3 or not -12 <= value <= 14:
        return None
    if value == 0:
        return "Etc/UTC"
    if value > 0:
        return f"Etc/GMT-{value}"
    return f"Etc/GMT+{abs(value)}"


def _legacy_users(connection: Connection) -> Iterable[sa.RowMapping]:
    result = connection.execute(
        sa.text("SELECT tg_id, nc_time_zone, timezone_override FROM users")
    )
    return result.mappings()


def _backfill_legacy_offsets(connection: Connection) -> None:
    for user in _legacy_users(connection):
        if user["timezone_override"] is not None:
            continue
        tzid = _legacy_offset_to_tzid(user["nc_time_zone"])
        if tzid is None:
            continue
        connection.execute(
            sa.text(
                "UPDATE users SET timezone_override = :tzid "
                "WHERE tg_id = :tg_id AND timezone_override IS NULL"
            ),
            {"tg_id": user["tg_id"], "tzid": tzid},
        )


def upgrade() -> None:
    connection = op.get_bind()
    columns = _column_names(connection)
    if not columns:
        return

    with op.batch_alter_table("users") as batch_op:
        if "nc_email" not in columns:
            batch_op.add_column(
                sa.Column("nc_email", sa.String(255), nullable=True)
            )
        if "nc_time_zone" not in columns:
            batch_op.add_column(
                sa.Column(
                    "nc_time_zone",
                    sa.Integer(),
                    nullable=False,
                    server_default=sa.text("3"),
                )
            )
        if "nc_timezone" not in columns:
            batch_op.add_column(
                sa.Column("nc_timezone", sa.String(64), nullable=True)
            )
        if "timezone_override" not in columns:
            batch_op.add_column(
                sa.Column("timezone_override", sa.String(64), nullable=True)
            )
        if "nc_token" not in columns:
            batch_op.add_column(
                sa.Column("nc_token", sa.String(100), nullable=True)
            )

    if "nc_time_zone" in columns:
        _backfill_legacy_offsets(connection)


def downgrade() -> None:
    connection = op.get_bind()
    columns = _column_names(connection)
    if not columns:
        return

    with op.batch_alter_table("users") as batch_op:
        if "timezone_override" in columns:
            batch_op.drop_column("timezone_override")
        if "nc_timezone" in columns:
            batch_op.drop_column("nc_timezone")
