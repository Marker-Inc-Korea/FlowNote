from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select, text

from app.db.models import (
    AuditEventEnvelope,
    Document,
    NotificationChannel,
    NotificationChannelMember,
    Report,
    ReportMutationReceipt,
    ReportSource,
    SyncMutationReceipt,
)
from app.api.v1.ai_search import _report_source_rows
from test_reports_api import (
    TEST_PASSWORD,
    auth_headers,
    create_document,
    create_field_comment,
    create_role_user,
    create_test_client,
)


def create_approved_report(client, headers: dict[str, str]) -> tuple[dict, dict, dict]:
    document = create_document(client, headers)
    comment = create_field_comment(client, headers, document)
    suffix = uuid4().hex
    response = client.post(
        "/api/v1/reports",
        headers=headers,
        json={
            "reportType": "field_review",
            "title": f"정정 기준 보고서 {suffix[:8]}",
            "summary": "정정 전 확정 내용",
            "analysisContent": "기준 분석",
            "sources": [
                {"sourceType": "FIELD_COMMENT", "sourceId": comment["comment_id"]},
                {"sourceType": "DOCUMENT", "sourceId": document["document_id"]},
            ],
            "saveAsDocument": True,
            "documentTitle": f"정정 기준 생성 문서 {suffix[:8]}",
            "documentStatus": "IN_REVIEW",
            "mutationKey": f"pytest:report-base:{suffix}",
        },
    )
    assert response.status_code == 201, response.text
    return response.json(), document, comment


def correction_create_payload(base: dict, key: str) -> dict:
    return {
        "correctionReason": "확정 뒤 발견한 수치 오류 정정",
        "baseReportRevision": base["report_revision"],
        "sourceSetHashSha256": base["source_set_hash_sha256"],
        "mutationKey": key,
    }


def correction_mutation(
    correction: dict,
    target_status: str,
    key: str,
    *,
    include_content: bool = False,
) -> dict:
    payload = {
        "draftReportId": correction["report_id"],
        "baseReportRevision": correction["report_revision"],
        "mutationKey": key,
        "reportStatus": target_status,
        "reportFamilyId": correction["report_family_id"],
        "replacesReportId": correction["replaces_report_id"],
        "replacesReportRevision": correction["replaces_report_revision"],
        "sourceSetHashSha256": correction["source_set_hash_sha256"],
        "saveAsDocument": target_status == "APPROVED",
        "documentStatus": "IN_REVIEW",
    }
    if include_content:
        payload.update({
            "title": f"{correction['title']} · 정정",
            "summary": "오류를 바로잡은 정정 내용",
            "analysisContent": "원천을 다시 대조한 분석",
        })
    return payload


def create_and_review_correction(client, headers: dict[str, str], base: dict) -> dict:
    created = client.post(
        f"/api/v1/reports/{base['report_id']}/corrections",
        headers=headers,
        json=correction_create_payload(base, f"pytest:correction-create:{uuid4().hex}"),
    )
    assert created.status_code == 201, created.text
    correction = created.json()
    reviewed = client.post(
        "/api/v1/reports",
        headers=headers,
        json=correction_mutation(
            correction,
            "REVIEWED",
            f"pytest:correction-review:{uuid4().hex}",
            include_content=True,
        ),
    )
    assert reviewed.status_code == 201, reviewed.text
    return reviewed.json()


def test_correction_creation_is_idempotent_and_keeps_base_effective() -> None:
    with create_test_client() as client:
        headers = auth_headers(client)
        base, _, _ = create_approved_report(client, headers)
        key = f"pytest:correction-idempotent:{uuid4().hex}"
        payload = correction_create_payload(base, key)

        first = client.post(
            f"/api/v1/reports/{base['report_id']}/corrections",
            headers=headers,
            json=payload,
        )
        second = client.post(
            f"/api/v1/reports/{base['report_id']}/corrections",
            headers=headers,
            json=payload,
        )

        assert first.status_code == second.status_code == 201
        correction = first.json()
        assert second.json()["report_id"] == correction["report_id"]
        changed_intent = dict(payload)
        changed_intent["correctionReason"] = "같은 키로 보낸 다른 정정 사유"
        reused = client.post(
            f"/api/v1/reports/{base['report_id']}/corrections",
            headers=headers,
            json=changed_intent,
        )
        assert reused.status_code == 409
        assert reused.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REUSED"
        assert correction["status"] == "DRAFT"
        assert correction["requires_re_review"] is True
        assert correction["replacement_state"] == "CORRECTION_PENDING"
        assert correction["replaces_report_id"] == base["report_id"]
        assert correction["report_family_id"] == base["report_family_id"]
        assert correction["generated_document_id"] is None

        current_base = client.get(f"/api/v1/reports/{base['report_id']}", headers=headers).json()
        assert current_base["status"] == "APPROVED"
        assert current_base["is_current_effective"] is True
        with client.app.state.database.session() as session:
            children = session.scalars(
                select(Report).where(Report.replaces_report_id == base["report_id"])
            ).all()
            assert len(children) == 1
            assert session.scalar(
                select(ReportMutationReceipt).where(ReportMutationReceipt.mutation_key == key)
            ) is not None
            audit = session.scalar(
                select(AuditEventEnvelope).where(
                    AuditEventEnvelope.event_type == "report.correction_created",
                    AuditEventEnvelope.target_id == correction["report_id"],
                )
            )
            assert audit is not None
            assert audit.related_target_id == base["report_id"]
            assert audit.related_target_revision == base["report_revision"]


