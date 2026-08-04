from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.api.v1 import document_approvals as approval_api
from app.db.init_db import hash_password
from app.db.models import (
    ActivityHistory,
    AuditEventEnvelope,
    Document,
    DocumentApproval,
    DocumentApprovalEvent,
    DocumentApprovalMutationReceipt,
    DocumentVersion,
    SyncMutationReceipt,
    UserAccount,
)
from test_common_mutation_receipts_api import _create_document
from test_documents_api import auth_headers, create_test_client, prepare_factory_sample_files


def _create_user_and_login(client, *, suffix: str, role: str) -> tuple[str, dict[str, str]]:
    user_id = f"user-approval-{suffix}"
    username = f"approval-{suffix}"
    password = f"Approval-{suffix}-pw"
    with client.app.state.database.session() as session:
        session.add(
            UserAccount(
                user_id=user_id,
                username=username,
                login_id=username,
                display_name=f"승인 담당자 {suffix}",
                role=role,
                password_hash=hash_password(password),
                is_active=True,
                status="ACTIVE",
            )
        )
        session.commit()
    login = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert login.status_code == 200, login.text
    return user_id, {"Authorization": f"Bearer {login.json()['access_token']}"}


def _request_approval(
    client,
    *,
    headers: dict[str, str],
    document: dict,
    reviewer_user_id: str,
    mutation_key: str,
) -> dict:
    latest = document["latest_version"]
    response = client.post(
        "/api/v1/document-approvals",
        headers=headers,
        json={
            "documentId": document["document_id"],
            "versionId": latest["version_id"],
            "baseDocumentRevision": document["revision"],
            "sourceFileHashSha256": latest["file"]["hash_sha256"],
            "reviewerUserId": reviewer_user_id,
            "reason": "현장 공개 전 정확한 버전과 파일 hash 검토",
            "mutationKey": mutation_key,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_approved_exact_version_is_published_with_append_only_trace_and_idempotency() -> None:
    suffix = uuid4().hex[:12]
    with create_test_client(
        document_approval_workflow_enforced=True,
        document_approval_requester_reviewer_separation=True,
        document_approval_requester_publisher_separation=True,
    ) as client:
        requester_headers = auth_headers(client)
        reviewer_id, reviewer_headers = _create_user_and_login(
            client, suffix=suffix, role="document-admin"
        )
        document = _create_document(client, requester_headers, suffix)
        request_key = f"approval-request:{suffix}"
        approval = _request_approval(
            client,
            headers=requester_headers,
            document=document,
            reviewer_user_id=reviewer_id,
            mutation_key=request_key,
        )
        assert approval["status"] == "REQUESTED"
        assert approval["base_document_revision"] == document["revision"] + 1

        decision_key = f"approval-decision:{suffix}"
        decision_payload = {
            "decision": "APPROVE",
            "reason": "현장 공개본으로 사용 가능한 버전과 hash를 확인함",
            "mutationKey": decision_key,
        }
        decided = client.post(
            f"/api/v1/document-approvals/{approval['approval_id']}/decision",
            headers=reviewer_headers,
            json=decision_payload,
        )
        retry = client.post(
            f"/api/v1/document-approvals/{approval['approval_id']}/decision",
            headers=reviewer_headers,
            json=decision_payload,
        )
        assert decided.status_code == retry.status_code == 200
        assert decided.json() == retry.json()
        reused = client.post(
            f"/api/v1/document-approvals/{approval['approval_id']}/decision",
            headers=reviewer_headers,
            json={**decision_payload, "decision": "REJECT"},
        )
        assert reused.status_code == 409
        assert reused.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REUSED"

        publish = client.post(
            f"/api/v1/documents/{document['document_id']}/versions/{document['latest_version_id']}/publish",
            headers=reviewer_headers,
            json={
                "approvalId": approval["approval_id"],
                "baseRevision": approval["base_document_revision"],
                "changeReason": "승인된 현장 공개본 반영",
                "mutationKey": f"approval-publish:{suffix}",
            },
        )
        assert publish.status_code == 200, publish.text
        body = publish.json()
        assert body["publication_approval_id"] == approval["approval_id"]
        assert body["publication_origin"] == "APPROVAL_WORKFLOW"

        with client.app.state.database.session() as session:
            projection = session.scalar(
                select(DocumentApproval).where(
                    DocumentApproval.approval_id == approval["approval_id"]
                )
            )
            events = session.scalars(
                select(DocumentApprovalEvent)
                .where(DocumentApprovalEvent.approval_id == approval["approval_id"])
                .order_by(DocumentApprovalEvent.id)
            ).all()
            assert projection is not None and projection.status == "PUBLISHED"
            assert [event.event_type for event in events] == ["REQUESTED", "APPROVED", "PUBLISHED"]
            assert session.scalar(
                select(func.count()).select_from(DocumentApprovalMutationReceipt).where(
                    DocumentApprovalMutationReceipt.approval_id == approval["approval_id"]
                )
            ) == 2
            assert session.scalar(
                select(func.count()).select_from(SyncMutationReceipt).where(
                    SyncMutationReceipt.operation_key.in_([request_key, decision_key])
                )
            ) == 2
            assert session.scalar(
                select(func.count()).select_from(AuditEventEnvelope).where(
                    AuditEventEnvelope.approval_reference == approval["approval_id"]
                )
            ) >= 2
            assert session.scalar(
                select(func.count()).select_from(ActivityHistory).where(
                    ActivityHistory.target_id == approval["approval_id"]
                )
            ) == 2


def test_unapproved_and_stale_approval_publication_are_blocked_without_losing_sources() -> None:
    suffix = uuid4().hex[:12]
    with create_test_client(
        document_approval_workflow_enforced=True,
        document_approval_requester_reviewer_separation=True,
        document_approval_requester_publisher_separation=True,
    ) as client:
        requester_headers = auth_headers(client)
        reviewer_id, reviewer_headers = _create_user_and_login(
            client, suffix=suffix, role="document-admin"
        )
        document = _create_document(client, requester_headers, suffix)
        without_approval = client.post(
            f"/api/v1/documents/{document['document_id']}/versions/{document['latest_version_id']}/publish",
            headers=reviewer_headers,
            json={"baseRevision": document["revision"], "mutationKey": f"missing:{suffix}"},
        )
        assert without_approval.status_code == 409
        assert without_approval.json()["detail"]["code"] == "APPROVAL_REQUIRED"

        approval = _request_approval(
            client,
            headers=requester_headers,
            document=document,
            reviewer_user_id=reviewer_id,
            mutation_key=f"request-stale:{suffix}",
        )
        approved = client.post(
            f"/api/v1/document-approvals/{approval['approval_id']}/decision",
            headers=reviewer_headers,
            json={
                "decision": "APPROVE",
                "reason": "현재 파일 기준 검토 완료",
                "mutationKey": f"approve-stale:{suffix}",
            },
        )
        assert approved.status_code == 200, approved.text

        _, changed_path, _, _ = prepare_factory_sample_files()
        with changed_path.open("rb") as file:
            changed = client.post(
                f"/api/v1/documents/{document['document_id']}/versions",
                headers=requester_headers,
                data={
                    "changeReason": "승인 뒤 파일 내용 변경",
                    "baseRevision": approval["base_document_revision"],
                    "baseVersionId": document["latest_version_id"],
                },
                files={"file": (changed_path.name, file, "application/pdf")},
            )
        assert changed.status_code == 201, changed.text
        publish = client.post(
            f"/api/v1/documents/{document['document_id']}/versions/{document['latest_version_id']}/publish",
            headers=reviewer_headers,
            json={
                "approvalId": approval["approval_id"],
                "baseRevision": approval["base_document_revision"] + 1,
                "mutationKey": f"publish-stale:{suffix}",
            },
        )
        assert publish.status_code == 409
        assert publish.json()["detail"]["code"] == "APPROVAL_STALE"

        with client.app.state.database.session() as session:
            projection = session.scalar(
                select(DocumentApproval).where(
                    DocumentApproval.approval_id == approval["approval_id"]
                )
            )
            stored_document = session.scalar(
                select(Document).where(Document.document_id == document["document_id"])
            )
            assert projection is not None and projection.status == "STALE"
            assert stored_document is not None
            assert stored_document.published_version_id is None
            assert stored_document.latest_version_id == changed.json()["version_id"]


def test_same_actor_policy_is_explicit_for_review_and_publication() -> None:
    suffix = uuid4().hex[:12]
    with create_test_client(
        document_approval_workflow_enforced=True,
        document_approval_requester_reviewer_separation=False,
        document_approval_requester_publisher_separation=False,
    ) as client:
        headers = auth_headers(client)
        document = _create_document(client, headers, suffix)
        approval = _request_approval(
            client,
            headers=headers,
            document=document,
            reviewer_user_id="user-admin",
            mutation_key=f"same-request:{suffix}",
        )
        decision = client.post(
            f"/api/v1/document-approvals/{approval['approval_id']}/decision",
            headers=headers,
            json={
                "decision": "APPROVE",
                "reason": "현장 설정에서 동일 담당 결정을 허용함",
                "mutationKey": f"same-decision:{suffix}",
            },
        )
        assert decision.status_code == 200, decision.text
        publish = client.post(
            f"/api/v1/documents/{document['document_id']}/versions/{document['latest_version_id']}/publish",
            headers=headers,
            json={
                "approvalId": approval["approval_id"],
                "baseRevision": approval["base_document_revision"],
                "mutationKey": f"same-publish:{suffix}",
            },
        )
        assert publish.status_code == 200, publish.text


def test_publication_cancellation_withdraws_pointer_but_preserves_version_and_events() -> None:
    suffix = uuid4().hex[:12]
    with create_test_client(
        document_approval_workflow_enforced=True,
        document_approval_requester_reviewer_separation=True,
        document_approval_requester_publisher_separation=True,
    ) as client:
        requester_headers = auth_headers(client)
        reviewer_id, reviewer_headers = _create_user_and_login(
            client, suffix=suffix, role="document-admin"
        )
        document = _create_document(client, requester_headers, suffix)
        approval = _request_approval(
            client,
            headers=requester_headers,
            document=document,
            reviewer_user_id=reviewer_id,
            mutation_key=f"cancel-request:{suffix}",
        )
        assert client.post(
            f"/api/v1/document-approvals/{approval['approval_id']}/decision",
            headers=reviewer_headers,
            json={
                "decision": "APPROVE",
                "reason": "공개 전 검토 완료",
                "mutationKey": f"cancel-decision:{suffix}",
            },
        ).status_code == 200
        assert client.post(
            f"/api/v1/documents/{document['document_id']}/versions/{document['latest_version_id']}/publish",
            headers=reviewer_headers,
            json={
                "approvalId": approval["approval_id"],
                "baseRevision": approval["base_document_revision"],
                "mutationKey": f"cancel-publish:{suffix}",
            },
        ).status_code == 200
        cancelled = client.post(
            f"/api/v1/document-approvals/{approval['approval_id']}/cancel",
            headers=reviewer_headers,
            json={
                "reason": "현장 배포 전 공개 승인 철회",
                "mutationKey": f"cancel:{suffix}",
            },
        )
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["status"] == "CANCELLED"

        with client.app.state.database.session() as session:
            stored = session.scalar(
                select(Document).where(Document.document_id == document["document_id"])
            )
            version_count = session.scalar(
                select(func.count()).select_from(DocumentVersion).where(
                    DocumentVersion.document_id == document["document_id"]
                )
            )
            events = session.scalars(
                select(DocumentApprovalEvent)
                .where(DocumentApprovalEvent.approval_id == approval["approval_id"])
                .order_by(DocumentApprovalEvent.id)
            ).all()
            assert stored is not None and stored.status == "WORKING"
            assert stored.published_version_id is None
            assert version_count == 1
            assert [event.event_type for event in events] == [
                "REQUESTED", "APPROVED", "PUBLISHED", "PUBLICATION_WITHDRAWN"
            ]


def test_approval_transaction_rolls_back_projection_event_receipt_audit_and_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suffix = uuid4().hex[:12]
    with create_test_client(
        document_approval_workflow_enforced=True,
        document_approval_requester_reviewer_separation=True,
        document_approval_requester_publisher_separation=True,
    ) as client:
        requester_headers = auth_headers(client)
        reviewer_id, _ = _create_user_and_login(client, suffix=suffix, role="document-admin")
        document = _create_document(client, requester_headers, suffix)

        def fail_common_receipt(*_args, **_kwargs):
            raise RuntimeError("injected common receipt failure")

        monkeypatch.setattr(approval_api, "record_common_mutation_result", fail_common_receipt)
        with pytest.raises(RuntimeError, match="injected common receipt failure"):
            _request_approval(
                client,
                headers=requester_headers,
                document=document,
                reviewer_user_id=reviewer_id,
                mutation_key=f"rollback:{suffix}",
            )

        with client.app.state.database.session() as session:
            stored = session.scalar(
                select(Document).where(Document.document_id == document["document_id"])
            )
            assert stored is not None and stored.revision == document["revision"]
            assert stored.status == "WORKING"
            assert session.scalar(
                select(func.count()).select_from(DocumentApproval).where(
                    DocumentApproval.document_id == document["document_id"]
                )
            ) == 0
            assert session.scalar(
                select(func.count()).select_from(DocumentApprovalEvent).where(
                    DocumentApprovalEvent.document_id == document["document_id"]
                )
            ) == 0
            assert session.scalar(
                select(func.count()).select_from(DocumentApprovalMutationReceipt).where(
                    DocumentApprovalMutationReceipt.document_id == document["document_id"]
                )
            ) == 0


def test_inactive_or_wrong_role_reviewer_is_rejected_and_rejection_cannot_publish() -> None:
    suffix = uuid4().hex[:12]
    with create_test_client(
        document_approval_workflow_enforced=True,
        document_approval_requester_reviewer_separation=True,
        document_approval_requester_publisher_separation=True,
    ) as client:
        requester_headers = auth_headers(client)
        reviewer_id, reviewer_headers = _create_user_and_login(
            client, suffix=suffix, role="document-admin"
        )
        with client.app.state.database.session() as session:
            session.add_all([
                UserAccount(
                    user_id=f"viewer-{suffix}", username=f"viewer-{suffix}",
                    login_id=f"viewer-{suffix}", display_name="권한 없는 검토자",
                    role="viewer", password_hash=hash_password("viewer-test-password"),
                    is_active=True, status="ACTIVE",
                ),
                UserAccount(
                    user_id=f"disabled-{suffix}", username=f"disabled-{suffix}",
                    login_id=f"disabled-{suffix}", display_name="비활성 검토자",
                    role="document-admin", password_hash=hash_password("disabled-test-password"),
                    is_active=False, status="DISABLED",
                ),
            ])
            session.commit()
        document = _create_document(client, requester_headers, suffix)

        for invalid_reviewer in (f"viewer-{suffix}", f"disabled-{suffix}"):
            latest = document["latest_version"]
            invalid = client.post(
                "/api/v1/document-approvals",
                headers=requester_headers,
                json={
                    "documentId": document["document_id"],
                    "versionId": latest["version_id"],
                    "baseDocumentRevision": document["revision"],
                    "sourceFileHashSha256": latest["file"]["hash_sha256"],
                    "reviewerUserId": invalid_reviewer,
                    "reason": "권한과 활성 상태 확인",
                    "mutationKey": f"invalid:{invalid_reviewer}",
                },
            )
            assert invalid.status_code == 422

        approval = _request_approval(
            client,
            headers=requester_headers,
            document=document,
            reviewer_user_id=reviewer_id,
            mutation_key=f"reject-request:{suffix}",
        )
        wrong_reviewer = client.post(
            f"/api/v1/document-approvals/{approval['approval_id']}/decision",
            headers=requester_headers,
            json={
                "decision": "APPROVE",
                "reason": "지정되지 않은 사용자의 결정 시도",
                "mutationKey": f"wrong-reviewer:{suffix}",
            },
        )
        assert wrong_reviewer.status_code == 403
        rejected = client.post(
            f"/api/v1/document-approvals/{approval['approval_id']}/decision",
            headers=reviewer_headers,
            json={
                "decision": "REJECT",
                "reason": "현장 적용 전 수정 항목이 남아 있어 반려",
                "mutationKey": f"reject:{suffix}",
            },
        )
        assert rejected.status_code == 200, rejected.text
        assert rejected.json()["status"] == "REJECTED"
        publish = client.post(
            f"/api/v1/documents/{document['document_id']}/versions/{document['latest_version_id']}/publish",
            headers=reviewer_headers,
            json={
                "approvalId": approval["approval_id"],
                "baseRevision": approval["base_document_revision"] + 1,
                "mutationKey": f"reject-publish:{suffix}",
            },
        )
        assert publish.status_code == 409
        assert publish.json()["detail"]["code"] == "APPROVAL_NOT_APPROVED"
