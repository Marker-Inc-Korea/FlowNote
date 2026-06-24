from sqlalchemy import select

from app.db.base import Base
from app.db.models import SchemaMigration
from app.db.session import Database

INITIAL_SCHEMA_VERSION = "0001_initial_mvp_schema"


def initialize_database(database: Database) -> None:
    Base.metadata.create_all(bind=database.engine)
    with database.session() as session:
        existing = session.scalar(
            select(SchemaMigration).where(SchemaMigration.version == INITIAL_SCHEMA_VERSION)
        )
        if existing is None:
            session.add(
                SchemaMigration(
                    version=INITIAL_SCHEMA_VERSION,
                    description="Initial SQLite MVP schema for FlowNote API",
                )
            )
            session.commit()
