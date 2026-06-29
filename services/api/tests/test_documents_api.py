from __future__ import annotations

import hashlib
import shutil
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.platypus import Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from sqlalchemy import select

from app.core.config import Settings
from app.db.models import Document, DocumentTag, DocumentVersion, FileObject, TagDefinition, UserAccount
from app.main import create_app


API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = API_ROOT.parents[1]
TEST_DB_PATH = API_ROOT / "data" / "flownote.test.sqlite3"
TEST_DATABASE_URL = f"sqlite:///{TEST_DB_PATH.as_posix()}"
TEST_STORAGE_ROOT = API_ROOT / "storage" / "document-registration-tests"
TEST_ARTIFACT_ROOT = API_ROOT / "data" / "test-artifacts" / "document-registration-2026-06-24"
EXCEL_SAMPLE_SOURCE = (
    REPO_ROOT
    / "apps"
    / "windows"
    / "src"
    / "FlowNote.Windows.App"
    / "Data"
    / "Files"
    / "Samples"
    / "문서-설비점검표-프레스A.xlsx"
)


def create_test_client() -> TestClient:
    app_settings = Settings(
        _env_file=None,
        environment="test",
        database_url=TEST_DATABASE_URL,
        test_database_url=TEST_DATABASE_URL,
        storage_root=str(TEST_STORAGE_ROOT),
    )
    return TestClient(create_app(app_settings))


def auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "1234"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def ensure_test_user(client: TestClient) -> None:
    with client.app.state.database.session() as session:
        existing = session.scalar(
            select(UserAccount).where(UserAccount.user_id == "user-test-admin")
        )
        if existing is None:
            session.add(
                UserAccount(
                    user_id="user-test-admin",
                    username="test-admin",
                    login_id="test-admin",
                    display_name="Test Document Admin",
                    role="admin",
                    password_hash="test-only-password-hash",
                    is_active=True,
                )
            )
            session.commit()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_sample_pdf(path: Path, *, title: str) -> None:
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(path), pagesize=A4, rightMargin=36, leftMargin=36)
    rows = [
        ["Area", "Line A press cell"],
        ["Equipment", "PRESS-A-1200"],
        ["Check point", "Hydraulic pressure, guard sensor, mold alignment"],
        ["Shift note", "Keep revision reason when the field file changes."],
    ]
    table = Table(rows, colWidths=[110, 330])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#E5E7EB")),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#111827")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#9CA3AF")),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story = [
        Paragraph(title, styles["Title"]),
        Paragraph("Factory document sample for FlowNote registration test.", styles["BodyText"]),
        Spacer(1, 12),
        table,
    ]
    doc.build(story)


def build_sample_image(path: Path) -> None:
    image = Image.new("RGB", (900, 600), "#F3F4F6")
    draw = ImageDraw.Draw(image)
    draw.rectangle((40, 40, 860, 560), outline="#374151", width=4)
    draw.rectangle((80, 110, 820, 250), fill="#DBEAFE", outline="#1D4ED8", width=3)
    draw.rectangle((120, 330, 340, 470), fill="#FEF3C7", outline="#D97706", width=3)
    draw.rectangle((520, 330, 780, 470), fill="#DCFCE7", outline="#16A34A", width=3)
    draw.text((90, 65), "PACK-LINE-02 label inspection photo", fill="#111827")
    draw.text((105, 155), "Conveyor label camera position", fill="#111827")
    draw.text((140, 385), "Reject box", fill="#111827")
    draw.text((555, 385), "OK tray", fill="#111827")
    image.save(path, format="PNG")


def prepare_factory_sample_files() -> tuple[Path, Path, Path, Path]:
    run_dir = TEST_ARTIFACT_ROOT / datetime.now().strftime("%Y%m%d-%H%M%S") / uuid4().hex[:8]
    sample_dir = run_dir / "sample-files"
    sample_dir.mkdir(parents=True, exist_ok=True)

    pdf_path = sample_dir / "작업표준서-프레스A-금형교환.pdf"
    pdf_v2_path = sample_dir / "작업표준서-프레스A-금형교환-v2.pdf"
    image_path = sample_dir / "사진-포장라인-라벨검사.png"
    excel_path = sample_dir / EXCEL_SAMPLE_SOURCE.name

    build_sample_pdf(pdf_path, title="Press A Mold Change Standard")
    build_sample_pdf(pdf_v2_path, title="Press A Mold Change Standard - Guard Sensor Update")
    build_sample_image(image_path)
    shutil.copy2(EXCEL_SAMPLE_SOURCE, excel_path)
    return pdf_path, pdf_v2_path, excel_path, image_path


