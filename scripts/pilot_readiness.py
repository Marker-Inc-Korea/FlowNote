"""Pilot authorization lifecycle and operator-facing readiness reports."""

from __future__ import annotations

import csv
import hashlib
import html
import json
import re
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


RESPONSIBILITY_LABELS = {
    "server": "서버 운영",
    "certificate": "인증서",
    "windows": "Windows 배포",
    "android": "Android 운영",
    "data_protection": "데이터 보호",
    "field_operations": "현장 운영",
    "support": "지원",
    "ai": "AI 승인",
    "operations": "운영 승인",
    "security": "보안 승인",
}

GATE_RESPONSIBILITIES = {
    "server_clean_install": "server",
    "server_reboot_autostart": "server",
    "wpf_clean_install": "windows",
    "wpf_upgrade": "windows",
    "wpf_remove_reinstall": "windows",
    "package_hash_and_signature": "windows",
    "https_renewal": "certificate",
    "firewall_and_address_change": "server",
    "time_synchronization": "server",
    "android_approved_install": "android",
    "android_secure_storage_and_viewer": "android",
    "android_delivery_and_recovery": "android",
    "android_mdm_kiosk_restart": "android",
    "android_device_replacement": "android",
    "server_restore_separate_pc": "data_protection",
    "wpf_restore_separate_pc": "data_protection",
    "role_workflows": "field_operations",
    "permission_negative_tests": "security",
    "disk_full_stop_and_rollback": "data_protection",
    "long_network_outage_recovery": "support",
    "approved_package_rollback": "data_protection",
    "ai_scope_or_disabled": "ai",
}

PREREQUISITE_LABELS = {
    "authorization_contract": "착수 승인 계약",
    "environment_and_equipment": "시험 환경·승인 장비",
    "execution_gate": "실기 게이트",
    "restore_and_reconciliation": "복구·재결합 선행조건",
    "role_measurement": "역할별 업무 측정",
    "android_operations": "Android 운영 선행조건",
    "ux_evidence": "현장 UX 원시 증거",
    "rollback": "rollback·업무 재개",
    "final_approval": "최종 독립 승인",
    "result_status": "최종 판정 상태",
    "other": "기타 확인 항목",
}

NEXT_ACTIONS = {
    "authorization_contract": "담당자·독립 승인자·승인 시각·근거 참조를 승인 원시표와 pilot-run.json에 함께 기록하세요.",
    "environment_and_equipment": "승인된 고객 유사망과 익명 장비 ID를 확정하고 장비 수와 판정표 수를 일치시키세요.",
    "execution_gate": "선행 승인 해제 후 해당 게이트를 실기하고 같은 run_id의 원시 증거를 연결하세요.",
    "restore_and_reconciliation": "같은 백업 세트와 복구 승인으로 별도 PC 복구·차단·관리자 재결합 증거를 수집하세요.",
    "role_measurement": "승인된 역할·시나리오별 반복 측정을 수행하고 원시 행에서 요약 지표를 다시 계산하세요.",
    "android_operations": "승인 단말·MDM·패키지·보안 조건을 실기하고 Android 원시 표와 증거를 채우세요.",
    "ux_evidence": "현장 관찰과 수정 전후 측정을 원시 행으로 남기고 모든 조치 가능 항목을 개발 항목에 연결하세요.",
    "rollback": "사전 승인한 이전 버전과 rollback 권한으로 복귀·핵심 업무 재개를 확인하세요.",
    "final_approval": "운영·보안·현장 독립 승인자가 원시 증거와 요약을 대조한 뒤 시각·근거를 서명하세요.",
    "result_status": "모든 선행 항목이 충족된 뒤에만 최종 상태를 PASS로 확정하세요.",
    "other": "오류 문구가 가리키는 원시 자료와 요약값을 같은 run_id에서 대조하세요.",
}

