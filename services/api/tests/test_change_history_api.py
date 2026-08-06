from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import func, select, text

from app.db.models import (
    AuditEventEnvelope,
    AuthSession,
    ChannelMessage,
    Document,
    NotificationChannel,
    NotificationChannelMember,
    ReconciliationItem,
    ReconciliationRun,
    Report,
    TerminalDevice,
    WorkSequenceBoard,
    WorkSequenceNotificationCandidate,
)
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


def test_operational_readiness_uses_current_state_and_stable_snapshot_cursor() -> None:
    suffix = uuid4().hex
    with create_test_client() as client:
        headers = auth_headers(client)
        document = _create_document(client, headers, suffix)
        for index in range(2):
            created = client.post(
                "/api/v1/field-comments",
                headers=headers,
                json={
                    "rawContent": f"운영 준비도 기한 초과 검증 {suffix}-{index}",
                    "documentId": document["document_id"],
                    "documentVersionId": document["latest_version"]["version_id"],
                    "authorId": "user-admin",
                    "signalLevel": "red",
                    "category": "quality",
                },
            )
            assert created.status_code == 201, created.text
            due = client.patch(
                f"/api/v1/field-comments/{created.json()['comment_id']}",
                headers=headers,
                json={
                    "reviewDueAt": (
                        datetime.now(timezone.utc) - timedelta(days=1)
                    ).isoformat()
                },
            )
            assert due.status_code == 200, due.text

        first = client.get(
            "/api/v1/operational-readiness",
            headers=headers,
            params={"blockerCode": "FIELD_COMMENT_REVIEW_OVERDUE", "limit": 1},
        )
        assert first.status_code == 200, first.text
        first_body = first.json()
        assert first_body["sourceAuthority"] == (
            "audit_event_envelopes + current_authority_tables"
        )
        assert first_body["filteredTotalCount"] >= 2
        assert first_body["nextCursor"]
        assert first_body["refreshRequired"] is False
        assert first_body["aiFieldReadiness"]["syntheticIncluded"] is False
        field_area = next(
            area for area in first_body["areas"] if area["areaCode"] == "FIELD_COMMENT"
        )
        assert field_area["blockedCount"] >= 2

        new_event = client.patch(
            f"/api/v1/documents/{document['document_id']}/status",
            headers=headers,
            json={
                "status": "IN_REVIEW",
                "baseRevision": 1,
                "mutationKey": f"readiness-after-snapshot-{suffix}",
            },
        )
        assert new_event.status_code == 200, new_event.text

        second = client.get(
            "/api/v1/operational-readiness",
            headers=headers,
            params={
                "blockerCode": "FIELD_COMMENT_REVIEW_OVERDUE",
                "limit": 1,
                "cursor": first_body["nextCursor"],
            },
        )
        assert second.status_code == 200, second.text
        second_body = second.json()
        assert second_body["snapshotAnchorId"] == first_body["snapshotAnchorId"]
        assert second_body["asOf"] == first_body["asOf"]
        assert second_body["refreshRequired"] is True
        assert second_body["items"][0]["itemId"] != first_body["items"][0]["itemId"]

        changed_filter = client.get(
            "/api/v1/operational-readiness",
            headers=headers,
            params={
                "severity": "BLOCKED",
                "limit": 1,
                "cursor": first_body["nextCursor"],
            },
        )
        assert changed_filter.status_code == 422
        assert changed_filter.json()["detail"]["code"] == (
            "OPERATIONAL_READINESS_CURSOR_INVALID"
        )


