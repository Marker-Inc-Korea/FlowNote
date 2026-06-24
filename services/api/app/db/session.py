from collections.abc import Generator
from pathlib import Path
from sqlite3 import Connection as SQLiteConnection
from urllib.parse import unquote, urlparse

from fastapi import Request
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker


def _sqlite_path_from_url(database_url: str) -> Path | None:
    parsed = urlparse(database_url)
    if parsed.scheme != "sqlite":
        return None
    if parsed.path in ("", "/:memory:"):
        return None
    if parsed.netloc:
        return Path(f"//{parsed.netloc}{unquote(parsed.path)}")
    raw_path = unquote(parsed.path)
    if raw_path.startswith("/") and len(raw_path) > 2 and raw_path[2] == ":":
        raw_path = raw_path[1:]
    return Path(raw_path)


def ensure_database_parent(database_url: str) -> None:
    sqlite_path = _sqlite_path_from_url(database_url)
    if sqlite_path is not None:
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)


class Database:
    def __init__(self, database_url: str, *, echo: bool = False) -> None:
        ensure_database_parent(database_url)
        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        self.database_url = database_url
        self.engine = create_engine(database_url, echo=echo, future=True, connect_args=connect_args)
        if database_url.startswith("sqlite"):
            self._enable_sqlite_foreign_keys(self.engine)
        self.session_factory = sessionmaker(
            bind=self.engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
            future=True,
        )

    @staticmethod
    def _enable_sqlite_foreign_keys(engine: Engine) -> None:
        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_connection: SQLiteConnection, _connection_record: object) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    def session(self) -> Session:
        return self.session_factory()

    def check_connection(self) -> None:
        with self.engine.connect() as connection:
            connection.execute(text("SELECT 1"))

    def dispose(self) -> None:
        self.engine.dispose()


def get_database(request: Request) -> Database:
    return request.app.state.database


def get_db_session(request: Request) -> Generator[Session, None, None]:
    database = get_database(request)
    with database.session() as session:
        yield session
