from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from sqlalchemy import delete, func, select

from app.api.v1.document_support import document_tag_intent_hash
from app.db.models import (
    ActivityHistory,
    Document,
    DocumentMutationReceipt,
    DocumentTag,
    TagDefinition,
)
from test_documents_api import auth_headers, create_test_client, prepare_factory_sample_files


def post_document_with_tags(client, headers, file_path, title: str, tags: list[str]) -> dict:
    with file_path.open("rb") as file:
        response = client.post(
            "/api/v1/documents",
            headers=headers,
            data={
                "title": title,
                "documentType": "work_instruction",
                "changeReason": "태그 병합 테스트 등록",
                "tags": tags,
            },
            files={"file": (file_path.name, file, "application/pdf")},
        )
    assert response.status_code == 201, response.text
    return response.json()


def tag_mutation(
    document_id: str,
    base_revision: int,
    added: list[str],
    removed: list[str],
    mutation_key: str,
) -> dict[str, object]:
    return {
        "baseRevision": base_revision,
        "addedTags": added,
        "removedTags": removed,
        "intentHash": document_tag_intent_hash(
            document_id, base_revision, added, removed
        ),
        "mutationKey": mutation_key,
    }


def test_non_overlapping_tag_mutations_merge_once_and_replay_receipt() -> None:
    pdf_path, _, _, _ = prepare_factory_sample_files()
    suffix = uuid4().hex
    with create_test_client() as client:
        headers = auth_headers(client)
        created = post_document_with_tags(
            client, headers, pdf_path, f"Tag merge {suffix}", ["line-a"]
        )
        document_id = created["document_id"]

        first = client.put(
            f"/api/v1/documents/{document_id}/tags",
            headers=headers,
            json=tag_mutation(document_id, 1, ["press-a"], [], f"tags-a:{suffix}"),
        )
        assert first.status_code == 200, first.text
        assert first.json()["revision"] == 2

        second_payload = tag_mutation(
            document_id, 1, ["guard-sensor"], [], f"tags-b:{suffix}"
        )
        second = client.put(
            f"/api/v1/documents/{document_id}/tags",
            headers=headers,
            json=second_payload,
        )
        replay = client.put(
            f"/api/v1/documents/{document_id}/tags",
            headers=headers,
            json=second_payload,
        )

        assert second.status_code == replay.status_code == 200
        assert second.json()["revision"] == replay.json()["revision"] == 3
        assert second.json()["tags"] == ["guard-sensor", "line-a", "press-a"]
        assert second.json()["latest_version"]["file"]["hash_sha256"]

        with client.app.state.database.session() as session:
            document = session.scalar(
                select(Document).where(Document.document_id == document_id)
            )
            receipt_count = session.scalar(
                select(func.count())
                .select_from(DocumentMutationReceipt)
                .where(DocumentMutationReceipt.document_id == document_id)
            )
            audit_count = session.scalar(
                select(func.count())
                .select_from(ActivityHistory)
                .where(
                    ActivityHistory.target_id == document_id,
                    ActivityHistory.event_type == "document.tags_merged",
                )
            )
            assert document is not None and document.revision == 3
            assert receipt_count == 2
            assert audit_count == 2


def test_two_concurrent_non_overlapping_tag_mutations_both_converge() -> None:
    pdf_path, _, _, _ = prepare_factory_sample_files()
    suffix = uuid4().hex
    with create_test_client() as client:
        headers = auth_headers(client)
        created = post_document_with_tags(
            client, headers, pdf_path, f"Concurrent tag merge {suffix}", ["line-a"]
        )
        document_id = created["document_id"]
        payloads = [
            tag_mutation(document_id, 1, ["press-a"], [], f"concurrent-a:{suffix}"),
            tag_mutation(document_id, 1, ["guard-sensor"], [], f"concurrent-b:{suffix}"),
        ]

        def send(payload: dict[str, object]):
            return client.put(
                f"/api/v1/documents/{document_id}/tags",
                headers=headers,
                json=payload,
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(send, payloads))

        assert [response.status_code for response in responses] == [200, 200]
        detail = client.get(
            f"/api/v1/documents/{document_id}", headers=headers
        ).json()
        assert detail["revision"] == 3
        assert detail["tags"] == ["guard-sensor", "line-a", "press-a"]


def test_opposing_and_unavailable_tag_changes_return_structured_conflicts() -> None:
    pdf_path, _, _, _ = prepare_factory_sample_files()
    suffix = uuid4().hex
    with create_test_client() as client:
        headers = auth_headers(client)
        created = post_document_with_tags(
            client,
            headers,
            pdf_path,
            f"Tag conflict {suffix}",
            ["line-a", "inactive-tag"],
        )
        document_id = created["document_id"]

        removed = client.put(
            f"/api/v1/documents/{document_id}/tags",
            headers=headers,
            json=tag_mutation(document_id, 1, [], ["line-a"], f"remove:{suffix}"),
        )
        assert removed.status_code == 200, removed.text

        opposing = client.put(
            f"/api/v1/documents/{document_id}/tags",
            headers=headers,
            json=tag_mutation(document_id, 1, ["line-a"], ["inactive-tag"], f"stale:{suffix}"),
        )
        assert opposing.status_code == 409
        detail = opposing.json()["detail"]
        assert detail["schemaVersion"] == "document-conflict-v1"
        assert detail["code"] == "TAG_MERGE_CONFLICT"
        assert detail["conflictKind"] == "TAG_SET"
        assert detail["allowedActions"] == [
            "KEEP_SERVER",
            "RETRY_WITH_LATEST",
            "REAPPLY_TAG_DELTA",
        ]
        assert detail["autoMergeAllowed"] is False
        assert detail["sourcePreserved"] is True
        assert detail["serverValue"]["revision"] == 2
        assert detail["localRequest"]["addedTags"] == ["line-a"]
        assert detail["autoMerge"]["removedTags"] == ["inactive-tag"]
        assert any(item["reason"] == "OPPOSING_TAG_CHANGE" for item in detail["userChoice"])

        with client.app.state.database.session() as session:
            inactive = session.scalar(
                select(TagDefinition).where(
                    TagDefinition.tag_type == "custom",
                    TagDefinition.code == "inactive-tag",
                )
            )
            assert inactive is not None
            inactive.is_active = False
            session.commit()

        unavailable = client.put(
            f"/api/v1/documents/{document_id}/tags",
            headers=headers,
            json=tag_mutation(
                document_id, 2, [], ["inactive-tag"], f"inactive:{suffix}"
            ),
        )
        assert unavailable.status_code == 409
        unavailable_detail = unavailable.json()["detail"]
        assert unavailable_detail["code"] == "TAG_UNAVAILABLE"
        assert any(item["reason"] == "INACTIVE" for item in unavailable_detail["userChoice"])


