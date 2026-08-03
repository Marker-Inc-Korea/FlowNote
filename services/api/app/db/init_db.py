from hashlib import pbkdf2_hmac
from hmac import compare_digest
import secrets

from sqlalchemy import inspect, or_, select, text

from app.db.base import Base
from app.db.models import SchemaMigration, ServerIdentity, UserAccount
from app.db.session import Database

INITIAL_SCHEMA_VERSION = "0001_initial_mvp_schema"
COMMON_MUTATION_RECEIPT_SCHEMA_VERSION = "0002_common_mutation_receipts"
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


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        DEFAULT_ADMIN_PASSWORD_ITERATIONS,
    ).hex()
    return f"pbkdf2_sha256${DEFAULT_ADMIN_PASSWORD_ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored_password_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt, expected_digest = stored_password_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_text)
        if iterations <= 0 or iterations > 1_000_000:
            return False
    except (TypeError, ValueError):
        return False
    actual_digest = pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    ).hex()
    return compare_digest(actual_digest, expected_digest)


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
        if "must_change_password" not in existing_columns:
            connection.execute(
                text("ALTER TABLE user_accounts ADD COLUMN must_change_password BOOLEAN DEFAULT 0")
            )
            connection.execute(
                text(
                    "UPDATE user_accounts SET must_change_password = 0 "
                    "WHERE must_change_password IS NULL"
                )
            )
        if "password_changed_at" not in existing_columns:
            connection.execute(
                text("ALTER TABLE user_accounts ADD COLUMN password_changed_at DATETIME")
            )

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
                    must_change_password BOOLEAN DEFAULT 0 NOT NULL,
                    password_changed_at DATETIME,
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
                    must_change_password,
                    password_changed_at,
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
                    COALESCE(must_change_password, 0),
                    password_changed_at,
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
        ("document_versions", "ix_document_versions_idempotency_key"),
        ("field_comments", "ix_field_comments_idempotency_key"),
        ("field_comment_attachments", "ix_field_comment_attachments_idempotency_key"),
        ("document_access_logs", "ix_document_access_logs_idempotency_key"),
        ("reports", "ix_reports_idempotency_key"),
        ("handovers", "ix_handovers_idempotency_key"),
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


def _ensure_handover_source_columns(database: Database) -> None:
    if not database.database_url.startswith("sqlite"):
        return
    columns = {
        "entry_source": "VARCHAR(30) NOT NULL DEFAULT 'field_user'",
        "device_id": "VARCHAR(64)",
    }
    with database.engine.begin() as connection:
        existing = {row[1] for row in connection.execute(text("PRAGMA table_info(handovers)"))}
        if not existing:
            return
        for name, definition in columns.items():
            if name not in existing:
                connection.execute(text(f"ALTER TABLE handovers ADD COLUMN {name} {definition}"))


def _ensure_field_comment_review_columns(database: Database) -> None:
    if not database.database_url.startswith("sqlite"):
        return
    columns = {
        "assigned_to": "VARCHAR(64)",
        "review_due_at": "DATETIME",
        "last_transition_reason": "TEXT",
        "conflict_flag": "BOOLEAN NOT NULL DEFAULT 0",
        "conflict_basis": "TEXT",
        "selected_at": "DATETIME",
        "review_revision": "INTEGER NOT NULL DEFAULT 1",
    }
    with database.engine.begin() as connection:
        existing = {row[1] for row in connection.execute(text("PRAGMA table_info(field_comments)"))}
        if not existing:
            return
        for name, definition in columns.items():
            if name not in existing:
                connection.execute(text(f"ALTER TABLE field_comments ADD COLUMN {name} {definition}"))


