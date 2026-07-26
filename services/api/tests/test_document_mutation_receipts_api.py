from uuid import uuid4

from sqlalchemy import select

from app.db.models import ActivityHistory, Document, DocumentMutationReceipt
from test_documents_api import (
    auth_headers,
    create_test_client,
    prepare_factory_sample_files,
)

def test_document_authority_mutations_replay_one_receipt_without_extra_revision() -> None:
    pdf_path, _, _, _ = prepare_factory_sample_files()
    suffix = uuid4().hex
    with create_test_client() as client:
        headers = auth_headers(client)
        with pdf_path.open("rb") as file:
            created_response = client.post(
                "/api/v1/documents",
                headers=headers,
                data={
                    "title": f"Authority mutation {suffix}",
                    "documentType": "work_instruction",
                    "changeReason": "authority mutation receipt test",
                },
                files={"file": (pdf_path.name, file, "application/pdf")},
            )
        assert created_response.status_code == 201, created_response.text
        created = created_response.json()
        document_id = created["document_id"]
        version_id = created["latest_version_id"]

        publish_key = f"pytest:publish:{suffix}"
        publish_payload = {
            "changeReason": "response loss replay publish",
            "baseRevision": 1,
            "expectedPublishedVersionId": None,
            "mutationKey": publish_key,
        }
        publish_responses = [
            client.post(
                f"/api/v1/documents/{document_id}/versions/{version_id}/publish",
                headers=headers,
                json=publish_payload,
            )
            for _ in range(2)
        ]
        assert all(response.status_code == 200 for response in publish_responses)
        assert [response.json()["revision"] for response in publish_responses] == [2, 2]

        status_key = f"pytest:status:{suffix}"
        status_payload = {
            "status": "ARCHIVED",
            "changeReason": "response loss replay status",
            "baseRevision": 2,
            "mutationKey": status_key,
        }
        status_responses = [
            client.patch(
                f"/api/v1/documents/{document_id}/status",
                headers=headers,
                json=status_payload,
            )
            for _ in range(2)
        ]
        assert all(response.status_code == 200 for response in status_responses)
        assert [response.json()["revision"] for response in status_responses] == [3, 3]

        tag_key = f"pytest:tags:{suffix}"
        tag_responses = [
            client.put(
                f"/api/v1/documents/{document_id}/tags",
                headers=headers,
                params={"baseRevision": 3, "mutationKey": tag_key},
                json=["line-a", "press-a"],
            )
            for _ in range(2)
        ]
        assert all(response.status_code == 200 for response in tag_responses)
        assert [response.json()["revision"] for response in tag_responses] == [4, 4]
        assert tag_responses[1].json()["tags"] == ["line-a", "press-a"]

        reused = client.patch(
            f"/api/v1/documents/{document_id}/status",
            headers=headers,
            json={
                **status_payload,
                "status": "IN_REVIEW",
            },
        )
        assert reused.status_code == 409
        assert reused.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REUSED"

        with client.app.state.database.session() as session:
            receipts = session.scalars(
                select(DocumentMutationReceipt).where(
                    DocumentMutationReceipt.document_id == document_id
                )
            ).all()
            document = session.scalar(
                select(Document).where(Document.document_id == document_id)
            )
            history = session.scalars(
                select(ActivityHistory).where(
                    ActivityHistory.target_id.in_([document_id, version_id])
                )
            ).all()
            assert document is not None and document.revision == 4
            assert len(receipts) == 3
            assert len({receipt.mutation_key for receipt in receipts}) == 3
            assert sum(item.event_type == "document.version_published" for item in history) == 1
            assert sum(item.event_type == "document.status_changed" for item in history) == 2
