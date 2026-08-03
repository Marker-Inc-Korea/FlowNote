from uuid import uuid4

from sqlalchemy import func, select

from app.db.models import AuditEventEnvelope, NotificationChannel
from test_common_mutation_receipts_api import _create_document
from test_documents_api import auth_headers, create_test_client
from test_role_permissions_api import auth_headers as role_auth_headers
from test_role_permissions_api import create_role_user


def test_change_history_traces_action_items_and_has_stable_pagination() -> None:
    suffix = uuid4().hex
    with create_test_client() as client:
        headers = {
            **auth_headers(client),
            "X-FlowNote-Run-Id": f"change-run-{suffix}",
            "X-Correlation-Id": f"change-correlation-{suffix}",
        }
        document = _create_document(client, headers, suffix)
        document_id = document["document_id"]
        success = client.patch(
            f"/api/v1/documents/{document_id}/status",
            headers=headers,
            json={
                "status": "IN_REVIEW",
                "baseRevision": 1,
                "mutationKey": f"change-success-{suffix}",
            },
        )
        assert success.status_code == 200, success.text
        conflict = client.patch(
            f"/api/v1/documents/{document_id}/status",
            headers=headers,
            json={
                "status": "ARCHIVED",
                "baseRevision": 1,
                "mutationKey": f"change-conflict-{suffix}",
            },
        )
        assert conflict.status_code == 409, conflict.text

        with client.app.state.database.session() as session:
            source = session.scalar(
                select(AuditEventEnvelope)
                .where(AuditEventEnvelope.target_id == document_id)
                .order_by(AuditEventEnvelope.id)
            )
            assert source is not None
            session.add(
                AuditEventEnvelope(
                    event_id=f"aevt_unlinked_{suffix}",
                    schema_version=1,
                    event_type="document.status_changed",
                    actor_id=source.actor_id,
                    actor_role=source.actor_role,
                    session_id=source.session_id,
                    device_id=source.device_id,
                    target_type="document",
                    target_id=document_id,
                    target_revision=2,
                    approval_status="NOT_REQUIRED",
                    result="SUCCESS",
                    result_code="APPLIED",
                    http_status=200,
                    run_id=f"change-run-{suffix}",
                    correlation_id=f"unlinked-correlation-{suffix}",
                    safe_payload_json=(
                        '{"operationKey":"unlinked-operation-'
                        f'{suffix}","receiptSchema":"sync-mutation-receipt-v1"}}'
                    ),
                )
            )
            session.commit()
            source_count = session.scalar(
                select(func.count(AuditEventEnvelope.id)).where(
                    AuditEventEnvelope.target_id == document_id
                )
            )

        event_ids: list[str] = []
        cursor = None
        first_page = None
        inserted_after_snapshot = False
        while True:
            params = {"targetId": document_id, "limit": 1}
            if cursor:
                params["cursor"] = cursor
            response = client.get("/api/v1/change-history", headers=headers, params=params)
            assert response.status_code == 200, response.text
            page = response.json()
            first_page = first_page or page
            event_ids.extend(item["eventId"] for item in page["items"])
            cursor = page["nextCursor"]
            if cursor is not None and not inserted_after_snapshot:
                with client.app.state.database.session() as session:
                    source = session.scalar(
                        select(AuditEventEnvelope).where(
                            AuditEventEnvelope.target_id == document_id
                        )
                    )
                    assert source is not None
                    session.add(
                        AuditEventEnvelope(
                            event_id=f"aevt_after_snapshot_{suffix}",
                            schema_version=1,
                            event_type="document.status_changed",
                            actor_id=source.actor_id,
                            actor_role=source.actor_role,
                            session_id=source.session_id,
                            target_type="document",
                            target_id=document_id,
                            target_revision=2,
                            approval_status="NOT_REQUIRED",
                            result="SUCCESS",
                            result_code="APPLIED",
                            http_status=200,
                            correlation_id=f"after-snapshot-{suffix}",
                            safe_payload_json="{}",
                        )
                    )
                    session.commit()
                inserted_after_snapshot = True
            if cursor is None:
                break

        assert first_page is not None
        assert first_page["sourceAuthority"] == "audit_event_envelopes"
        assert first_page["rebuildable"] is True
        assert first_page["totalCount"] == source_count == 3
        assert first_page["actionRequiredCount"] == 2
        assert len(event_ids) == len(set(event_ids)) == 3
        fresh_page = client.get(
            "/api/v1/change-history",
            headers=headers,
            params={"targetId": document_id, "limit": 20},
        )
        assert fresh_page.status_code == 200, fresh_page.text
        assert fresh_page.json()["totalCount"] == 4

        changed_filter_cursor = client.get(
            "/api/v1/change-history",
            headers=headers,
            params={
                "targetId": document_id,
                "riskLevel": "LOW",
                "limit": 1,
                "cursor": first_page["nextCursor"],
            },
        )
        assert changed_filter_cursor.status_code == 422
        assert changed_filter_cursor.json()["detail"]["code"] == (
            "CHANGE_HISTORY_CURSOR_INVALID"
        )

        action_page = client.get(
            "/api/v1/change-history",
            headers=headers,
            params={
                "targetId": document_id,
                "actionRequired": True,
                "runId": f"change-run-{suffix}",
                "limit": 20,
            },
        )
        assert action_page.status_code == 200, action_page.text
        action_body = action_page.json()
        assert action_body["totalCount"] == 2
        assert {item["riskLevel"] for item in action_body["items"]} == {"CRITICAL", "HIGH"}
        unlinked = next(
            item for item in action_body["items"] if "UNLINKED_MUTATION" in item["issueKinds"]
        )
        assert unlinked["currentStatus"] == "IN_REVIEW"
        assert unlinked["assignee"]
        assert unlinked["nextAction"]
        assert unlinked["actionRoute"] == "DOCUMENT_CONFLICT"

        detail = client.get(
            f"/api/v1/change-history/{unlinked['eventId']}", headers=headers
        )
        assert detail.status_code == 200, detail.text
        detail_body = detail.json()
        assert detail_body["item"]["targetId"] == document_id
        assert detail_body["auditEnvelope"]["safePayload"]["operationKey"].startswith(
            "unlinked-operation-"
        )
        assert detail_body["auditEnvelope"]["correlationId"] == (
            f"unlinked-correlation-{suffix}"
        )


