from pathlib import Path
import sqlite3
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import func, inspect, select, text

from app.core.config import Settings
from app.db.init_db import (
    COMMON_MUTATION_RECEIPT_SCHEMA_VERSION,
    DEFAULT_ADMIN_USERNAME,
    initialize_database,
)
from app.db.init_db import INITIAL_SCHEMA_VERSION, verify_password
from app.db.models import ActivityHistory, Document, DocumentVersion, FieldComment, FileObject, Role
from app.db.models import SchemaMigration, UserAccount, UserRole
from app.main import create_app
from app.db.session import Database


API_ROOT = Path(__file__).resolve().parents[1]
TEST_DB_PATH = API_ROOT / "data" / "flownote.test.sqlite3"
TEST_DATABASE_URL = f"sqlite:///{TEST_DB_PATH.as_posix()}"


def create_test_client() -> TestClient:
    app_settings = Settings(
        _env_file=None,
        environment="test",
        database_url=TEST_DATABASE_URL,
        test_database_url=TEST_DATABASE_URL,
        storage_root=str(API_ROOT / "storage"),
    )
    return TestClient(create_app(app_settings))


def test_app_startup_creates_mvp_schema(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="FLOWNOTE_ACCESS_TOKEN_SECRET"):
        Settings(_env_file=None, environment="production")
    production_settings = Settings(
        _env_file=None,
        environment="production",
        access_token_secret="production-specific-secret-with-32-chars",
    )
    assert production_settings.environment == "production"

    expected_tables = {
        "ai_search_candidates",
        "ai_search_evaluation_runs",
        "ai_search_evaluation_cases",
        "ai_search_ground_truth_cases",
        "ai_search_ground_truth_provenance",
        "ai_field_readiness_sample_reviews",
        "ai_queries",
        "ai_query_evidence_candidates",
        "ai_query_citations",
        "ai_query_legal_holds",
        "ai_prompt_versions",
        "ai_call_attempts",
        "ai_sensitive_data_policies",
        "ai_transfer_approvals",
        "audit_event_envelopes",
        "comment_templates",
        "controlled_copy_grants",
        "document_access_logs",
        "document_tags",
        "document_tag_revisions",
        "document_versions",
        "documents",
        "field_comment_attachments",
        "field_comments",
        "file_objects",
        "channel_messages",
        "handover_receipts",
        "handovers",
        "notification_channel_members",
        "notification_channels",
        "operator_profiles",
        "report_sources",
        "reports",
        "roles",
        "schema_migrations",
        "sync_mutation_receipts",
        "tag_definitions",
        "terminal_devices",
        "user_accounts",
        "user_roles",
        "work_record_versions",
        "work_records",
        "work_sequence_boards",
        "work_sequence_change_history",
        "work_sequence_items",
        "work_sequence_notification_candidates",
    }

    with create_test_client() as client:
        response = client.get("/api/v1/health/db")

        assert response.status_code == 200
        assert response.json() == {"status": "ok", "database": "ok"}
        assert TEST_DB_PATH.exists()

        table_names = set(inspect(client.app.state.database.engine).get_table_names())
        assert expected_tables <= table_names

        with client.app.state.database.engine.connect() as connection:
            assert connection.scalar(text("PRAGMA journal_mode")) == "wal"
            assert connection.scalar(text("PRAGMA busy_timeout")) == 30_000
            assert connection.scalar(text("PRAGMA foreign_keys")) == 1

        with client.app.state.database.session() as session:
            migration = session.scalar(
                select(SchemaMigration).where(SchemaMigration.version == INITIAL_SCHEMA_VERSION)
            )
            assert migration is not None
            common_receipt_migration = session.scalar(
                select(SchemaMigration).where(
                    SchemaMigration.version == COMMON_MUTATION_RECEIPT_SCHEMA_VERSION
                )
            )
            assert common_receipt_migration is not None

            admin_account = session.scalar(
                select(UserAccount).where(UserAccount.username == DEFAULT_ADMIN_USERNAME)
            )
            assert admin_account is not None
            assert admin_account.user_id == "user-admin"
            assert admin_account.display_name == "FlowNote Admin"
            assert admin_account.role == "admin"
            assert verify_password("1234", admin_account.password_hash)
            assert admin_account.is_active is True

    fresh_server_path = tmp_path / "fresh-server.sqlite3"
    fresh_server = Database(f"sqlite:///{fresh_server_path.as_posix()}")
    try:
        with pytest.raises(RuntimeError, match="FLOWNOTE_INITIAL_ADMIN_PASSWORD"):
            initialize_database(fresh_server)
        initialize_database(fresh_server, "initial-admin-password")
        with fresh_server.session() as session:
            fresh_admin = session.scalar(
                select(UserAccount).where(UserAccount.username == DEFAULT_ADMIN_USERNAME)
            )
            assert fresh_admin is not None
            assert verify_password("initial-admin-password", fresh_admin.password_hash)
            assert fresh_admin.must_change_password is True
    finally:
        fresh_server.dispose()

    wpf_database_path = tmp_path / "flownote.local.sqlite"
    with sqlite3.connect(wpf_database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE documents (
                id INTEGER PRIMARY KEY,
                document_id TEXT NOT NULL UNIQUE,
                folder_id INTEGER NOT NULL
            );
            CREATE TABLE document_versions (
                id INTEGER PRIMARY KEY,
                document_id TEXT NOT NULL,
                version_no INTEGER NOT NULL,
                file_name TEXT NOT NULL,
                local_path TEXT
            );
            """
        )

    misconfigured_database = Database(f"sqlite:///{wpf_database_path.as_posix()}")
    try:
        with pytest.raises(RuntimeError, match="WPF local SQLite"):
            initialize_database(misconfigured_database)
    finally:
        misconfigured_database.dispose()

    with sqlite3.connect(wpf_database_path) as connection:
        controlled_copy_table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='controlled_copy_grants'"
        ).fetchone()
    assert controlled_copy_table is None


def test_app_startup_seeds_default_admin_account_once() -> None:
    for _ in range(2):
        with create_test_client() as client:
            response = client.get("/api/v1/health/db")
            assert response.status_code == 200

    with create_test_client() as client:
        with client.app.state.database.session() as session:
            admin_count = session.scalar(
                select(func.count()).select_from(UserAccount).where(
                    UserAccount.username == DEFAULT_ADMIN_USERNAME
                )
            )
            assert admin_count == 1


def test_common_receipt_migration_preserves_legacy_audit_and_separate_wpf_queue() -> None:
    migration_db_path = API_ROOT / "data" / "flownote.common-receipt-migration.test.sqlite3"
    wpf_queue_db_path = API_ROOT / "data" / "flownote.wpf-queue-preservation.test.sqlite3"
    database = Database(f"sqlite:///{migration_db_path.as_posix()}")
    legacy_history_id = "hist-common-receipt-migration-preserved"
    try:
        SchemaMigration.__table__.create(database.engine, checkfirst=True)
        UserAccount.__table__.create(database.engine, checkfirst=True)
        ActivityHistory.__table__.create(database.engine, checkfirst=True)
        with database.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT OR IGNORE INTO schema_migrations (version, description) "
                    "VALUES (:version, :description)"
                ),
                {
                    "version": INITIAL_SCHEMA_VERSION,
                    "description": "Legacy schema before common receipt migration",
                },
            )
            connection.execute(
                text(
                    "INSERT OR IGNORE INTO activity_history "
                    "(history_id, event_type, target_type, target_id, message) "
                    "VALUES (:history_id, :event_type, :target_type, :target_id, :message)"
                ),
                {
                    "history_id": legacy_history_id,
                    "event_type": "legacy.preserved",
                    "target_type": "document",
                    "target_id": "doc-legacy-preserved",
                    "message": "Legacy audit row must remain unchanged.",
                },
            )
        with sqlite3.connect(wpf_queue_db_path) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS server_sync_queue (
                    id INTEGER PRIMARY KEY,
                    operation_key TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL
                );
                INSERT OR IGNORE INTO server_sync_queue (operation_key, status)
                VALUES ('preserved-wpf-queue-operation', 'FAILED');
                """
            )

        initialize_database(
            database,
            "1234",
            allow_insecure_test_password=True,
        )

        with database.session() as session:
            legacy = session.scalar(
                select(ActivityHistory).where(
                    ActivityHistory.history_id == legacy_history_id
                )
            )
            migration = session.scalar(
                select(SchemaMigration).where(
                    SchemaMigration.version == COMMON_MUTATION_RECEIPT_SCHEMA_VERSION
                )
            )
            assert legacy is not None
            assert legacy.message == "Legacy audit row must remain unchanged."
            assert migration is not None
        with sqlite3.connect(wpf_queue_db_path) as connection:
            queue_row = connection.execute(
                "SELECT operation_key, status FROM server_sync_queue "
                "WHERE operation_key = 'preserved-wpf-queue-operation'"
            ).fetchone()
        assert queue_row == ("preserved-wpf-queue-operation", "FAILED")
    finally:
        database.dispose()