def _ensure_report_source_trace_columns(database: Database) -> None:
    if not database.database_url.startswith("sqlite"):
        return
    with database.engine.begin() as connection:
        existing = {row[1] for row in connection.execute(text("PRAGMA table_info(report_sources)"))}
        if not existing:
            return
        if "trace_id" not in existing:
            connection.execute(text("ALTER TABLE report_sources ADD COLUMN trace_id VARCHAR(64)"))
        if "source_hash_sha256" not in existing:
            connection.execute(text("ALTER TABLE report_sources ADD COLUMN source_hash_sha256 VARCHAR(64)"))
        if "source_revision" not in existing:
            connection.execute(text("ALTER TABLE report_sources ADD COLUMN source_revision INTEGER"))
        missing_trace_count = connection.scalar(
            text("SELECT COUNT(*) FROM report_sources WHERE trace_id IS NULL OR trace_id = ''")
        ) or 0
        if missing_trace_count:
            connection.execute(
                text(
                    "UPDATE report_sources "
                    "SET trace_id = 'legacy-report-source-' || id "
                    "WHERE trace_id IS NULL OR trace_id = ''"
                )
            )
        missing_hash_count = connection.scalar(
            text(
                "SELECT COUNT(*) FROM report_sources "
                "WHERE source_hash_sha256 IS NULL OR source_hash_sha256 = ''"
            )
        ) or 0
        if missing_hash_count:
            connection.execute(
                text(
                    "UPDATE report_sources "
                    "SET source_hash_sha256 = lower(hex(randomblob(32))) "
                    "WHERE source_hash_sha256 IS NULL OR source_hash_sha256 = ''"
                )
            )
        connection.execute(
            text("CREATE UNIQUE INDEX IF NOT EXISTS ix_report_sources_trace_id ON report_sources (trace_id)")
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_report_sources_source_hash_sha256 "
                "ON report_sources (source_hash_sha256)"
            )
        )


def _ensure_report_aggregate_columns(database: Database) -> None:
    if not database.database_url.startswith("sqlite"):
        return
    columns = {
        "report_revision": "INTEGER NOT NULL DEFAULT 1",
        "content_hash_sha256": "VARCHAR(64)",
        "source_set_hash_sha256": "VARCHAR(64)",
    }
    with database.engine.begin() as connection:
        existing = {row[1] for row in connection.execute(text("PRAGMA table_info(reports)"))}
        if not existing:
            return
        for name, definition in columns.items():
            if name not in existing:
                connection.execute(text(f"ALTER TABLE reports ADD COLUMN {name} {definition}"))


def _ensure_auth_session_device_column(database: Database) -> None:
    if not database.database_url.startswith("sqlite"):
        return

    with database.engine.begin() as connection:
        existing_columns = {
            row[1] for row in connection.execute(text("PRAGMA table_info(auth_sessions)"))
        }
        if not existing_columns or "device_id" in existing_columns:
            return
        connection.execute(text("ALTER TABLE auth_sessions ADD COLUMN device_id VARCHAR(64)"))


def _ensure_document_access_log_reason_column(database: Database) -> None:
    if not database.database_url.startswith("sqlite"):
        return

    with database.engine.begin() as connection:
        existing_columns = {
            row[1] for row in connection.execute(text("PRAGMA table_info(document_access_logs)"))
        }
        if existing_columns and "reason" not in existing_columns:
            connection.execute(text("ALTER TABLE document_access_logs ADD COLUMN reason VARCHAR(255)"))


def _ensure_document_revision(database: Database) -> None:
    if not database.database_url.startswith("sqlite"):
        return

    with database.engine.begin() as connection:
        existing_columns = {
            row[1] for row in connection.execute(text("PRAGMA table_info(documents)"))
        }
        if existing_columns and "revision" not in existing_columns:
            connection.execute(
                text("ALTER TABLE documents ADD COLUMN revision INTEGER NOT NULL DEFAULT 1")
            )
        if existing_columns:
            connection.execute(
                text("UPDATE documents SET revision = 1 WHERE revision IS NULL OR revision < 1")
            )


def _ensure_reconciliation_resolution_status(database: Database) -> None:
    inspector = inspect(database.engine)
    if "reconciliation_items" not in inspector.get_table_names():
        return
    existing = {
        column["name"] for column in inspector.get_columns("reconciliation_items")
    }
    if "resolution_status" in existing:
        return
    with database.engine.begin() as connection:
        connection.execute(
            text("ALTER TABLE reconciliation_items ADD COLUMN resolution_status VARCHAR(30)")
        )