def test_operational_readiness_hides_restricted_target_from_counts_and_detail() -> None:
    suffix = uuid4().hex
    with create_test_client() as client:
        admin_headers = auth_headers(client)
        document = _create_document(client, admin_headers, suffix)
        document_id = document["document_id"]
        manager = create_role_user(client, "manager")
        manager_headers = role_auth_headers(client, manager)
        with client.app.state.database.session() as session:
            row = session.scalar(select(Document).where(Document.document_id == document_id))
            assert row is not None
            row.status = "PUBLISHED"
            row.published_version_id = None
            session.add(
                NotificationChannel(
                    channel_id=f"readiness-restricted-{suffix}",
                    name="제한 준비도 문서 채널",
                    channel_type="CUSTOM",
                    source_type="DOCUMENT",
                    source_id=document_id,
                    status="ACTIVE",
                    created_by="user-admin",
                )
            )
            session.commit()

        admin = client.get(
            "/api/v1/operational-readiness",
            headers=admin_headers,
            params={"areaCode": "DOCUMENT_PUBLICATION"},
        )
        assert admin.status_code == 200, admin.text
        admin_item = next(
            item for item in admin.json()["items"] if item["targetId"] == document_id
        )

        hidden = client.get(
            "/api/v1/operational-readiness",
            headers=manager_headers,
            params={"areaCode": "DOCUMENT_PUBLICATION"},
        )
        assert hidden.status_code == 200, hidden.text
        assert all(item["targetId"] != document_id for item in hidden.json()["items"])
        detail = client.get(
            f"/api/v1/operational-readiness/{admin_item['itemId']}",
            headers=manager_headers,
        )
        assert detail.status_code == 404
        assert detail.json()["detail"]["code"] == "RESOURCE_NOT_FOUND"

        viewer = create_role_user(client, "viewer")
        viewer_response = client.get(
            "/api/v1/operational-readiness",
            headers=role_auth_headers(client, viewer),
        )
        assert viewer_response.status_code == 403

        system_admin = create_role_user(client, "system-admin")
        system_admin_response = client.get(
            "/api/v1/operational-readiness",
            headers=role_auth_headers(client, system_admin),
        )
        assert system_admin_response.status_code == 200
        privileged_areas = {
            area["areaCode"]: area for area in system_admin_response.json()["areas"]
        }
        assert privileged_areas["TERMINAL_DEVICE"]["failure"] is None
        assert privileged_areas["SYNC"]["failure"] is None


def test_operational_readiness_keeps_other_areas_when_one_aggregation_fails(
    monkeypatch,
) -> None:
    from app.services import operational_readiness

    def broken_reports(session, *_args, **_kwargs):
        session.execute(text("SELECT * FROM injected_missing_readiness_table"))

    broken_reports.__name__ = "_reports"
    monkeypatch.setattr(
        operational_readiness,
        "AREA_BUILDERS",
        [broken_reports, operational_readiness._field_comments],
    )
    with create_test_client() as client:
        response = client.get(
            "/api/v1/operational-readiness",
            headers=auth_headers(client),
        )
        assert response.status_code == 200, response.text
        areas = {area["areaCode"]: area for area in response.json()["areas"]}
        assert areas["REPORT"]["status"] == "NO_DATA"
        assert areas["REPORT"]["failure"]["code"] == "AREA_AGGREGATION_FAILED"
        assert areas["REPORT"]["failure"]["sourcePreserved"] is True
        assert areas["FIELD_COMMENT"]["status"] in {"NORMAL", "WARNING", "BLOCKED"}