def post_document(client: TestClient, file_path: Path, *, title: str, document_type: str) -> dict:
    with file_path.open("rb") as file:
        response = client.post(
            "/api/v1/documents",
            headers=auth_headers(client),
            data={
                "title": title,
                "description": "Factory floor sample registration test",
                "documentType": document_type,
                "ownerId": "user-test-admin",
                "categoryId": "line-a",
                "versionLabel": "v1",
                "changeReason": "Initial field document registration test.",
                "createdBy": "user-test-admin",
                "tags": ["line-a", "press-a", "mold-change"],
            },
            files={"file": (file_path.name, file, "application/octet-stream")},
        )
    assert response.status_code == 201, response.text
    return response.json()


def test_register_factory_files_and_document_versions_are_preserved() -> None:
    pdf_path, pdf_v2_path, excel_path, image_path = prepare_factory_sample_files()
    run_log = pdf_path.parents[1] / "document-registration-log.txt"

    with create_test_client() as client:
        ensure_test_user(client)
        pdf_doc = post_document(
            client,
            pdf_path,
            title="Press A mold change work standard",
            document_type="work_instruction",
        )
        excel_doc = post_document(
            client,
            excel_path,
            title="Press A equipment inspection sheet",
            document_type="inspection_sheet",
        )
        image_doc = post_document(
            client,
            image_path,
            title="Packaging line label inspection photo",
            document_type="field_photo",
        )

        with pdf_v2_path.open("rb") as file:
            version_response = client.post(
                f"/api/v1/documents/{pdf_doc['document_id']}/versions",
                headers=auth_headers(client),
                data={
                    "versionLabel": "v2",
                    "changeReason": "Guard sensor confirmation step added after field review.",
                    "createdBy": "user-test-admin",
                },
                files={"file": (pdf_v2_path.name, file, "application/pdf")},
            )
        assert version_response.status_code == 201, version_response.text
        second_version = version_response.json()

        detail_response = client.get(
            f"/api/v1/documents/{pdf_doc['document_id']}",
            headers=auth_headers(client),
        )
        assert detail_response.status_code == 200
        detail = detail_response.json()
        assert detail["latest_version"]["version_no"] == 2
        assert detail["latest_version"]["change_reason"] == (
            "Guard sensor confirmation step added after field review."
        )
        assert detail["tags"] == ["line-a", "mold-change", "press-a"]

        versions_response = client.get(
            f"/api/v1/documents/{pdf_doc['document_id']}/versions",
            headers=auth_headers(client),
        )
        assert versions_response.status_code == 200
        versions = versions_response.json()
        assert [version["version_no"] for version in versions] == [2, 1]
        assert versions[0]["is_latest"] is True
        assert versions[1]["is_latest"] is False
        assert versions[1]["version_status"] == "SUPERSEDED"

        tag_update_response = client.put(
            f"/api/v1/documents/{pdf_doc['document_id']}/tags",
            headers=auth_headers(client),
            json=["line-a", "guard-sensor", "press-a"],
        )
        assert tag_update_response.status_code == 200, tag_update_response.text
        assert tag_update_response.json()["tags"] == ["guard-sensor", "line-a", "press-a"]

        tags_response = client.get("/api/v1/tags")
        assert tags_response.status_code == 200
        tag_names = {tag["name"] for tag in tags_response.json()}
        assert {"line-a", "press-a", "guard-sensor"} <= tag_names

        with client.app.state.database.session() as session:
            saved_documents = session.scalars(
                select(Document).where(
                    Document.document_id.in_(
                        [pdf_doc["document_id"], excel_doc["document_id"], image_doc["document_id"]]
                    )
                )
            ).all()
            assert len(saved_documents) == 3
            saved_versions = session.scalars(
                select(DocumentVersion).where(
                    DocumentVersion.document_id == pdf_doc["document_id"]
                )
            ).all()
            assert len(saved_versions) == 2
            stored_files = session.scalars(select(FileObject)).all()
            storage_keys = {file_object.storage_key for file_object in stored_files}
            saved_tag_names = {
                tag.name
                for tag in session.scalars(select(TagDefinition)).all()
            }
            saved_document_tags = session.scalars(
                select(DocumentTag).where(DocumentTag.document_id == pdf_doc["document_id"])
            ).all()
            assert {"line-a", "press-a", "guard-sensor"} <= saved_tag_names
            assert len(saved_document_tags) == 3

        for uploaded in [pdf_doc["latest_version"], excel_doc["latest_version"], image_doc["latest_version"]]:
            storage_key = uploaded["file"]["storage_key"]
            assert storage_key in storage_keys
            stored_path = TEST_STORAGE_ROOT / Path(storage_key)
            assert stored_path.exists()
            source_path = {
                pdf_path.name: pdf_path,
                excel_path.name: excel_path,
                image_path.name: image_path,
            }[uploaded["file"]["original_filename"]]
            assert uploaded["file"]["hash_sha256"] == file_sha256(source_path)
            assert uploaded["file"]["size_bytes"] == source_path.stat().st_size

        stored_v2_path = TEST_STORAGE_ROOT / Path(second_version["file"]["storage_key"])
        assert stored_v2_path.exists()
        assert second_version["file"]["hash_sha256"] == file_sha256(pdf_v2_path)

    run_log.write_text(
        "\n".join(
            [
                "FlowNote document registration integration test",
                f"generated_at={datetime.now().isoformat(timespec='seconds')}",
                f"test_db={TEST_DB_PATH}",
                f"storage_root={TEST_STORAGE_ROOT}",
                f"pdf_sample={pdf_path}",
                f"pdf_version2_sample={pdf_v2_path}",
                f"excel_sample={excel_path}",
                f"image_sample={image_path}",
                f"pdf_document_id={pdf_doc['document_id']}",
                f"excel_document_id={excel_doc['document_id']}",
                f"image_document_id={image_doc['document_id']}",
            ]
        ),
        encoding="utf-8",
    )