def test_correction_can_freeze_an_explicit_current_source_set() -> None:
    with create_test_client() as client:
        headers = auth_headers(client)
        base, _, _ = create_approved_report(client, headers)
        sources = [
            {
                "sourceType": source["source_type"],
                "sourceId": source["source_id"],
                "sourceVersionId": source["source_version_id"],
                "sourceRevision": source["source_revision"],
                "sourceHashSha256": source["source_hash_sha256"],
                "relationType": source["relation_type"],
            }
            for source in base["sources"]
        ]
        payload = correction_create_payload(base, f"pytest:correction-explicit-source:{uuid4().hex}")
        payload.pop("sourceSetHashSha256")
        payload["sources"] = sources

        response = client.post(
            f"/api/v1/reports/{base['report_id']}/corrections",
            headers=headers,
            json=payload,
        )

        assert response.status_code == 201, response.text
        correction = response.json()
        assert correction["source_set_hash_sha256"] == base["source_set_hash_sha256"]
        assert {source["trace_id"] for source in correction["sources"]}.isdisjoint(
            {source["trace_id"] for source in base["sources"]}
        )


def test_correction_approval_atomically_supersedes_base_and_preserves_trace() -> None:
    approved_id: str
    base_id: str
    with create_test_client() as client:
        headers = auth_headers(client)
        base, _, _ = create_approved_report(client, headers)
        reviewed = create_and_review_correction(client, headers, base)
        approval_key = f"pytest:correction-approve:{uuid4().hex}"
        payload = correction_mutation(reviewed, "APPROVED", approval_key)

        first = client.post("/api/v1/reports", headers=headers, json=payload)
        retry = client.post("/api/v1/reports", headers=headers, json=payload)

        assert first.status_code == retry.status_code == 201, first.text
        approved = first.json()
        assert retry.json()["report_id"] == approved["report_id"]
        assert approved["is_current_effective"] is True
        assert approved["replacement_state"] == "REPLACEMENT_COMMITTED"
        assert approved["current_effective_report_id"] == approved["report_id"]
        assert approved["generated_document"]["status"] == "IN_REVIEW"
        assert approved["generated_document"]["published_version_id"] is None

        old = client.get(f"/api/v1/reports/{base['report_id']}", headers=headers).json()
        assert old["status"] == "SUPERSEDED"
        assert old["replacement_state"] == "SUPERSEDED"
        assert old["is_current_effective"] is False
        assert old["superseded_by_report_id"] == approved["report_id"]
        lineage = client.get(
            f"/api/v1/reports/{approved['report_id']}/lineage", headers=headers
        )
        assert lineage.status_code == 200, lineage.text
        assert [row["status"] for row in lineage.json()] == ["SUPERSEDED", "APPROVED"]

        with client.app.state.database.session() as session:
            old_document = session.scalar(
                select(Document).where(Document.document_id == base["generated_document_id"])
            )
            assert old_document is not None and old_document.status == "ARCHIVED"
            report_rows = session.scalars(
                select(Report).where(Report.report_family_id == base["report_family_id"])
            ).all()
            assert len(report_rows) == 2
            source_rows = session.scalars(
                select(ReportSource).where(
                    ReportSource.report_id.in_([base["report_id"], approved["report_id"]])
                )
            ).all()
            assert len(source_rows) == 4
            assert len({row.trace_id for row in source_rows}) == 4
            eligible_report_ids = {row_report.report_id for _, row_report in _report_source_rows(session)}
            assert approved["report_id"] in eligible_report_ids
            assert base["report_id"] not in eligible_report_ids
            receipt = session.scalar(
                select(ReportMutationReceipt).where(ReportMutationReceipt.mutation_key == approval_key)
            )
            common = session.scalar(
                select(SyncMutationReceipt).where(SyncMutationReceipt.operation_key == approval_key)
            )
            assert receipt is not None and common is not None
            audit = session.scalar(
                select(AuditEventEnvelope).where(AuditEventEnvelope.event_id == common.event_id)
            )
            assert audit is not None
            assert audit.related_target_id == base["report_id"]
            assert audit.related_target_revision == base["report_revision"]
        approved_id = approved["report_id"]
        base_id = base["report_id"]

    with create_test_client() as restarted:
        restarted_headers = auth_headers(restarted)
        approved_after_restart = restarted.get(
            f"/api/v1/reports/{approved_id}", headers=restarted_headers
        )
        base_after_restart = restarted.get(
            f"/api/v1/reports/{base_id}", headers=restarted_headers
        )
        assert approved_after_restart.status_code == base_after_restart.status_code == 200
        assert approved_after_restart.json()["is_current_effective"] is True
        assert base_after_restart.json()["status"] == "SUPERSEDED"


