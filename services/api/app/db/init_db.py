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
ALLOWED_USER_ROLES = (
    "admin",
    "manager",
    "viewer",
    "system-admin",
    "document-admin",
    "assistant-manager",
    "department-manager",
    "line-foreman",
    "team-lead",
    "team-member",
)


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


def _ensure_user_account_role_constraint(database: Database) -> None:
    if not database.database_url.startswith("sqlite"):
        return

    with database.engine.begin() as connection:
        table_sql = connection.scalar(
            text("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'user_accounts'")
        )
        if not table_sql or "team-lead" in table_sql:
            return

        roles_sql = ", ".join(f"'{role}'" for role in ALLOWED_USER_ROLES)
        connection.execute(text("PRAGMA foreign_keys=OFF"))
        connection.execute(
            text(
                f"""
                CREATE TABLE user_accounts_new (
                    id INTEGER NOT NULL,
                    user_id VARCHAR(64) NOT NULL,
                    username VARCHAR(100) NOT NULL,
                    login_id VARCHAR(100) NOT NULL,
                    display_name VARCHAR(100) NOT NULL,
                    role VARCHAR(50) NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    is_active BOOLEAN NOT NULL,
                    status VARCHAR(20) NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    PRIMARY KEY (id),
                    CONSTRAINT ck_user_role CHECK (role IN ({roles_sql})),
                    CONSTRAINT ck_user_status CHECK (status IN ('ACTIVE', 'LOCKED', 'DISABLED')),
                    UNIQUE (user_id),
                    UNIQUE (username),
                    UNIQUE (login_id)
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO user_accounts_new (
                    id,
                    user_id,
                    username,
                    login_id,
                    display_name,
                    role,
                    password_hash,
                    is_active,
                    status,
                    created_at,
                    updated_at
                )
                SELECT
                    id,
                    user_id,
                    username,
                    login_id,
                    display_name,
                    CASE
                        WHEN role IS NULL OR role = '' THEN 'viewer'
                        ELSE role
                    END,
                    password_hash,
                    COALESCE(is_active, 1),
                    COALESCE(NULLIF(status, ''), 'ACTIVE'),
                    COALESCE(created_at, CURRENT_TIMESTAMP),
                    COALESCE(updated_at, CURRENT_TIMESTAMP)
                FROM user_accounts
                """
            )
        )
        connection.execute(text("DROP TABLE user_accounts"))
        connection.execute(text("ALTER TABLE user_accounts_new RENAME TO user_accounts"))
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_user_accounts_user_id ON user_accounts (user_id)")
        )
        connection.execute(
            text("CREATE UNIQUE INDEX IF NOT EXISTS ix_user_accounts_username ON user_accounts (username)")
        )
        connection.execute(
            text("CREATE UNIQUE INDEX IF NOT EXISTS ix_user_accounts_login_id ON user_accounts (login_id)")
        )
        connection.execute(text("PRAGMA foreign_keys=ON"))


def _ensure_idempotency_columns(database: Database) -> None:
    if not database.database_url.startswith("sqlite"):
        return

    targets = (
        ("documents", "ix_documents_idempotency_key"),
        ("field_comments", "ix_field_comments_idempotency_key"),
        ("document_access_logs", "ix_document_access_logs_idempotency_key"),
    )
    with database.engine.begin() as connection:
        for table_name, index_name in targets:
            existing_columns = {
                row[1] for row in connection.execute(text(f"PRAGMA table_info({table_name})"))
            }
            if not existing_columns:
                continue
            if "idempotency_key" not in existing_columns:
                connection.execute(
                    text(f"ALTER TABLE {table_name} ADD COLUMN idempotency_key VARCHAR(160)")
                )
            connection.execute(
                text(
                    f"CREATE UNIQUE INDEX IF NOT EXISTS {index_name} "
                    f"ON {table_name} (idempotency_key)"
                )
            )


def _ensure_work_sequence_columns(database: Database) -> None:
    if not database.database_url.startswith("sqlite"):
        return

    targets = {
        "work_sequence_items": (("hold_reason", "TEXT"),),
        "work_sequence_notification_candidates": (
            ("recipient_hint", "VARCHAR(120)"),
        ),
    }
    with database.engine.begin() as connection:
        for table_name, columns in targets.items():
            existing_columns = {
                row[1] for row in connection.execute(text(f"PRAGMA table_info({table_name})"))
            }
            if not existing_columns:
                continue
            for column_name, definition in columns:
                if column_name not in existing_columns:
                    connection.execute(
                        text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")
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
    _ensure_user_account_role_constraint(database)
    _ensure_idempotency_columns(database)
    _ensure_work_sequence_columns(database)
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
