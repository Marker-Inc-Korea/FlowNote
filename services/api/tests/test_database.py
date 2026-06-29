from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select

from app.core.config import Settings
from app.db.init_db import DEFAULT_ADMIN_PASSWORD, DEFAULT_ADMIN_USERNAME
from app.db.init_db import INITIAL_SCHEMA_VERSION, hash_password_for_dev
from app.db.models import Document, DocumentVersion, FieldNote, FileObject, Role
from app.db.models import SchemaMigration, UserAccount, UserRole
from app.main import create_app


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


def test_app_startup_creates_mvp_schema() -> None:
    expected_tables = {
        "comment_templates",
        "document_access_logs",
        "document_tags",
        "document_versions",
        "documents",
        "field_note_attachments",
        "field_notes",
        "file_objects",
        "operator_profiles",
        "report_sources",
        "reports",
        "roles",
        "schema_migrations",
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

        with client.app.state.database.session() as session:
            migration = session.scalar(
                select(SchemaMigration).where(SchemaMigration.version == INITIAL_SCHEMA_VERSION)
            )
            assert migration is not None

            admin_account = session.scalar(
                select(UserAccount).where(UserAccount.username == DEFAULT_ADMIN_USERNAME)
            )
            assert admin_account is not None
            assert admin_account.user_id == "user-admin"
            assert admin_account.display_name == "FlowNote Admin"
            assert admin_account.role == "admin"
            assert admin_account.password_hash == hash_password_for_dev(DEFAULT_ADMIN_PASSWORD)
            assert admin_account.is_active is True


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


def test_mvp_schema_accepts_document_version_and_field_note() -> None:
    suffix = uuid4().hex
    user_id = f"user-test-{suffix}"
    role_id = f"role-test-{suffix}"
    document_id = f"doc-test-{suffix}"
    version_id = f"ver-test-{suffix}"
    note_id = f"note-test-{suffix}"

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
                FieldNote(
                    note_id=note_id,
                    document_id=document_id,
                    note_type="issue",
                    input_mode="free_text",
                    raw_content="Test field note",
                    author_id=user_id,
                    entry_source="field_user",
                )
            )
            session.commit()

        with client.app.state.database.session() as session:
            saved_note = session.scalar(select(FieldNote).where(FieldNote.note_id == note_id))
            assert saved_note is not None
            assert saved_note.document_id == document_id