def _ensure_terminal_device_schema(database: Database) -> None:
    if not database.database_url.startswith("sqlite"):
        return

    with database.engine.begin() as connection:
        table_sql = connection.scalar(
            text("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'terminal_devices'")
        )
        if not table_sql:
            return

        existing_columns = {
            row[1] for row in connection.execute(text("PRAGMA table_info(terminal_devices)"))
        }
        required_columns = {"registered_by", "updated_by", "replaced_device_id"}
        if "RETIRED" in table_sql and required_columns.issubset(existing_columns):
            return

        connection.execute(text("PRAGMA foreign_keys=OFF"))
        connection.execute(
            text(
                """
                CREATE TABLE terminal_devices_new (
                    id INTEGER NOT NULL,
                    device_id VARCHAR(64) NOT NULL,
                    device_name VARCHAR(120) NOT NULL,
                    device_mode VARCHAR(30) NOT NULL,
                    location_code VARCHAR(64),
                    group_id VARCHAR(64),
                    status VARCHAR(20) NOT NULL,
                    last_seen_at DATETIME,
                    registered_by VARCHAR(64),
                    updated_by VARCHAR(64),
                    replaced_device_id VARCHAR(64),
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    PRIMARY KEY (id),
                    CONSTRAINT ck_device_mode CHECK (device_mode IN ('viewer', 'admin_support')),
                    CONSTRAINT ck_device_status CHECK (status IN ('ACTIVE', 'INACTIVE', 'RETIRED')),
                    UNIQUE (device_id),
                    FOREIGN KEY(registered_by) REFERENCES user_accounts (user_id),
                    FOREIGN KEY(updated_by) REFERENCES user_accounts (user_id)
                )
                """
            )
        )
        registered_by_sql = "registered_by" if "registered_by" in existing_columns else "NULL"
        updated_by_sql = "updated_by" if "updated_by" in existing_columns else "NULL"
        replaced_device_id_sql = (
            "replaced_device_id" if "replaced_device_id" in existing_columns else "NULL"
        )
        connection.execute(
            text(
                f"""
                INSERT INTO terminal_devices_new (
                    id, device_id, device_name, device_mode, location_code, group_id,
                    status, last_seen_at, registered_by, updated_by, replaced_device_id,
                    created_at, updated_at
                )
                SELECT
                    id, device_id, device_name, device_mode, location_code, group_id,
                    status, last_seen_at, {registered_by_sql}, {updated_by_sql},
                    {replaced_device_id_sql}, created_at, updated_at
                FROM terminal_devices
                """
            )
        )
        connection.execute(text("DROP TABLE terminal_devices"))
        connection.execute(text("ALTER TABLE terminal_devices_new RENAME TO terminal_devices"))
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_terminal_devices_device_id "
                "ON terminal_devices (device_id)"
            )
        )
        connection.execute(text("PRAGMA foreign_keys=ON"))


def _ensure_work_sequence_columns(database: Database) -> None:
    if not database.database_url.startswith("sqlite"):
        return

    targets = {
        "work_sequence_boards": (("board_revision", "INTEGER NOT NULL DEFAULT 1"),),
        "work_sequence_items": (("hold_reason", "TEXT"),),
        "work_sequence_change_history": (
            ("mutation_key", "VARCHAR(160)"),
            ("board_revision", "INTEGER"),
        ),
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
        history_columns = {
            row[1] for row in connection.execute(text("PRAGMA table_info(work_sequence_change_history)"))
        }
        if history_columns:
            connection.execute(text(
                "UPDATE work_sequence_change_history "
                "SET mutation_key = COALESCE(mutation_key, 'legacy:' || change_id), "
                "board_revision = COALESCE(board_revision, 0)"
            ))
            connection.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_work_sequence_history_mutation_key "
                "ON work_sequence_change_history (mutation_key)"
            ))


def _ensure_ai_evidence_snapshot_has_no_candidate_fk(database: Database) -> None:
    if not database.database_url.startswith("sqlite"):
        return
    with database.engine.connect() as connection:
        foreign_keys = connection.execute(
            text("PRAGMA foreign_key_list(ai_query_evidence_candidates)")
        ).fetchall()
        if not any(row[2] == "ai_search_candidates" for row in foreign_keys):
            return
        connection.commit()
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.exec_driver_sql(
            """
            CREATE TABLE ai_query_evidence_candidates_new (
                id INTEGER NOT NULL PRIMARY KEY,
                query_id VARCHAR(64) NOT NULL REFERENCES ai_queries(query_id),
                candidate_id VARCHAR(64) NOT NULL,
                source_type VARCHAR(50) NOT NULL,
                source_id VARCHAR(64) NOT NULL,
                source_version_id VARCHAR(64),
                trace_table VARCHAR(80) NOT NULL,
                trace_id VARCHAR(64) NOT NULL,
                trace_version_id VARCHAR(64),
                rank INTEGER NOT NULL,
                selected_for_prompt BOOLEAN NOT NULL,
                sent_externally BOOLEAN NOT NULL,
                content_hash VARCHAR(64) NOT NULL,
                eligibility_result VARCHAR(30) NOT NULL,
                exclusion_reason VARCHAR(80),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                CONSTRAINT uq_ai_query_evidence UNIQUE (query_id, candidate_id)
            )
            """
        )
        connection.exec_driver_sql(
            """
            INSERT INTO ai_query_evidence_candidates_new
            SELECT id, query_id, candidate_id, source_type, source_id, source_version_id,
                   trace_table, trace_id, trace_version_id, rank, selected_for_prompt,
                   sent_externally, content_hash, eligibility_result, exclusion_reason, created_at
            FROM ai_query_evidence_candidates
            """
        )
        connection.exec_driver_sql("DROP TABLE ai_query_evidence_candidates")
        connection.exec_driver_sql(
            "ALTER TABLE ai_query_evidence_candidates_new RENAME TO ai_query_evidence_candidates"
        )
        connection.exec_driver_sql(
            "CREATE INDEX ix_ai_query_evidence_candidates_query_id ON ai_query_evidence_candidates (query_id)"
        )
        connection.commit()
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")