def test_correction_requires_re_review_after_reviewed_content_change() -> None:
    with create_test_client() as client:
        headers = auth_headers(client)
        base, _, _ = create_approved_report(client, headers)
        reviewed = create_and_review_correction(client, headers, base)
        changed_approval = correction_mutation(
            reviewed,
            "APPROVED",
            f"pytest:changed-approval:{uuid4().hex}",
        )
        changed_approval["title"] = "재검토 뒤 변경된 제목"

        rejected = client.post("/api/v1/reports", headers=headers, json=changed_approval)
        assert rejected.status_code == 409
        assert rejected.json()["detail"]["code"] == "REPORT_REVIEW_INVALIDATED"

        draft_payload = correction_mutation(
            reviewed,
            "DRAFT",
            f"pytest:correction-redraft:{uuid4().hex}",
            include_content=True,
        )
        draft_payload["title"] = "재검토 뒤 변경된 제목"
        redrafted = client.post("/api/v1/reports", headers=headers, json=draft_payload)
        assert redrafted.status_code == 201, redrafted.text
        assert redrafted.json()["requires_re_review"] is True

        reviewed_again = client.post(
            "/api/v1/reports",
            headers=headers,
            json=correction_mutation(
                redrafted.json(),
                "REVIEWED",
                f"pytest:correction-rereview:{uuid4().hex}",
                include_content=True,
            ),
        )
        assert reviewed_again.status_code == 201, reviewed_again.text


def test_correction_creation_reports_source_change_and_single_open_correction() -> None:
    with create_test_client() as client:
        headers = auth_headers(client)
        base, _, comment = create_approved_report(client, headers)
        with client.app.state.database.engine.begin() as connection:
            connection.execute(
                text("UPDATE field_comments SET raw_content = :content WHERE comment_id = :id"),
                {"content": "정정 생성 직전 변경된 원천", "id": comment["comment_id"]},
            )
        stale = client.post(
            f"/api/v1/reports/{base['report_id']}/corrections",
            headers=headers,
            json=correction_create_payload(base, f"pytest:stale-correction:{uuid4().hex}"),
        )
        assert stale.status_code == 409
        assert stale.json()["detail"]["code"] == "REPORT_CORRECTION_SOURCE_CONFLICT"
        assert stale.json()["detail"]["sourcePreserved"] is True

        with client.app.state.database.engine.begin() as connection:
            connection.execute(
                text("UPDATE field_comments SET raw_content = :content WHERE comment_id = :id"),
                {"content": comment["raw_content"], "id": comment["comment_id"]},
            )
        first = client.post(
            f"/api/v1/reports/{base['report_id']}/corrections",
            headers=headers,
            json=correction_create_payload(base, f"pytest:first-correction:{uuid4().hex}"),
        )
        second = client.post(
            f"/api/v1/reports/{base['report_id']}/corrections",
            headers=headers,
            json=correction_create_payload(base, f"pytest:second-correction:{uuid4().hex}"),
        )
        assert first.status_code == 201, first.text
        assert second.status_code == 409
        assert second.json()["detail"]["code"] == "REPORT_CORRECTION_ALREADY_EXISTS"


def test_correction_creation_reports_channel_membership_loss_without_source_details() -> None:
    with create_test_client() as client:
        admin_headers = auth_headers(client)
        base, _, comment = create_approved_report(client, admin_headers)
        manager = create_role_user(client, "manager")
        manager_headers = auth_headers(client, manager.username, TEST_PASSWORD)
        channel_id = f"channel-{uuid4().hex}"
        with client.app.state.database.session() as session:
            session.add(NotificationChannel(
                channel_id=channel_id,
                name="정정 권한 채널",
                channel_type="LINE",
                source_type="FIELD_COMMENT",
                source_id=comment["comment_id"],
                status="ACTIVE",
                created_by="user-admin",
            ))
            session.add(NotificationChannelMember(
                member_id=f"member-{uuid4().hex}",
                channel_id=channel_id,
                user_id=manager.user_id,
                member_role="MEMBER",
                status="ACTIVE",
                added_by="user-admin",
            ))
            session.commit()
            membership = session.scalar(select(NotificationChannelMember).where(
                NotificationChannelMember.channel_id == channel_id,
                NotificationChannelMember.user_id == manager.user_id,
            ))
            assert membership is not None
            membership.status = "REMOVED"
            session.commit()
        response = client.post(
            f"/api/v1/reports/{base['report_id']}/corrections",
            headers=manager_headers,
            json=correction_create_payload(base, f"pytest:channel-loss:{uuid4().hex}"),
        )
        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["code"] == "REPORT_CORRECTION_SOURCE_CONFLICT"
        assert detail["conflictKind"] == "SOURCE_ACCESS_CHANGED"
        assert comment["comment_id"] not in response.text