EVENTS_PATH = Path("approvals/pilot-authorization-events.jsonl")


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _aware_timestamp(value: Any) -> datetime | None:
    if not _nonempty(value):
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _normalized(value: Any) -> str:
    return str(value or "").strip().casefold()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _evidence_failures(run_root: Path, values: Any, label: str) -> list[str]:
    if not isinstance(values, list) or not values:
        return [f"{label}: 승인 근거 참조가 없습니다."]
    failures: list[str] = []
    root = run_root.resolve()
    for value in values:
        if not _nonempty(value):
            failures.append(f"{label}: 빈 승인 근거 참조가 있습니다.")
            continue
        relative = Path(value)
        candidate = (run_root / relative).resolve()
        if relative.is_absolute() or not candidate.is_relative_to(root):
            failures.append(f"{label}: 승인 근거는 실행 폴더 안의 상대경로여야 합니다.")
        elif not candidate.is_file():
            failures.append(f"{label}: 승인 근거 파일이 없습니다: {value}")
    return failures


def _csv_rows(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    if not path.is_file():
        return [], [f"승인 원시표가 없습니다: {path.name}"]
    try:
        with path.open(newline="", encoding="utf-8-sig") as stream:
            return list(csv.DictReader(stream)), []
    except (OSError, csv.Error) as error:
        return [], [f"승인 원시표를 읽을 수 없습니다: {path.name}: {error}"]


def contract_failures(
    run_root: Path,
    record: dict[str, Any],
    responsibility_areas: tuple[str, ...],
    required_approvals: tuple[str, ...],
) -> list[str]:
    """Validate only the immutable pre-execution contract and its raw references."""

    failures: list[str] = []
    run_id = record.get("run_id")
    if not _nonempty(run_id) or run_root.name != run_id:
        failures.append("승인 계약 run_id가 실행 폴더와 다릅니다.")
    if record.get("profile") != "full_pilot":
        failures.append("단일 파일럿 승인 계약은 full_pilot 프로필이어야 합니다.")

    responsibilities = record.get("responsibilities", {})
    raw_rows, raw_failures = _csv_rows(
        run_root / "approvals" / "responsibility-assignments.csv"
    )
    failures.extend(raw_failures)
    raw_by_area = {
        (row.get("area") or "").strip(): row
        for row in raw_rows
        if (row.get("area") or "").strip()
    }
    repositories: set[str] = set()
    for area in responsibility_areas:
        assignment = responsibilities.get(area, {})
        owner = assignment.get("owner")
        approver = assignment.get("approver")
        if not _nonempty(owner) or not _nonempty(approver):
            failures.append(f"책임 영역 {area}의 담당자와 독립 승인자가 필요합니다.")
        elif _normalized(owner) == _normalized(approver):
            failures.append(f"책임 영역 {area}는 담당자와 독립 승인자가 달라야 합니다.")
        for field, label in (
            ("test_scope", "시험 범위"),
            ("stop_criteria", "중단 기준"),
            ("evidence_repository", "증거 저장소 식별자"),
            ("approved_at", "승인 시각/시간대"),
            ("approval_reference", "승인 근거 참조"),
        ):
            if not _nonempty(assignment.get(field)):
                failures.append(f"책임 영역 {area}의 {label}가 필요합니다.")
        if _nonempty(assignment.get("approved_at")) and _aware_timestamp(
            assignment.get("approved_at")
        ) is None:
            failures.append(f"책임 영역 {area}의 승인 시각에는 시간대가 필요합니다.")
        if _nonempty(assignment.get("evidence_repository")):
            repositories.add(assignment["evidence_repository"].strip())
        failures.extend(
            _evidence_failures(
                run_root,
                assignment.get("approval_evidence"),
                f"책임 영역 {area}",
            )
        )
        raw = raw_by_area.get(area)
        if raw is None:
            failures.append(f"책임 영역 {area}의 승인 원시 행이 없습니다.")
            continue
        for field in (
            "owner",
            "approver",
            "test_scope",
            "stop_criteria",
            "evidence_repository",
            "approved_at",
            "approval_reference",
        ):
            if (raw.get(field) or "").strip() != str(
                assignment.get(field) or ""
            ).strip():
                failures.append(
                    f"책임 영역 {area}의 {field}가 승인 원시표와 판정표에서 다릅니다."
                )
        raw_evidence = (raw.get("approval_evidence") or "").strip()
        if raw_evidence not in (assignment.get("approval_evidence") or []):
            failures.append(
                f"책임 영역 {area}의 승인 원시 근거가 판정표에 연결되지 않았습니다."
            )

    authorization = record.get("authorization", {})
    approved_at = _aware_timestamp(authorization.get("approved_at"))
    if authorization.get("decision") != "PASS" or approved_at is None:
        failures.append("통합 착수 승인의 PASS와 시간대가 있는 승인 시각이 필요합니다.")
    for field, label in (
        ("run_scope", "통합 시험 범위"),
        ("evidence_repository", "통합 증거 저장소 식별자"),
        ("rollback_decision_authority", "rollback 결정권자 역할 ID"),
        ("emergency_contact_flow", "비상 연락 흐름 ID"),
    ):
        if not _nonempty(authorization.get(field)):
            failures.append(f"통합 착수 승인의 {label}가 필요합니다.")
    repository = str(authorization.get("evidence_repository") or "").strip()
    if repository and (len(repositories) != 1 or repository not in repositories):
        failures.append("모든 책임 영역과 통합 승인은 같은 증거 저장소 식별자를 사용해야 합니다.")
    stop_criteria = authorization.get("stop_criteria")
    if (
        not isinstance(stop_criteria, list)
        or len(stop_criteria) < 5
        or not all(_nonempty(item) for item in stop_criteria)
        or len({_normalized(item) for item in stop_criteria}) != len(stop_criteria)
    ):
        failures.append("통합 착수 승인에는 서로 다른 구체적 중단 기준이 5개 이상 필요합니다.")
    try:
        retention = date.fromisoformat(str(authorization.get("retention_until") or ""))
        if approved_at is not None and retention < approved_at.date():
            raise ValueError
    except ValueError:
        failures.append("증거 보존 기한은 승인일 이후의 YYYY-MM-DD 값이어야 합니다.")

    environment = record.get("environment", {})
    equipment = authorization.get("equipment", {})
    if environment.get("customer_like_network") is not True:
        failures.append("승인 계약에 고객 유사망 사용이 확정되지 않았습니다.")
    for count_field, id_field, label in (
        ("clean_server_count", "server_ids", "시험 서버"),
        ("clean_windows_client_count", "windows_client_ids", "시험 Windows 클라이언트"),
        ("approved_android_count", "android_device_ids", "승인 Android 단말"),
    ):
        count = environment.get(count_field)
        identifiers = equipment.get(id_field)
        if not isinstance(identifiers, list) or not identifiers or not all(
            _nonempty(item) for item in identifiers
        ):
            failures.append(f"{label}의 익명 장비 ID가 1개 이상 필요합니다.")
        elif len({_normalized(item) for item in identifiers}) != len(identifiers):
            failures.append(f"{label}의 익명 장비 ID가 중복되었습니다.")
        if not isinstance(count, int) or not isinstance(identifiers, list) or count != len(
            identifiers
        ):
            failures.append(f"{label} 수와 승인 장비 ID 수가 다릅니다.")

    versions = authorization.get("previous_approved_versions", {})
    packages = authorization.get("previous_approved_packages", {})
    for target in ("server", "wpf", "android"):
        version = versions.get(target)
        package = packages.get(target, {})
        if not _nonempty(version):
            failures.append(f"{target} 이전 승인 버전이 필요합니다.")
        if not _nonempty(package.get("version")) or package.get("version") != version:
            failures.append(f"{target} 이전 승인 패키지 버전이 승인 버전과 같아야 합니다.")
        for field in ("sha256", "signer_sha256"):
            if not re.fullmatch(r"[0-9a-fA-F]{64}", str(package.get(field) or "")):
                failures.append(f"{target} 이전 승인 패키지 {field}가 필요합니다.")

    objectives = authorization.get("recovery_objectives", {})
    for target in ("server_restore", "wpf_restore", "rollback"):
        objective = objectives.get(target, {})
        for field in ("rto_seconds", "rpo_seconds"):
            value = objective.get(field)
            if not isinstance(value, (int, float)) or value <= 0:
                failures.append(f"{target} 승인 {field}는 0보다 커야 합니다.")

    approval_rows, approval_row_failures = _csv_rows(
        run_root / "approvals" / "pilot-approval-signatures.csv"
    )
    failures.extend(approval_row_failures)
    approval_by_area = {
        (row.get("area") or "").strip(): row
        for row in approval_rows
        if (row.get("area") or "").strip()
    }
    signers: set[str] = set()
    approvals = authorization.get("approvals", {})
    for area in required_approvals:
        approval = approvals.get(area, {})
        signed_at = _aware_timestamp(approval.get("signed_at"))
        if approval.get("decision") != "PASS":
            failures.append(f"통합 착수 승인 {area}의 PASS가 필요합니다.")
        for field, label in (
            ("signer", "독립 승인자"),
            ("signed_at", "승인 시각/시간대"),
            ("approval_reference", "승인 근거 참조"),
        ):
            if not _nonempty(approval.get(field)):
                failures.append(f"통합 착수 승인 {area}의 {label}가 필요합니다.")
        if signed_at is None or (approved_at is not None and signed_at > approved_at):
            failures.append(f"통합 착수 승인 {area}의 서명 시각이 통합 승인보다 늦거나 시간대가 없습니다.")
        if _nonempty(approval.get("signer")):
            signers.add(_normalized(approval["signer"]))
        failures.extend(
            _evidence_failures(run_root, approval.get("evidence"), f"통합 착수 승인 {area}")
        )
        raw = approval_by_area.get(area)
        if raw is None:
            failures.append(f"통합 착수 승인 {area}의 원시 서명 행이 없습니다.")
            continue
        for field in ("decision", "signer", "signed_at", "approval_reference"):
            if (raw.get(field) or "").strip() != str(approval.get(field) or "").strip():
                failures.append(f"통합 착수 승인 {area}의 {field}가 원시 서명표와 다릅니다.")
        raw_evidence = (raw.get("evidence") or "").strip()
        if raw_evidence not in (approval.get("evidence") or []):
            failures.append(f"통합 착수 승인 {area}의 원시 근거가 판정표에 연결되지 않았습니다.")
    if len(signers) != len(required_approvals):
        failures.append("운영·보안·현장 통합 착수 승인자는 서로 달라야 합니다.")
    failures.extend(_evidence_failures(run_root, authorization.get("evidence"), "통합 착수 승인"))
    return failures


def _contract_payload(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": record.get("run_id"),
        "profile": record.get("profile"),
        "environment": record.get("environment"),
        "responsibilities": record.get("responsibilities"),
        "authorization": record.get("authorization"),
    }


def contract_sha256(record: dict[str, Any]) -> str:
    payload = json.dumps(
        _contract_payload(record), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def read_events(run_root: Path) -> list[dict[str, Any]]:
    path = run_root / EVENTS_PATH
    if not path.is_file():
        return []
    events: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            event = json.loads(line)
            if not isinstance(event, dict):
                raise ValueError(f"승인 이벤트 {line_number}이 JSON 객체가 아닙니다.")
            events.append(event)
    return events


def append_event(run_root: Path, event: dict[str, Any]) -> None:
    path = run_root / EVENTS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def authorization_status(run_root: Path) -> str:
    events = read_events(run_root)
    if not events:
        return "DRAFT"
    return str(events[-1].get("event") or "INVALID")


def authorize(run_root: Path, record: dict[str, Any]) -> dict[str, Any]:
    if read_events(run_root):
        raise ValueError("기존 승인 수명주기를 덮어쓰지 않습니다. 철회된 실행은 새 run_id를 사용하세요.")
    event = {
        "schema_version": 1,
        "sequence": 1,
        "event": "AUTHORIZED",
        "run_id": record["run_id"],
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "contract_sha256": contract_sha256(record),
        "approval_reference": "approvals/pilot-approval-signatures.csv",
    }
    append_event(run_root, event)
    return event


def transition(
    run_root: Path,
    record: dict[str, Any],
    event_name: str,
    actor_role_id: str,
    reason: str,
    *,
    criterion: str = "",
    approval_reference: str = "",
) -> dict[str, Any]:
    events = read_events(run_root)
    status = authorization_status(run_root)
    allowed = {
        "REVOKED": {"AUTHORIZED", "RESUMED"},
        "STOPPED": {"AUTHORIZED", "RESUMED"},
        "RESUMED": {"STOPPED"},
    }
    if status not in allowed[event_name]:
        raise ValueError(f"현재 승인 상태 {status}에서는 {event_name} 전이를 기록할 수 없습니다.")
    if not _nonempty(actor_role_id) or not _nonempty(reason):
        raise ValueError("전이에는 익명 역할 ID와 사유가 필요합니다.")
    if event_name == "STOPPED" and criterion not in record.get("authorization", {}).get(
        "stop_criteria", []
    ):
        raise ValueError("중단 사유는 사전 승인한 중단 기준 중 하나와 정확히 같아야 합니다.")
    if event_name == "RESUMED":
        authority = record.get("authorization", {}).get("rollback_decision_authority")
        if _normalized(actor_role_id) != _normalized(authority):
            raise ValueError("재개는 사전 승인한 rollback 결정권자 역할만 승인할 수 있습니다.")
        if not _nonempty(approval_reference):
            raise ValueError("재개에는 접근 통제 저장소의 승인 근거 참조가 필요합니다.")
    event = {
        "schema_version": 1,
        "sequence": len(events) + 1,
        "event": event_name,
        "run_id": record["run_id"],
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "actor_role_id": actor_role_id,
        "reason": reason,
        "criterion": criterion,
        "approval_reference": approval_reference,
        "contract_sha256": contract_sha256(record),
    }
    append_event(run_root, event)
    return event


def execution_access_failures(run_root: Path, record: dict[str, Any]) -> list[str]:
    events = read_events(run_root)
    if not events:
        return ["파일럿 승인 계약이 확정되지 않아 설치·복구·Android 운영 입력이 잠겨 있습니다."]
    latest = events[-1]
    status = latest.get("event")
    if status not in {"AUTHORIZED", "RESUMED"}:
        return [f"파일럿 승인 상태가 {status}이므로 운영 입력과 완료 판정을 차단합니다."]
    if latest.get("run_id") != record.get("run_id"):
        return ["승인 이벤트 run_id가 판정표와 다릅니다."]
    current_hash = contract_sha256(record)
    authorized_hash = next(
        (
            event.get("contract_sha256")
            for event in reversed(events)
            if event.get("event") == "AUTHORIZED"
        ),
        None,
    )
    if current_hash != authorized_hash:
        return ["착수 승인 뒤 계약 내용이 변경되었습니다. 현재 run을 중단하고 새 run_id로 다시 승인하세요."]
    return []


def _classify_prerequisite(failure: str) -> str:
    if any(
        token in failure
        for token in (
            "승인 계약",
            "사전 승인",
            "착수 승인",
            "책임 영역",
            "증거 보존 기한",
            "이전 승인 버전",
            "이전 승인 패키지",
            "RTO",
            "RPO",
            "rollback 결정권자",
            "비상 연락",
        )
    ):
        return "authorization_contract"
    if any(token in failure for token in ("environment.", "고객 유사망", "시험 서버", "시험 Windows", "시험 Android", "승인 장비")):
        return "environment_and_equipment"
    if "필수 게이트" in failure or failure.startswith("게이트 "):
        return "execution_gate"
    if any(token in failure for token in ("복구", "comparison", "reconciliation", "backup_set")):
        return "restore_and_reconciliation"
    if failure.startswith("역할 ") or "role-metrics" in failure:
        return "role_measurement"
    if "Android" in failure:
        return "android_operations"
    if any(token in failure for token in ("UX ", "현장 관찰", "개발 항목", "BEFORE", "AFTER")):
        return "ux_evidence"
    if "rollback" in failure:
        return "rollback"
    if "최종 승인" in failure:
        return "final_approval"
    if "최종 status" in failure or "최종 상태" in failure:
        return "result_status"
    return "other"


def _classify_gate(failure: str, prerequisite: str) -> str:
    for gate in GATE_RESPONSIBILITIES:
        if gate in failure:
            return gate
    if failure.startswith("0건 필수 지표 "):
        return "zero_tolerance_integrity"
    return {
        "authorization_contract": "pilot_authorization",
        "environment_and_equipment": "pilot_authorization",
        "restore_and_reconciliation": "restore_readiness",
        "role_measurement": "role_workflows",
        "android_operations": "android_operations",
        "ux_evidence": "role_workflows",
        "rollback": "approved_package_rollback",
        "final_approval": "final_approval",
        "result_status": "final_result",
    }.get(prerequisite, "cross_cutting_integrity")


def _classify_role(failure: str, gate: str, prerequisite: str) -> str:
    match = re.search(r"책임 영역 ([a-z_]+)", failure)
    if match:
        return match.group(1)
    match = re.search(r"최종 승인 (operations|security|field_operations)", failure)
    if match:
        return match.group(1)
    if gate in GATE_RESPONSIBILITIES:
        return GATE_RESPONSIBILITIES[gate]
    if "Android" in failure:
        return "android"
    if any(token in failure for token in ("권한", "미승인", "유출", "secret", "plaintext")):
        return "security"
    if prerequisite == "restore_and_reconciliation" or "rollback" in failure:
        return "data_protection"
    if prerequisite in {"role_measurement", "ux_evidence", "environment_and_equipment"}:
        return "field_operations"
    if prerequisite == "authorization_contract":
        return "operations"
    return "support"


def build_readiness(
    run_root: Path, record: dict[str, Any], failures: list[str]
) -> dict[str, Any]:
    responsibilities = record.get("responsibilities", {})
    items = []
    for index, failure in enumerate(failures, start=1):
        prerequisite = _classify_prerequisite(failure)
        gate = _classify_gate(failure, prerequisite)
        role = _classify_role(failure, gate, prerequisite)
        owner = responsibilities.get(role, {}).get("owner")
        owner_display = str(owner).strip() if _nonempty(owner) else f"{RESPONSIBILITY_LABELS.get(role, role)} 담당자(미배정)"
        items.append(
            {
                "number": index,
                "failure": failure,
                "role": role,
                "role_label": RESPONSIBILITY_LABELS.get(role, role),
                "gate": gate,
                "prerequisite": prerequisite,
                "prerequisite_label": PREREQUISITE_LABELS[prerequisite],
                "owner": owner_display,
                "next_action": NEXT_ACTIONS[prerequisite],
            }
        )
    events = read_events(run_root)
    status = authorization_status(run_root)
    role_counts = Counter(item["role"] for item in items)
    gate_counts = Counter(item["gate"] for item in items)
    prerequisite_counts = Counter(item["prerequisite"] for item in items)
    return {
        "schema_version": 1,
        "run_id": record.get("run_id"),
        "profile": record.get("profile"),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "authorization_status": status,
        "execution_inputs_locked": status not in {"AUTHORIZED", "RESUMED"},
        "authorization_event_count": len(events),
        "missing_count": len(items),
        "summary": {
            "by_role": [
                {
                    "role": key,
                    "label": RESPONSIBILITY_LABELS.get(key, key),
                    "count": value,
                }
                for key, value in sorted(role_counts.items(), key=lambda item: (-item[1], item[0]))
            ],
            "by_gate": [
                {"gate": key, "count": value}
                for key, value in sorted(gate_counts.items(), key=lambda item: (-item[1], item[0]))
            ],
            "by_prerequisite": [
                {
                    "prerequisite": key,
                    "label": PREREQUISITE_LABELS[key],
                    "count": value,
                }
                for key, value in sorted(
                    prerequisite_counts.items(), key=lambda item: (-item[1], item[0])
                )
            ],
        },
        "items": items,
    }


def _summary_table(rows: list[dict[str, Any]], key_name: str) -> str:
    return "".join(
        f"<tr><td>{html.escape(str(row.get('label') or row[key_name]))}</td><td>{row['count']}</td></tr>"
        for row in rows
    )


def write_readiness(run_root: Path, report: dict[str, Any]) -> tuple[Path, Path, Path]:
    json_path = run_root / "pilot-readiness.json"
    csv_path = run_root / "pilot-readiness.csv"
    html_path = run_root / "pilot-readiness.html"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with csv_path.open("w", newline="", encoding="utf-8-sig") as stream:
        fieldnames = (
            "number",
            "role_label",
            "gate",
            "prerequisite_label",
            "owner",
            "next_action",
            "failure",
        )
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(report["items"])
    item_rows = "".join(
        "<tr>"
        f"<td>{item['number']}</td>"
        f"<td>{html.escape(item['role_label'])}</td>"
        f"<td><code>{html.escape(item['gate'])}</code></td>"
        f"<td>{html.escape(item['prerequisite_label'])}</td>"
        f"<td>{html.escape(item['owner'])}</td>"
        f"<td>{html.escape(item['next_action'])}</td>"
        f"<td>{html.escape(item['failure'])}</td>"
        "</tr>"
        for item in report["items"]
    )
    locked = "잠김" if report["execution_inputs_locked"] else "입력 가능"
    document = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>FlowNote 파일럿 준비 - {html.escape(str(report['run_id']))}</title>
<style>
body{{font-family:'Malgun Gothic',sans-serif;margin:24px;color:#17202a;background:#f5f7fa}}h1,h2{{margin:.4em 0}}.cards{{display:grid;grid-template-columns:repeat(3,minmax(220px,1fr));gap:12px}}.card,section{{background:white;border:1px solid #d8dee8;border-radius:10px;padding:16px;margin:12px 0}}.locked{{color:#8a1c1c;font-weight:700}}.open{{color:#126b3a;font-weight:700}}table{{width:100%;border-collapse:collapse;background:white}}th,td{{border:1px solid #d8dee8;padding:8px;vertical-align:top;text-align:left}}th{{position:sticky;top:0;background:#eaf0f7}}code{{white-space:nowrap}}.items{{max-height:68vh;overflow:auto}}small{{color:#52606d}}@media(max-width:900px){{.cards{{grid-template-columns:1fr}}}}
</style></head><body>
<h1>파일럿 준비 화면</h1>
<p><code>{html.escape(str(report['run_id']))}</code> · 승인 상태 <strong>{html.escape(report['authorization_status'])}</strong> · 운영 입력 <span class="{'locked' if report['execution_inputs_locked'] else 'open'}">{locked}</span></p>
<p>미충족 <strong>{report['missing_count']}건</strong>. 표에서 브라우저 찾기(Ctrl+F)로 역할, 게이트, 선행조건, 담당자 또는 오류 문구를 찾을 수 있습니다.</p>
<div class="cards"><section><h2>역할별</h2><table><tr><th>역할</th><th>건수</th></tr>{_summary_table(report['summary']['by_role'], 'role')}</table></section>
<section><h2>게이트별</h2><table><tr><th>게이트</th><th>건수</th></tr>{_summary_table(report['summary']['by_gate'], 'gate')}</table></section>
<section><h2>선행조건별</h2><table><tr><th>선행조건</th><th>건수</th></tr>{_summary_table(report['summary']['by_prerequisite'], 'prerequisite')}</table></section></div>
<section><h2>담당자와 다음 행동</h2><small>승인 전에는 설치·복구·Android 운영 템플릿이 생성되지 않습니다. 이미 수집한 원시는 승인 철회나 중단 뒤에도 삭제하지 않습니다.</small>
<div class="items"><table><thead><tr><th>#</th><th>역할</th><th>게이트</th><th>선행조건</th><th>담당자</th><th>다음 행동</th><th>미충족 내용</th></tr></thead><tbody>{item_rows}</tbody></table></div></section>
</body></html>"""
    html_path.write_text(document, encoding="utf-8")
    return json_path, csv_path, html_path
