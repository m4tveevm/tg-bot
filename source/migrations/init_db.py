from sqlalchemy.engine import Connection, Engine

from source.db.db import engine
from source.migrations.models import Base


def init_db(bind: Engine | Connection = engine) -> None:
    Base.metadata.create_all(bind=bind)