def test_operational_readiness_aggregates_each_authoritative_domain() -> None:
    suffix = uuid4().hex
    with create_test_client() as client:
        headers = auth_headers(client)
        document = _create_document(client, headers, suffix)
        document_id = document["document_id"]
        now = datetime.now(timezone.utc)
        with client.app.state.database.session() as session:
            document_row = session.scalar(
                select(Document).where(Document.document_id == document_id)
            )
            auth_session = session.scalar(
                select(AuthSession).where(
                    AuthSession.user_id == "user-admin",
                    AuthSession.status == "ACTIVE",
                )
            )
            assert document_row is not None and auth_session is not None
            document_row.status = "PUBLISHED"
            document_row.published_version_id = None

            base_report_id = f"report-readiness-base-{suffix}"
            correction_report_id = f"report-readiness-correction-{suffix}"
            session.add(Report(
                report_id=base_report_id,
                report_type="production",
                title=f"준비도 기준 보고서 {suffix}",
                status="APPROVED",
                created_by="user-admin",
                report_revision=1,
            ))
            session.flush()
            session.add(Report(
                report_id=correction_report_id,
                report_type="production",
                title=f"준비도 정정 보고서 {suffix}",
                status="DRAFT",
                created_by="user-admin",
                report_revision=1,
                replaces_report_id=base_report_id,
                replaces_report_revision=1,
                correction_reason="운영 준비도 정정 대기 fixture",
            ))

            board_id = f"board-readiness-{suffix}"
            candidate_id = f"candidate-readiness-{suffix}"
            session.add(WorkSequenceBoard(
                board_id=board_id,
                title=f"준비도 작업판 {suffix}",
                status="ACTIVE",
                board_revision=1,
                created_by="user-admin",
            ))
            session.flush()
            session.add(WorkSequenceNotificationCandidate(
                candidate_id=candidate_id,
                board_id=board_id,
                event_type="work_sequence.changed",
                actor_id="user-admin",
                message="전달되지 않은 작업순서 후보",
                board_revision=1,
                expires_at=now - timedelta(minutes=1),
                status="CANDIDATE",
            ))

            channel_id = f"channel-readiness-{suffix}"
            message_id = f"message-readiness-{suffix}"
            session.add(NotificationChannel(
                channel_id=channel_id,
                name=f"준비도 채널 {suffix}",
                channel_type="CUSTOM",
                status="ACTIVE",
                created_by="user-admin",
            ))
            session.flush()
            session.add(NotificationChannelMember(
                member_id=f"member-readiness-{suffix}",
                channel_id=channel_id,
                user_id="user-admin",
                member_role="OWNER",
                status="ACTIVE",
                added_by="user-admin",
            ))
            session.add(ChannelMessage(
                message_id=message_id,
                channel_id=channel_id,
                message_type="SYSTEM",
                source_type="SYSTEM",
                source_id=f"source-readiness-{suffix}",
                title="확인이 필요한 준비도 메시지",
                created_by="user-admin",
            ))

            device_id = f"device-readiness-{suffix}"
            session.add(TerminalDevice(
                device_id=device_id,
                device_name=f"비활성 준비도 단말 {suffix}",
                device_mode="viewer",
                status="INACTIVE",
                registered_by="user-admin",
                updated_by="user-admin",
            ))
            session.flush()
            session.add(AuthSession(
                session_id=f"session-readiness-{suffix}",
                user_id="user-admin",
                device_id=device_id,
                access_token_id=f"access-readiness-{suffix}",
                refresh_token_hash=f"refresh-readiness-{suffix}",
                status="ACTIVE",
                access_expires_at=now + timedelta(hours=1),
                refresh_expires_at=now + timedelta(days=1),
                last_used_at=now,
            ))

            run_id = f"run-readiness-{suffix}"
            reconciliation_item_id = f"recon-readiness-{suffix}"
            session.add(ReconciliationRun(
                run_id=run_id,
                client_id=f"client-readiness-{suffix}",
                server_instance_id=f"server-readiness-{suffix}",
                server_epoch=1,
                trigger_reason="TEST_FIXTURE",
                status="REVIEW_REQUIRED",
                client_cursor=0,
                server_cursor=0,
                created_by="user-admin",
            ))
            session.flush()
            session.add(ReconciliationItem(
                item_id=reconciliation_item_id,
                run_id=run_id,
                client_item_id=f"client-item-{suffix}",
                entity_type="document",
                local_id=document_id,
                local_version_no=1,
                idempotency_key=f"recon-key-{suffix}",
                verdict="DIVERGED",
                proposed_action="CONFLICT",
                details="서버 revision과 로컬 원천 충돌",
            ))

            session.add(AuditEventEnvelope(
                event_id=f"audit-readiness-{suffix}",
                schema_version=1,
                event_type="document.status_changed",
                actor_id="user-admin",
                actor_role="admin",
                session_id=auth_session.session_id,
                target_type="document",
                target_id=document_id,
                target_revision=None,
                approval_status="NOT_REQUIRED",
                result="SUCCESS",
                result_code="APPLIED",
                http_status=200,
                correlation_id=f"audit-readiness-{suffix}",
                safe_payload_json="{}",
            ))
            session.commit()

        response = client.get(
            "/api/v1/operational-readiness",
            headers=headers,
            params={"targetQuery": suffix, "limit": 200},
        )
        assert response.status_code == 200, response.text
        items = response.json()["items"]
        codes_by_target = {
            item["targetId"]: set(item["blockerCodes"])
            for item in items
        }
        assert document_id in codes_by_target, items
        assert "DOCUMENT_PUBLISHED_VERSION_MISSING" in codes_by_target[document_id]
        assert "REPORT_CORRECTION_PENDING" in codes_by_target[correction_report_id]
        assert "WORK_SEQUENCE_CANDIDATE_EXPIRED" in codes_by_target[candidate_id]
        assert "CHANNEL_MESSAGE_UNREAD" in codes_by_target[f"{channel_id}:user-admin"]
        assert "TERMINAL_INACTIVE_WITH_ACTIVE_SESSION" in codes_by_target[device_id]
        assert "SYNC_CONFLICT_UNRESOLVED" in codes_by_target[reconciliation_item_id]
        audit_item = next(
            item for item in items if item["latestEventId"] == f"audit-readiness-{suffix}"
        )
        assert "AUDIT_MISSING_AUDIT_FIELDS" in audit_item["blockerCodes"]