def test_document_version_change_reason_is_required() -> None:
    pdf_path, _, _, _ = prepare_factory_sample_files()

    with create_test_client() as client:
        ensure_test_user(client)
        created = post_document(
            client,
            pdf_path,
            title="Press A safety work memo",
            document_type="safety_memo",
        )
        with pdf_path.open("rb") as file:
            response = client.post(
                f"/api/v1/documents/{created['document_id']}/versions",
                headers=auth_headers(client),
                data={"versionLabel": "v2", "changeReason": "   "},
                files={"file": (pdf_path.name, file, "application/pdf")},
            )

    assert response.status_code == 422


def test_document_registration_requires_authentication() -> None:
    pdf_path, _, _, _ = prepare_factory_sample_files()

    with create_test_client() as client:
        with pdf_path.open("rb") as file:
            response = client.post(
                "/api/v1/documents",
                data={
                    "title": "Unauthenticated document registration",
                    "documentType": "work_instruction",
                    "changeReason": "This should be rejected without an auth token.",
                },
                files={"file": (pdf_path.name, file, "application/pdf")},
            )

    assert response.status_code == 401


def test_document_registration_allows_missing_user_reference_after_authentication() -> None:
    pdf_path, _, _, _ = prepare_factory_sample_files()

    with create_test_client() as client:
        with pdf_path.open("rb") as file:
            response = client.post(
                "/api/v1/documents",
                headers=auth_headers(client),
                data={
                    "title": "Authenticated document registration without explicit user reference",
                    "documentType": "work_instruction",
                    "changeReason": "Registering with authentication but no owner or createdBy.",
                },
                files={"file": (pdf_path.name, file, "application/pdf")},
            )

    assert response.status_code == 201, response.text
    created = response.json()
    assert created["owner_id"] is None
    assert created["latest_version"]["created_by"] is None
    assert created["latest_version"]["file"]["size_bytes"] == pdf_path.stat().st_size


def test_document_registration_rejects_unknown_user_reference() -> None:
    pdf_path, _, _, _ = prepare_factory_sample_files()
    stored_files_before = {
        path.relative_to(TEST_STORAGE_ROOT)
        for path in TEST_STORAGE_ROOT.rglob("*")
        if path.is_file()
    }

    with create_test_client() as client:
        with pdf_path.open("rb") as file:
            response = client.post(
                "/api/v1/documents",
                headers=auth_headers(client),
                data={
                    "title": "Unknown owner upload",
                    "documentType": "work_instruction",
                    "ownerId": "user-does-not-exist",
                    "changeReason": "This should fail before storing the file.",
                },
                files={"file": (pdf_path.name, file, "application/pdf")},
            )

    stored_files_after = {
        path.relative_to(TEST_STORAGE_ROOT)
        for path in TEST_STORAGE_ROOT.rglob("*")
        if path.is_file()
    }
    assert response.status_code == 422
    assert response.json()["detail"] == "ownerId must reference an existing user_id."
    assert stored_files_after == stored_files_before
