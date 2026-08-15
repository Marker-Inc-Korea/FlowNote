import json
from uuid import uuid4

from sqlalchemy import func, select

from app.db.models import (
    ActivityHistory,
    AuditEventEnvelope,
    Document,
    DocumentMutationReceipt,
    SyncMutationReceipt,
)
from test_documents_api import (
    auth_headers,
    create_test_client,
    prepare_factory_sample_files,
)


def _create_document(client, headers: dict[str, str], suffix: str) -> dict:
    pdf_path, _, _, _ = prepare_factory_sample_files()
    with pdf_path.open("rb") as file:
        response = client.post(
            "/api/v1/documents",
            headers=headers,
            data={
                "title": f"Common mutation receipt {suffix}",
                "documentType": "work_instruction",
                "changeReason": "common receipt test setup",
            },
            files={"file": (pdf_path.name, file, "application/pdf")},
        )
    assert response.status_code == 201, response.text
    return response.json()


def test_document_status_success_retry_and_key_reuse_share_common_receipt() -> None:
    suffix = uuid4().hex
    with create_test_client() as client:
        headers = {
            **auth_headers(client),
            "X-FlowNote-Run-Id": f"run-{suffix}",
            "X-Correlation-Id": f"correlation-{suffix}",
        }
        created = _create_document(client, headers, suffix)
        document_id = created["document_id"]
        operation_key = f"status-common:{suffix}"
        payload = {
            "status": "IN_REVIEW",
            "changeReason": r"검토 전환 password=not-stored C:\Users\example\secret.txt",
            "baseRevision": 1,
            "mutationKey": operation_key,
        }

        first = client.patch(
            f"/api/v1/documents/{document_id}/status", headers=headers, json=payload
        )
        retry = client.patch(
            f"/api/v1/documents/{document_id}/status", headers=headers, json=payload
        )
        assert first.status_code == retry.status_code == 200
        assert first.json()["revision"] == retry.json()["revision"] == 2

        reused = client.patch(
            f"/api/v1/documents/{document_id}/status",
            headers=headers,
            json={**payload, "status": "ARCHIVED"},
        )
        assert reused.status_code == 409
        assert reused.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REUSED"

        with client.app.state.database.session() as session:
            document = session.scalar(
                select(Document).where(Document.document_id == document_id)
            )
            common = session.scalar(
                select(SyncMutationReceipt).where(
                    SyncMutationReceipt.operation_key == operation_key
                )
            )
            domain = session.scalar(
                select(DocumentMutationReceipt).where(
                    DocumentMutationReceipt.mutation_key == operation_key
                )
            )
            envelopes = session.scalars(
                select(AuditEventEnvelope)
                .where(AuditEventEnvelope.target_id == document_id)
                .order_by(AuditEventEnvelope.id)
            ).all()
            history = session.scalar(
                select(ActivityHistory).where(
                    ActivityHistory.target_id == document_id,
                    ActivityHistory.event_type == "document.status_changed",
                )
            )
            assert document is not None and document.revision == 2
            assert common is not None and domain is not None
            assert common.domain_receipt_type == "document_mutation_receipts"
            assert common.domain_receipt_id == str(domain.id)
            assert common.result == "SUCCESS" and common.http_status == 200
            assert len(envelopes) == 2
            applied, key_reuse = envelopes
            assert applied.event_id == common.event_id
            assert applied.actor_id == "user-admin"
            assert applied.actor_role == "admin"
            assert applied.session_id
            assert applied.run_id == f"run-{suffix}"
            assert applied.correlation_id == f"correlation-{suffix}"
            assert applied.target_revision == 2
            assert applied.before_hash_sha256 and applied.after_hash_sha256
            assert applied.before_hash_sha256 != applied.after_hash_sha256
            assert "not-stored" not in (applied.reason or "")
            assert "C:\\Users" not in (applied.reason or "")
            assert key_reuse.result == "CONFLICT"
            assert key_reuse.result_code == "IDEMPOTENCY_KEY_REUSED"
            assert history is not None
            assert "not-stored" not in (history.change_reason or "")