def test_change_history_list_and_detail_hide_channel_restricted_target() -> None:
    suffix = uuid4().hex
    with create_test_client() as client:
        admin_headers = auth_headers(client)
        document = _create_document(client, admin_headers, suffix)
        document_id = document["document_id"]
        mutation = client.patch(
            f"/api/v1/documents/{document_id}/status",
            headers=admin_headers,
            json={
                "status": "IN_REVIEW",
                "baseRevision": 1,
                "mutationKey": f"restricted-change-{suffix}",
            },
        )
        assert mutation.status_code == 200, mutation.text
        event_id = client.get(
            "/api/v1/change-history",
            headers=admin_headers,
            params={"targetId": document_id},
        ).json()["items"][0]["eventId"]

        manager = create_role_user(client, "manager")
        manager_headers = role_auth_headers(client, manager)
        with client.app.state.database.session() as session:
            session.add(
                NotificationChannel(
                    channel_id=f"channel-restricted-{suffix}",
                    name="제한 문서 채널",
                    channel_type="CUSTOM",
                    source_type="DOCUMENT",
                    source_id=document_id,
                    status="ACTIVE",
                    created_by="user-admin",
                )
            )
            session.commit()

        hidden_list = client.get(
            "/api/v1/change-history",
            headers=manager_headers,
            params={"targetId": document_id},
        )
        assert hidden_list.status_code == 200, hidden_list.text
        assert hidden_list.json()["totalCount"] == 0
        assert hidden_list.json()["items"] == []

        hidden_detail = client.get(
            f"/api/v1/change-history/{event_id}", headers=manager_headers
        )
        assert hidden_detail.status_code == 404
        assert hidden_detail.json()["detail"]["code"] == "RESOURCE_NOT_FOUND"


def test_permission_denial_followed_by_revision_change_is_critical_action() -> None:
    suffix = uuid4().hex
    with create_test_client() as client:
        headers = auth_headers(client)
        document = _create_document(client, headers, suffix)
        document_id = document["document_id"]
        applied = client.patch(
            f"/api/v1/documents/{document_id}/status",
            headers=headers,
            json={
                "status": "IN_REVIEW",
                "baseRevision": 1,
                "mutationKey": f"permission-follow-up-{suffix}",
            },
        )
        assert applied.status_code == 200, applied.text
        with client.app.state.database.session() as session:
            source = session.scalar(
                select(AuditEventEnvelope).where(
                    AuditEventEnvelope.target_id == document_id
                )
            )
            assert source is not None
            event_id = f"aevt_permission_denied_{suffix}"
            session.add(
                AuditEventEnvelope(
                    event_id=event_id,
                    schema_version=1,
                    event_type="document.status_changed",
                    actor_id=source.actor_id,
                    actor_role=source.actor_role,
                    session_id=source.session_id,
                    target_type="document",
                    target_id=document_id,
                    target_revision=1,
                    approval_status="NOT_REQUIRED",
                    result="REJECTED",
                    result_code="PERMISSION_DENIED",
                    http_status=403,
                    correlation_id=f"permission-correlation-{suffix}",
                    safe_payload_json="{}",
                )
            )
            session.commit()

        response = client.get(
            "/api/v1/change-history",
            headers=headers,
            params={"correlationId": f"permission-correlation-{suffix}"},
        )
        assert response.status_code == 200, response.text
        item = response.json()["items"][0]
        assert item["eventId"] == event_id
        assert item["riskLevel"] == "CRITICAL"
        assert item["permissionDeniedChangeDetected"] is True
        assert "PERMISSION_DENIED_THEN_CHANGED" in item["issueKinds"]
        assert item["currentRevision"] == 2
        assert "권한 거부 뒤" in item["impact"]