def _ensure_ai_search_candidate_content_hash(database: Database) -> None:
    if not database.database_url.startswith("sqlite"):
        return
    with database.engine.begin() as connection:
        columns = {row[1] for row in connection.execute(text("PRAGMA table_info(ai_search_candidates)"))}
        if columns and "content_hash" not in columns:
            connection.execute(text("ALTER TABLE ai_search_candidates ADD COLUMN content_hash VARCHAR(64)"))
            connection.execute(
                text(
                    "UPDATE ai_search_candidates SET content_hash = lower(hex(randomblob(32))) "
                    "WHERE content_hash IS NULL"
                )
            )
            connection.execute(
                text("CREATE INDEX IF NOT EXISTS ix_ai_search_candidates_content_hash ON ai_search_candidates (content_hash)")
            )


def _ensure_ai_ground_truth_indexes(database: Database) -> None:
    if not database.database_url.startswith("sqlite"):
        return
    with database.engine.begin() as connection:
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_ai_search_evaluation_cases_case_key_id "
            "ON ai_search_evaluation_cases (case_key, id)"
        ))


def _ensure_ai_field_readiness_sample_review_columns(database: Database) -> None:
    if not database.database_url.startswith("sqlite"):
        return
    with database.engine.begin() as connection:
        columns = {
            row[1]
            for row in connection.execute(
                text("PRAGMA table_info(ai_field_readiness_sample_reviews)")
            )
        }
        if columns and "resolved_review_ids_json" not in columns:
            connection.execute(
                text(
                    "ALTER TABLE ai_field_readiness_sample_reviews "
                    "ADD COLUMN resolved_review_ids_json TEXT"
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


def _ensure_ai_operations_columns(database: Database) -> None:
    if not database.database_url.startswith("sqlite"):
        return
    additions = {
        "ai_prompt_versions": {
            "reviewed_by": "VARCHAR(64)",
            "reviewed_at": "DATETIME",
            "activated_at": "DATETIME",
        },
        "ai_queries": {
            "customer_scope": "VARCHAR(120) NOT NULL DEFAULT 'DEFAULT'",
            "site_scope": "VARCHAR(120) NOT NULL DEFAULT 'DEFAULT'",
            "prompt_snapshot_json": "TEXT",
            "approval_snapshot_json": "TEXT",
            "response_retention_until": "DATETIME",
            "immediate_expiry_operation_key": "VARCHAR(160)",
            "immediate_expiry_requested_at": "DATETIME",
            "immediate_expiry_reason": "TEXT",
        },
        "ai_call_attempts": {"cost_micros": "INTEGER"},
        "ai_transfer_approvals": {
            "allowed_purposes": (
                "TEXT NOT NULL DEFAULT '[\"EVIDENCE_SEARCH\", \"EVIDENCE_SUMMARY\"]'"
            ),
        },
        "ai_retention_audits": {"operation_key": "VARCHAR(160)"},
        "ai_query_legal_holds": {
            "operation_key": "VARCHAR(160)",
            "release_operation_key": "VARCHAR(160)",
        },
        "ai_sensitive_data_policies": {
            "content_hash": "VARCHAR(64) NOT NULL DEFAULT ''",
            "status": "VARCHAR(30) NOT NULL DEFAULT 'ACTIVE'",
            "state_revision": "INTEGER NOT NULL DEFAULT 1",
            "reviewed_by": "VARCHAR(64)",
            "reviewed_at": "DATETIME",
            "approved_by": "VARCHAR(64)",
            "approved_at": "DATETIME",
            "activated_by": "VARCHAR(64)",
            "activated_at": "DATETIME",
            "replaced_by_policy_id": "VARCHAR(64)",
            "approval_withdrawn_by": "VARCHAR(64)",
            "approval_withdrawn_at": "DATETIME",
            "retired_by": "VARCHAR(64)",
            "retired_at": "DATETIME",
            "updated_at": "DATETIME",
        },
    }
    with database.engine.begin() as connection:
        for table_name, columns in additions.items():
            existing = {
                row[1] for row in connection.execute(text(f"PRAGMA table_info({table_name})"))
            }
            if not existing:
                continue
            for column_name, definition in columns.items():
                if column_name not in existing:
                    connection.execute(
                        text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")
                    )
        connection.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_ai_queries_immediate_expiry_operation_key "
            "ON ai_queries (immediate_expiry_operation_key)"
        ))
        connection.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_ai_retention_audits_operation_key "
            "ON ai_retention_audits (operation_key)"
        ))
        connection.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_ai_query_legal_holds_operation_key "
            "ON ai_query_legal_holds (operation_key)"
        ))
        connection.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_ai_query_legal_holds_release_operation_key "
            "ON ai_query_legal_holds (release_operation_key)"
        ))
        connection.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_ai_query_legal_holds_active_query "
            "ON ai_query_legal_holds (query_id) WHERE status = 'ACTIVE'"
        ))
        connection.execute(text(
            "UPDATE ai_sensitive_data_policies SET updated_at = created_at "
            "WHERE updated_at IS NULL"
        ))