def test_document_status_conflict_and_rejection_replay_without_duplicate_rows() -> None:
    suffix = uuid4().hex
    with create_test_client() as client:
        headers = auth_headers(client)
        created = _create_document(client, headers, suffix)
        document_id = created["document_id"]
        applied = client.patch(
            f"/api/v1/documents/{document_id}/status",
            headers=headers,
            json={
                "status": "IN_REVIEW",
                "baseRevision": 1,
                "mutationKey": f"prepare:{suffix}",
            },
        )
        assert applied.status_code == 200

        stale_key = f"stale:{suffix}"
        stale_payload = {
            "status": "ARCHIVED",
            "baseRevision": 1,
            "mutationKey": stale_key,
        }
        stale = client.patch(
            f"/api/v1/documents/{document_id}/status", headers=headers, json=stale_payload
        )
        stale_retry = client.patch(
            f"/api/v1/documents/{document_id}/status", headers=headers, json=stale_payload
        )
        assert stale.status_code == stale_retry.status_code == 409
        assert stale.json()["detail"] == stale_retry.json()["detail"]

        rejected_key = f"rejected:{suffix}"
        rejected_payload = {
            "status": "NOT_A_STATUS",
            "baseRevision": 2,
            "mutationKey": rejected_key,
        }
        rejected = client.patch(
            f"/api/v1/documents/{document_id}/status",
            headers=headers,
            json=rejected_payload,
        )
        rejected_retry = client.patch(
            f"/api/v1/documents/{document_id}/status",
            headers=headers,
            json=rejected_payload,
        )
        assert rejected.status_code == rejected_retry.status_code == 422

        with client.app.state.database.session() as session:
            receipts = session.scalars(
                select(SyncMutationReceipt).where(
                    SyncMutationReceipt.operation_key.in_([stale_key, rejected_key])
                )
            ).all()
            by_key = {receipt.operation_key: receipt for receipt in receipts}
            assert by_key[stale_key].result == "CONFLICT"
            assert by_key[stale_key].result_code == "STALE_REVISION"
            assert by_key[rejected_key].result == "REJECTED"
            assert by_key[rejected_key].result_code == "HTTP_422"
            assert session.scalar(
                select(func.count())
                .select_from(SyncMutationReceipt)
                .where(SyncMutationReceipt.operation_key.in_([stale_key, rejected_key]))
            ) == 2
            assert session.scalar(
                select(func.count())
                .select_from(DocumentMutationReceipt)
                .where(DocumentMutationReceipt.mutation_key.in_([stale_key, rejected_key]))
            ) == 0


def test_audit_event_query_marks_legacy_rows_without_inferred_values() -> None:
    suffix = uuid4().hex
    with create_test_client() as client:
        headers = auth_headers(client)
        created = _create_document(client, headers, suffix)
        document_id = created["document_id"]
        changed = client.patch(
            f"/api/v1/documents/{document_id}/status",
            headers=headers,
            json={
                "status": "IN_REVIEW",
                "baseRevision": 1,
                "mutationKey": f"query:{suffix}",
            },
        )
        assert changed.status_code == 200

        response = client.get(
            "/api/v1/audit-events",
            headers=headers,
            params={"targetType": "document", "targetId": document_id},
        )
        assert response.status_code == 200, response.text
        rows = response.json()
        common = next(row for row in rows if row["formatStatus"] == "공통 형식")
        legacy = next(
            row for row in rows if row["formatStatus"] == "이전 형식·일부 필드 없음"
        )
        assert common["schemaVersion"] == 1
        assert common["result"] == "SUCCESS"
        assert legacy["actorRole"] is None
        assert legacy["sessionId"] is None
        assert legacy["targetRevision"] is None
        assert legacy["result"] is None
        assert "actorRole" in legacy["missingFields"]