def test_mvp_schema_accepts_document_version_and_field_comment() -> None:
    suffix = uuid4().hex
    user_id = f"user-test-{suffix}"
    role_id = f"role-test-{suffix}"
    document_id = f"doc-test-{suffix}"
    version_id = f"ver-test-{suffix}"
    comment_id = f"comment-test-{suffix}"

    with create_test_client() as client:
        with client.app.state.database.session() as session:
            session.add(
                UserAccount(
                    user_id=user_id,
                    username=f"login-test-{suffix}",
                    login_id=f"login-test-{suffix}",
                    display_name="Test User",
                    role="viewer",
                    password_hash="test-only-password-hash",
                    is_active=True,
                )
            )
            session.add(Role(role_id=role_id, role_name="Test Role"))
            session.add(UserRole(user_id=user_id, role_id=role_id))

            file_object = FileObject(
                storage_key=f"tests/{suffix}/document.txt",
                original_filename="document.txt",
                extension=".txt",
                mime_type="text/plain",
                file_family="text",
                size_bytes=12,
                hash_sha256="0" * 64,
            )
            session.add(file_object)
            session.flush()

            session.add(
                Document(
                    document_id=document_id,
                    title="Test document",
                    document_type="work_instruction",
                    owner_id=user_id,
                    status="WORKING",
                )
            )
            session.add(
                DocumentVersion(
                    version_id=version_id,
                    document_id=document_id,
                    file_object_id=file_object.id,
                    version_no=1,
                    version_label="v1",
                    change_reason="Initial test version",
                    created_by=user_id,
                )
            )
            session.add(
                FieldComment(
                    comment_id=comment_id,
                    document_id=document_id,
                    comment_type="issue",
                    input_mode="free_text",
                    raw_content="Test field comment",
                    author_id=user_id,
                    entry_source="field_user",
                )
            )
            session.commit()

        with client.app.state.database.session() as session:
            saved_comment = session.scalar(select(FieldComment).where(FieldComment.comment_id == comment_id))
            assert saved_comment is not None
            assert saved_comment.document_id == document_id