def _assert_database_schema_ownership(database: Database) -> None:
    """Refuse to merge the FastAPI schema into a WPF local SQLite database."""
    if not database.database_url.startswith("sqlite"):
        return

    with database.engine.connect() as connection:
        document_version_columns = {
            row[1] for row in connection.execute(text("PRAGMA table_info(document_versions)"))
        }
        document_columns = {
            row[1] for row in connection.execute(text("PRAGMA table_info(documents)"))
        }

    is_wpf_local_schema = (
        bool(document_version_columns)
        and "version_no" in document_version_columns
        and "file_name" in document_version_columns
        and "version_id" not in document_version_columns
        and "folder_id" in document_columns
    )
    if is_wpf_local_schema:
        raise RuntimeError(
            "FLOWNOTE_DATABASE_URL points to a WPF local SQLite database. "
            "FastAPI and WPF must use separate database files; no server tables were created."
        )


def initialize_database(database: Database) -> None:
    _assert_database_schema_ownership(database)
    Base.metadata.create_all(bind=database.engine)
    _ensure_user_account_columns(database)
    _ensure_user_account_role_constraint(database)
    _ensure_idempotency_columns(database)
    _ensure_handover_source_columns(database)
    _ensure_field_comment_review_columns(database)
    _ensure_report_source_trace_columns(database)
    _ensure_report_aggregate_columns(database)
    _ensure_terminal_device_schema(database)
    _ensure_auth_session_device_column(database)
    _ensure_document_access_log_reason_column(database)
    _ensure_document_revision(database)
    _ensure_reconciliation_resolution_status(database)
    _ensure_work_sequence_columns(database)
    _ensure_ai_evidence_snapshot_has_no_candidate_fk(database)
    _ensure_ai_search_candidate_content_hash(database)
    _ensure_ai_ground_truth_indexes(database)
    _ensure_ai_field_readiness_sample_review_columns(database)
    _ensure_ai_operations_columns(database)
    with database.session() as session:
        identity = session.get(ServerIdentity, 1)
        if identity is None:
            session.add(
                ServerIdentity(
                    singleton_id=1,
                    server_instance_id=f"srv-{secrets.token_hex(16)}",
                    server_epoch=1,
                    schema_contract=1,
                    api_contract_min=1,
                    api_contract_max=1,
                )
            )
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
        common_receipt_migration = session.scalar(
            select(SchemaMigration).where(
                SchemaMigration.version == COMMON_MUTATION_RECEIPT_SCHEMA_VERSION
            )
        )
        if common_receipt_migration is None:
            session.add(
                SchemaMigration(
                    version=COMMON_MUTATION_RECEIPT_SCHEMA_VERSION,
                    description="Add common audit event envelopes and sync mutation receipts",
                )
            )
        session.commit()
    _seed_default_admin_account(database)