def test_field_comment_report_and_work_sequence_keep_domain_receipt_links() -> None:
    suffix = uuid4().hex
    with create_test_client() as client:
        headers = auth_headers(client)
        document = _create_document(client, headers, suffix)
        document_id = document["document_id"]
        version_id = document["latest_version_id"]
        published = client.post(
            f"/api/v1/documents/{document_id}/versions/{version_id}/publish",
            headers=headers,
            json={
                "changeReason": "공통 receipt 교차 도메인 검증",
                "baseRevision": 1,
                "mutationKey": f"publish-cross:{suffix}",
            },
        )
        assert published.status_code == 200, published.text

        created_comment = client.post(
            "/api/v1/field-comments",
            headers=headers,
            json={
                "documentId": document_id,
                "documentVersionId": version_id,
                "rawContent": f"공통 receipt 보고서 원천 {suffix}",
            },
        )
        assert created_comment.status_code == 201, created_comment.text
        comment = created_comment.json()
        review_keys: list[str] = []
        for status_value in ("ANALYZED", "REVIEWED", "SELECTED"):
            operation_key = f"field-review:{status_value}:{suffix}"
            review_keys.append(operation_key)
            reviewed = client.patch(
                f"/api/v1/field-comments/{comment['comment_id']}",
                headers=headers,
                json={
                    "status": status_value,
                    "normalizedContent": "공통 receipt 검증용 정리 내용",
                    "analysisContent": "공통 receipt 검증용 관리자 분석",
                    "transitionReason": f"{status_value} 전이 검증",
                    "baseReviewRevision": comment["review_revision"],
                    "mutationKey": operation_key,
                },
            )
            assert reviewed.status_code == 200, reviewed.text
            comment = reviewed.json()

        board_key = f"board-cross:{suffix}"
        board = client.post(
            "/api/v1/work-sequence-boards",
            headers=headers,
            json={"title": f"공통 receipt 보드 {suffix}", "idempotencyKey": board_key},
        )
        assert board.status_code == 201, board.text

        report_key = f"report-cross:{suffix}"
        report = client.post(
            "/api/v1/reports",
            headers=headers,
            json={
                "reportType": "field_review",
                "title": f"공통 receipt 보고서 {suffix}",
                "sources": [
                    {
                        "sourceType": "DOCUMENT",
                        "sourceId": document_id,
                        "sourceVersionId": version_id,
                    },
                    {
                        "sourceType": "FIELD_COMMENT",
                        "sourceId": comment["comment_id"],
                        "sourceRevision": comment["review_revision"],
                        "sourceHashSha256": comment["source_hash_sha256"],
                    },
                ],
                "mutationKey": report_key,
            },
        )
        assert report.status_code == 201, report.text

        with client.app.state.database.session() as session:
            receipts = session.scalars(
                select(SyncMutationReceipt).where(
                    SyncMutationReceipt.operation_key.in_(
                        [review_keys[-1], board_key, report_key]
                    )
                )
            ).all()
            by_key = {receipt.operation_key: receipt for receipt in receipts}
            assert by_key[review_keys[-1]].domain_receipt_type == (
                "field_comment_review_mutation_receipts"
            )
            assert by_key[board_key].domain_receipt_type == (
                "work_sequence_mutation_receipts"
            )
            assert by_key[report_key].domain_receipt_type == "report_mutation_receipts"
            report_event = session.scalar(
                select(AuditEventEnvelope).where(
                    AuditEventEnvelope.event_id == by_key[report_key].event_id
                )
            )
            assert report_event is not None
            assert report_event.approval_status == "APPROVED"
            assert report_event.approved_by == "user-admin"


def test_legacy_domain_receipt_key_cannot_be_reused_by_another_domain() -> None:
    suffix = uuid4().hex
    operation_key = f"legacy-cross-domain:{suffix}"
    with create_test_client() as client:
        headers = auth_headers(client)
        document = _create_document(client, headers, suffix)
        with client.app.state.database.session() as session:
            session.add(
                DocumentMutationReceipt(
                    mutation_key=operation_key,
                    mutation_type="UPDATE_STATUS",
                    intent_hash_sha256="a" * 64,
                    document_id=document["document_id"],
                    applied_revision=document["revision"],
                    response_json=json.dumps(document),
                    created_by="user-admin",
                )
            )
            session.commit()

        reused = client.post(
            "/api/v1/work-sequence-boards",
            headers=headers,
            json={
                "title": f"거부되어야 하는 보드 {suffix}",
                "idempotencyKey": operation_key,
            },
        )
        assert reused.status_code == 409
        assert reused.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REUSED"