def test_tag_delta_does_not_auto_merge_across_non_tag_aggregate_revision() -> None:
    pdf_path, _, _, _ = prepare_factory_sample_files()
    suffix = uuid4().hex
    with create_test_client() as client:
        headers = auth_headers(client)
        created = post_document_with_tags(
            client, headers, pdf_path, f"Aggregate tag conflict {suffix}", ["line-a"]
        )
        document_id = created["document_id"]

        status_response = client.patch(
            f"/api/v1/documents/{document_id}/status",
            headers=headers,
            json={
                "status": "IN_REVIEW",
                "changeReason": "태그 기준 뒤 상태 변경",
                "baseRevision": 1,
                "mutationKey": f"status-before-tag:{suffix}",
            },
        )
        assert status_response.status_code == 200, status_response.text

        stale_tag = client.put(
            f"/api/v1/documents/{document_id}/tags",
            headers=headers,
            json=tag_mutation(
                document_id, 1, ["press-a"], [], f"tag-after-status:{suffix}"
            ),
        )
        assert stale_tag.status_code == 409
        detail = stale_tag.json()["detail"]
        assert detail["code"] == "TAG_AGGREGATE_CHANGED"
        assert detail["autoMergeAllowed"] is False
        assert detail["authoritativeSnapshot"] == {
            "revision": 2,
            "status": "IN_REVIEW",
            "deleted": False,
            "latestVersionId": created["latest_version_id"],
            "latestVersionHashSha256": created["latest_version"]["file"]["hash_sha256"],
            "publishedVersionId": None,
            "publishedVersionHashSha256": None,
            "tags": ["line-a"],
            "allowedActions": [
                "KEEP_SERVER",
                "RETRY_WITH_LATEST",
                "REAPPLY_TAG_DELTA",
            ],
        }
        assert detail["serverValue"]["latestVersionHashSha256"]
        assert detail["serverValue"]["tags"] == ["line-a"]

        read_back = client.get(
            f"/api/v1/documents/{document_id}", headers=headers
        ).json()
        assert read_back["revision"] == 2
        assert read_back["tags"] == ["line-a"]


def test_canonical_tag_intent_hash_deduplicates_normalized_codes() -> None:
    assert document_tag_intent_hash(
        "doc-canonical", 7, [" Line A ", "line   a", "PRESS"], [" Old Tag "]
    ) == document_tag_intent_hash(
        "doc-canonical", 7, ["press", "line-a"], ["old-tag", "OLD TAG"]
    )


def test_deleted_tag_and_document_delete_replay_preserve_authority_once() -> None:
    pdf_path, _, _, _ = prepare_factory_sample_files()
    suffix = uuid4().hex
    with create_test_client() as client:
        headers = auth_headers(client)
        created = post_document_with_tags(
            client, headers, pdf_path, f"Deleted tag {suffix}", ["retired-tag"]
        )
        document_id = created["document_id"]

        with client.app.state.database.session() as session:
            definition = session.scalar(
                select(TagDefinition).where(
                    TagDefinition.tag_type == "custom",
                    TagDefinition.code == "retired-tag",
                )
            )
            assert definition is not None
            session.execute(
                delete(DocumentTag).where(
                    DocumentTag.document_id == document_id,
                    DocumentTag.tag_id == definition.tag_id,
                )
            )
            session.delete(definition)
            session.commit()

        deleted_tag = client.put(
            f"/api/v1/documents/{document_id}/tags",
            headers=headers,
            json=tag_mutation(document_id, 1, [], ["retired-tag"], f"tag-deleted:{suffix}"),
        )
        assert deleted_tag.status_code == 409
        assert deleted_tag.json()["detail"]["code"] == "TAG_UNAVAILABLE"
        assert deleted_tag.json()["detail"]["userChoice"][0]["reason"] == "DELETED"

        delete_payload = {
            "changeReason": "멱등 삭제 검증",
            "baseRevision": 1,
            "mutationKey": f"delete:{suffix}",
        }
        first = client.request(
            "DELETE", f"/api/v1/documents/{document_id}", headers=headers, json=delete_payload
        )
        replay = client.request(
            "DELETE", f"/api/v1/documents/{document_id}", headers=headers, json=delete_payload
        )
        assert first.status_code == replay.status_code == 200
        assert first.json()["revision"] == replay.json()["revision"] == 2

        with client.app.state.database.session() as session:
            delete_audits = session.scalar(
                select(func.count())
                .select_from(ActivityHistory)
                .where(
                    ActivityHistory.target_id == document_id,
                    ActivityHistory.event_type == "document.deleted",
                )
            )
            assert delete_audits == 1
