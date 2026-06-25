from hashlib import pbkdf2_hmac

from sqlalchemy import or_, select, text

from app.db.base import Base
from app.db.models import SchemaMigration, UserAccount
from app.db.session import Database

INITIAL_SCHEMA_VERSION = "0001_initial_mvp_schema"
DEFAULT_ADMIN_USER_ID = "user-admin"
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "1234"
DEFAULT_ADMIN_DISPLAY_NAME = "FlowNote Admin"
DEFAULT_ADMIN_ROLE = "admin"
DEFAULT_ADMIN_PASSWORD_SALT = "flownote-dev-admin-v1"
DEFAULT_ADMIN_PASSWORD_ITERATIONS = 100_000


def hash_password_for_dev(password: str) -> str:
    digest = pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        DEFAULT_ADMIN_PASSWORD_SALT.encode("utf-8"),
        DEFAULT_ADMIN_PASSWORD_ITERATIONS,
    ).hex()
    return (
        f"pbkdf2_sha256${DEFAULT_ADMIN_PASSWORD_ITERATIONS}$"
        f"{DEFAULT_ADMIN_PASSWORD_SALT}${digest}"
    )


def _ensure_user_account_columns(database: Database) -> None:
    if not database.database_url.startswith("sqlite"):
        return

    with database.engine.begin() as connection:
        existing_columns = {
            row[1] for row in connection.execute(text("PRAGMA table_info(user_accounts)"))
        }
        if not existing_columns:
            return

        if "username" not in existing_columns:
            connection.execute(text("ALTER TABLE user_accounts ADD COLUMN username VARCHAR(100)"))
            connection.execute(
                text(
                    "UPDATE user_accounts "
                    "SET username = COALESCE(NULLIF(login_id, ''), user_id, 'user-' || id) "
                    "WHERE username IS NULL OR username = ''"
                )
            )
        if "role" not in existing_columns:
            connection.execute(
                text("ALTER TABLE user_accounts ADD COLUMN role VARCHAR(50) DEFAULT 'viewer'")
            )
            connection.execute(
                text("UPDATE user_accounts SET role = 'viewer' WHERE role IS NULL OR role = ''")
            )
        if "is_active" not in existing_columns:
            connection.execute(
                text("ALTER TABLE user_accounts ADD COLUMN is_active BOOLEAN DEFAULT 1")
            )
            connection.execute(text("UPDATE user_accounts SET is_active = 1 WHERE is_active IS NULL"))

        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                "ix_user_accounts_username ON user_accounts (username)"
            )
        )


def _seed_default_admin_account(database: Database) -> None:
    with database.session() as session:
        existing = session.scalar(
            select(UserAccount).where(
                or_(
                    UserAccount.username == DEFAULT_ADMIN_USERNAME,
                    UserAccount.login_id == DEFAULT_ADMIN_USERNAME,
                    UserAccount.user_id == DEFAULT_ADMIN_USER_ID,
                )
            )
        )
        if existing is not None:
            return

        session.add(
            UserAccount(
                user_id=DEFAULT_ADMIN_USER_ID,
                username=DEFAULT_ADMIN_USERNAME,
                login_id=DEFAULT_ADMIN_USERNAME,
                display_name=DEFAULT_ADMIN_DISPLAY_NAME,
                role=DEFAULT_ADMIN_ROLE,
                password_hash=hash_password_for_dev(DEFAULT_ADMIN_PASSWORD),
                is_active=True,
                status="ACTIVE",
            )
        )
        session.commit()


def initialize_database(database: Database) -> None:
    Base.metadata.create_all(bind=database.engine)
    _ensure_user_account_columns(database)
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
    _seed_default_admin_account(database)
