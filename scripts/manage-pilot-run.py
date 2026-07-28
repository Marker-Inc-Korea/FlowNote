#!/usr/bin/env python3
"""Create and strictly validate a FlowNote PILOT evidence run."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import statistics
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts import pilot_restore_gate
    from scripts import pilot_windows_server_evidence as windows_server_evidence
except ModuleNotFoundError:
    import pilot_restore_gate
    import pilot_windows_server_evidence as windows_server_evidence


RUN_ID_PATTERN = re.compile(r"^PILOT-\d{8}-\d{4}-[A-Z0-9_-]+-\d{3}$")
SCHEMA_VERSION = 7
RUN_PROFILES = ("full_pilot", "windows_server_rehearsal")
RESPONSIBILITY_AREAS = (
    "server",
    "certificate",
    "windows",
    "android",
    "data_protection",
    "field_operations",
    "support",
    "ai",
)
REQUIRED_GATES = (
    "server_clean_install",
    "server_reboot_autostart",
    "wpf_clean_install",
    "wpf_upgrade",
    "wpf_remove_reinstall",
    "package_hash_and_signature",
    "https_renewal",
    "firewall_and_address_change",
    "time_synchronization",
    "android_approved_install",
    "android_secure_storage_and_viewer",
    "android_delivery_and_recovery",
    "android_mdm_kiosk_restart",
    "android_device_replacement",
    "server_restore_separate_pc",
    "wpf_restore_separate_pc",
    "role_workflows",
    "permission_negative_tests",
    "disk_full_stop_and_rollback",
    "long_network_outage_recovery",
    "approved_package_rollback",
    "ai_scope_or_disabled",
)
WINDOWS_SERVER_REHEARSAL_GATES = (
    "server_clean_install",
    "server_reboot_autostart",
    "wpf_clean_install",
    "wpf_upgrade",
    "wpf_remove_reinstall",
    "package_hash_and_signature",
    "https_renewal",
    "firewall_and_address_change",
    "time_synchronization",
    "permission_negative_tests",
    "disk_full_stop_and_rollback",
    "long_network_outage_recovery",
    "server_restore_separate_pc",
    "wpf_restore_separate_pc",
    "approved_package_rollback",
)
REQUIRED_ROLES = ("admin", "line_foreman", "team_lead", "team_member")
REQUIRED_APPROVALS = ("operations", "security", "field_operations")
RESTORE_FAULT_CASES = (
    "partial_restore",
    "old_database_new_files",
    "missing_file",
    "wrong_server_epoch",
)
ROLE_SCENARIOS = {
    "admin": (
        "ADMIN-DOCUMENT",
        "ADMIN-FIELD-COMMENT-PHOTO",
        "ADMIN-WORK-SEQUENCE",
        "ADMIN-HANDOVER",
        "ADMIN-REVIEW-REPORT",
    ),
    "line_foreman": (
        "LINE-FOREMAN-DOCUMENT",
        "LINE-FOREMAN-FIELD-COMMENT-PHOTO",
        "LINE-FOREMAN-WORK-SEQUENCE",
        "LINE-FOREMAN-HANDOVER",
    ),
    "team_lead": (
        "TEAM-LEAD-DOCUMENT",
        "TEAM-LEAD-FIELD-COMMENT-PHOTO",
        "TEAM-LEAD-WORK-SEQUENCE",
        "TEAM-LEAD-HANDOVER",
    ),
    "team_member": (
        "TEAM-MEMBER-DOCUMENT",
        "TEAM-MEMBER-FIELD-COMMENT-PHOTO",
        "TEAM-MEMBER-WORK-SEQUENCE",
        "TEAM-MEMBER-HANDOVER",
    ),
}
UX_PRIORITIES = ("P0", "P1", "P2", "P3")
UX_CLASSIFICATIONS = (
    "common_product",
    "device_or_mdm_setting",
    "site_layout_or_training",
)
UX_DECISIONS = ("ACCEPTED", "REJECTED", "REVIEW")
ZERO_TOLERANCE_METRICS = (
    "data_loss",
    "permission_bypass",
    "plaintext_token_or_outbox",
    "external_share_exposure",
    "residual_secure_viewer_cache",
    "unauthorized_file_disclosure",
    "secret_or_personal_data_disclosure",
    "database_integrity_failure",
    "source_count_mismatch",
    "source_hash_mismatch",
)
WINDOWS_SERVER_ZERO_TOLERANCE_METRICS = (
    "data_loss",
    "permission_bypass",
    "unauthorized_file_disclosure",
    "secret_or_personal_data_disclosure",
    "database_integrity_failure",
)
ANDROID_DELIVERY_CASES = (
    ("AND-NOTIFY-NORMAL", "normal"),
    ("AND-NOTIFY-DOZE", "doze"),
    ("AND-NOTIFY-DISCONNECT", "disconnect_5m"),
    ("AND-NOTIFY-BOOT", "reboot"),
    ("AND-NOTIFY-ADDRESS", "address_change"),
    ("AND-NOTIFY-ACCESS-EXPIRY", "access_token_expiry"),
    ("AND-NOTIFY-REFRESH-REJECTED", "refresh_rejected"),
    ("AND-NOTIFY-FORCESTOP", "force_stop_kiosk_restart"),
)
ANDROID_DELIVERY_SCENARIOS = tuple(condition for _, condition in ANDROID_DELIVERY_CASES)
ANDROID_SECURITY_CHECKS = (
    "keystore_token_ciphertext",
    "outbox_ciphertext",
    "encrypted_photo",
    "wrong_key_decryption_failure",
    "secure_cache_cleanup",
    "flag_secure",
    "external_share_absent",
    "backup_disabled",
)
ANDROID_DEVICE_LIFECYCLE_CASES = (
    "device_issue",
    "device_deactivate",
    "device_lost",
    "device_replacement",
)
EVIDENCE_DIRECTORIES = (
    "approvals",
    "packages",
    "install",
    "network-and-certificate",
    "server-logs",
    "windows-logs",
    "android-logs",
    "backup-restore",
    "scenario-results",
    "observations",
    "integrity",
    "incident-and-rollback",
)


def validate_run_id(value: str) -> str:
    if not RUN_ID_PATTERN.fullmatch(value) or "TOOLTEST" in value:
        raise argparse.ArgumentTypeError(
            "run_id는 PILOT-YYYYMMDD-HHMM-현장코드-일련번호 형식이어야 하며 TOOLTEST를 포함할 수 없습니다."
        )
    return value


def empty_record(run_id: str, profile: str) -> dict[str, Any]:
    record = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "profile": profile,
        "status": "PENDING",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "customer_like_network": False,
            "clean_server_count": 0,
            "clean_windows_client_count": 0,
            "approved_android_count": 0,
        },
        "responsibilities": {
            area: {
                "owner": "",
                "approver": "",
                "test_scope": "",
                "stop_criteria": "",
                "evidence_repository": "",
                "approval_evidence": [],
            }
            for area in RESPONSIBILITY_AREAS
        },
        "authorization": {
            "decision": "PENDING",
            "approved_at": "",
            "run_scope": "",
            "stop_criteria": [],
            "evidence_repository": "",
            "retention_until": "",
            "equipment": {
                "server_ids": [],
                "windows_client_ids": [],
                "android_device_ids": [],
            },
            "previous_approved_versions": {
                "server": "",
                "wpf": "",
                "android": "",
            },
            "evidence": [],
        },
        "gates": {
            gate: {"result": "PENDING", "evidence": []} for gate in REQUIRED_GATES
        },
        "zero_tolerance": {metric: None for metric in ZERO_TOLERANCE_METRICS},
        "roles": {
            role: {
                "required_attempts": 0,
                "successful_attempts": 0,
                "success_rate_percent": None,
                "approved_minimum_percent": None,
                "median_seconds": None,
                "approved_max_median_seconds": None,
                "maximum_seconds": None,
                "approved_maximum_seconds": None,
                "retry_count": None,
                "help_request_count": None,
                "screen_transition_count": None,
                "critical_blockers": None,
                "time_limit_approval_id": "",
                "time_limit_approved_at": "",
                "evidence": [],
            }
            for role in REQUIRED_ROLES
        },
        "android_delivery": {
            "scenarios": {
                scenario: {
                    "required_attempts": 0,
                    "successful_attempts": 0,
                    "maximum_seconds": None,
                    "page_seconds": None,
                    "allowed_seconds": None,
                    "evidence": [],
                }
                for scenario in ANDROID_DELIVERY_SCENARIOS
            },
            "lost_messages": None,
            "server_receipt_duplicates": None,
            "crash_boundary_display_duplicates": None,
            "evidence": [],
        },
        "android_security": {
            "keystore_token_ciphertext_verified": None,
            "outbox_ciphertext_verified": None,
            "encrypted_photo_verified": None,
            "wrong_key_decryption_failed": None,
            "secure_cache_cleared_after_exit": None,
            "flag_secure_verified": None,
            "external_share_absent": None,
            "backup_disabled": None,
            "evidence": [],
        },
        "android_device_lifecycle": {
            "lost_or_inactive_device_reconnect_blocked": None,
            "replacement_history_preserved": None,
            "evidence": [],
        },
        "ux_development_items": {
            "actionable_findings": None,
            "converted_items": None,
            "unconverted_actionable_findings": None,
            "priorities": {priority: None for priority in UX_PRIORITIES},
            "classifications": {
                classification: None for classification in UX_CLASSIFICATIONS
            },
            "evidence": [],
        },
        "rollback": {
            target: {
                "result": "PENDING",
                "previous_approved_version": "",
                "normal_work_resumed": False,
                "evidence": [],
            }
            for target in ("server", "wpf", "android")
        },
        "remaining_items": [],
        "final_approvals": {
            area: {"decision": "PENDING", "signer": "", "signed_at": "", "evidence": []}
            for area in REQUIRED_APPROVALS
        },
    }
    record["authorization"].update(windows_server_evidence.authorization_defaults())
    return record


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def prepare(args: argparse.Namespace) -> int:
    run_root = args.evidence_root / args.run_id
    record_path = run_root / "pilot-run.json"
    if record_path.exists() and not args.allow_existing:
        raise ValueError(f"기존 실행을 덮어쓰지 않습니다: {record_path}")
    run_root.mkdir(parents=True, exist_ok=True)
    for directory in EVIDENCE_DIRECTORIES:
        (run_root / directory).mkdir(exist_ok=True)
    if not record_path.exists():
        write_json(record_path, empty_record(args.run_id, args.profile))
    manifest = run_root / "manifest.md"
    if not manifest.exists():
        manifest.write_text(
            f"# {args.run_id}\n\n"
            f"- 프로필: {args.profile}\n"
            "- 상태: 대기\n- 현장/라인 코드:\n- 시작 시각/시간대:\n"
            "- 종료 시각/시간대:\n- 증거 저장소 식별자:\n"
            "- 이전 승인 서버/WPF/Android 버전:\n"
            "- 최종 판정: 대기\n",
            encoding="utf-8",
        )
    android_delivery_rows = "".join(
        ",".join([scenario_id, condition, *("" for _ in range(9)), "NOT_RUN", ""])
        + "\n"
        for scenario_id, condition in ANDROID_DELIVERY_CASES
    )
    templates = {
        run_root / "approvals" / "responsibility-assignments.csv": (
            "area,owner,approver,test_scope,stop_criteria,evidence_repository,"
            "approved_at,approval_evidence\n"
            + "".join(f"{area},,,,,,,\n" for area in RESPONSIBILITY_AREAS)
        ),
        run_root / "approvals" / "rehearsal-authorization.md": (
            f"# {args.run_id} 리허설 사전 승인\n\n"
            f"- 프로필: {args.profile}\n"
            "- 승인 결정: 대기\n- 승인 시각/시간대:\n- 통합 시험 범위:\n"
            "- 중단 기준:\n- 증거 저장소 식별자:\n- 증거 보존 기한:\n"
            "- 익명 서버 ID:\n- 익명 Windows 클라이언트 ID:\n"
            "- 익명 Android 단말 ID:\n- 이전 승인 서버 버전:\n"
            "- 이전 승인 WPF 버전:\n- 이전 승인 Android 버전:\n"
            "- 이전 승인 서버 패키지 SHA-256/signer SHA-256:\n"
            "- 이전 승인 WPF MSI SHA-256/signer SHA-256:\n"
            "- 서버 복구 승인 RTO/RPO(초):\n"
            "- WPF 복구 승인 RTO/RPO(초):\n"
            "- rollback 승인 RTO/RPO(초):\n"
            "- rollback 의사결정권자 역할 ID:\n"
            "- 비상 연락 흐름 ID:\n"
            "- 운영 승인자/서명:\n- 보안 승인자/서명:\n"
            "- 현장 승인자/서명:\n"
        ),
        run_root / "scenario-results" / "android-delivery.csv": (
            "scenario_id,condition,delivery_run_id,message_id,created_at_utc,"
            "recovery_ready_at_utc,displayed_at_utc,receipt_at_utc,page_seconds,"
            "elapsed_seconds,allowed_seconds,result,evidence\n" + android_delivery_rows
        ),
        run_root / "scenario-results" / "android-delivery-integrity.csv": (
            "pilot_run_id,lost_messages,server_receipt_duplicates,"
            "crash_boundary_display_duplicates,result,evidence\n"
            f"{args.run_id},,,,NOT_RUN,\n"
        ),
        run_root / "integrity" / "android-security.csv": (
            "check_id,result,checked_at,device_id,evidence,notes\n"
            + "".join(f"{check},NOT_RUN,,,,\n" for check in ANDROID_SECURITY_CHECKS)
        ),
        run_root / "scenario-results" / "android-device-lifecycle.csv": (
            "scenario_id,result,checked_at,old_device_id,new_device_id,"
            "old_access_result,old_refresh_result,old_login_result,"
            "server_status,history_event_ids,mdm_event_id,evidence,notes\n"
            + "".join(
                f"{case},NOT_RUN,,,,,,,,,,,\n"
                for case in ANDROID_DEVICE_LIFECYCLE_CASES
            )
        ),
        run_root / "packages" / "android-release-approval.csv": (
            "artifact_role,artifact_type,version_name,version_code,sha256,"
            "signer_sha256,mdm_package_id,rollout_ring,approval_id,result,evidence\n"
            "release_candidate,,,,,,,,,NOT_RUN,\n"
            "previous_approved_rollback,,,,,,,,,NOT_RUN,\n"
        ),
        run_root / "scenario-results" / "role-metrics.csv": (
            "role,participant_id,scenario_id,required,success,elapsed_seconds,"
            "retry_count,help_request_count,screen_transitions,critical_blocker,evidence\n"
        ),
        run_root / "scenario-results" / "role-ux-comparison.csv": (
            "comparison_id,development_cycle_id,attempt_no,role,participant_id,"
            "scenario_id,ui_phase,ui_build,"
            "success,elapsed_seconds,click_count,screen_transitions,"
            "help_request_count,screen_capture_evidence,notes\n"
        ),
        run_root / "scenario-results" / "restore-fault-injections.csv": (
            "injection_id,target,automatic_send_blocked,polling_blocked,"
            "reconciliation_required,admin_approved_rebind,normal_operation_resumed,"
            "result,screen_evidence,wpf_log_evidence,server_audit_evidence\n"
            + "".join(f"{case},,,,,,,NOT_RUN,,,\n" for case in RESTORE_FAULT_CASES)
        ),
        run_root / "observations" / "role-observations.csv": (
            "observation_id,role,scenario_id,device_id,location,network,gloves,"
            "one_hand,lighting,terminal_position,input_moment,terminology_confusion,"
            "button_confusion,photo_capture,short_memo,signal_input,actionable,success,"
            "elapsed_seconds,retry_count,help_request_count,screen_transitions,notes,evidence\n"
        ),
        run_root / "observations" / "development-items.csv": (
            "item_id,observation_id,decision,decision_basis,priority,classification,title,"
            "acceptance_criteria,owner,due_date,status,development_cycle_id,"
            "comparison_id,evidence\n"
        ),
    }
    for path, header in templates.items():
        if not path.exists():
            path.write_text(header, encoding="utf-8")
    if args.profile == "windows_server_rehearsal":
        windows_server_evidence.write_templates(run_root, args.run_id)
    print(f"파일럿 실행 폴더 준비: {run_root}")
    print(f"기계 판정표: {record_path}")
    print("초기 판정: PENDING")
    return 0


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def required_android_csv_failures(
    run_root: Path,
    relative_path: str,
    id_column: str,
    required_ids: tuple[str, ...],
    label: str,
    required_fields: tuple[str, ...] = (),
    exactly_one: bool = True,
) -> list[str]:
    path = run_root / relative_path
    if not path.is_file():
        return [f"{label}: 원시 결과 파일이 없습니다: {relative_path}"]
    try:
        with path.open(newline="", encoding="utf-8-sig") as stream:
            rows = list(csv.DictReader(stream))
    except (OSError, csv.Error) as exc:
        return [f"{label}: CSV를 읽을 수 없습니다: {exc}"]

    failures: list[str] = []
    grouped = {required_id: [] for required_id in required_ids}
    for row in rows:
        row_id = (row.get(id_column) or "").strip()
        if row_id in grouped:
            grouped[row_id].append(row)
    for required_id, matching in grouped.items():
        if not matching:
            failures.append(f"{label} {required_id} 행이 없습니다.")
            continue
        if exactly_one and len(matching) != 1:
            failures.append(f"{label} {required_id} 행은 정확히 1개여야 합니다.")
        for row in matching:
            if (row.get("result") or "").strip() != "PASS":
                failures.append(f"{label} {required_id}의 원시 판정이 PASS가 아닙니다.")
            for field in required_fields:
                if not (row.get(field) or "").strip():
                    failures.append(f"{label} {required_id}의 {field} 값이 없습니다.")
            evidence = (row.get("evidence") or "").strip()
            failures.extend(
                evidence_failures(run_root, [evidence], f"{label} {required_id}")
            )
    return failures


def android_delivery_csv_failures(
    run_root: Path, expected: dict[str, Any] | None = None
) -> list[str]:
    relative_path = "scenario-results/android-delivery.csv"
    path = run_root / relative_path
    failures = required_android_csv_failures(
        run_root,
        relative_path,
        "condition",
        ANDROID_DELIVERY_SCENARIOS,
        "Android 전달 원시 결과",
        exactly_one=False,
    )
    if not path.is_file():
        return failures
    try:
        with path.open(newline="", encoding="utf-8-sig") as stream:
            rows = list(csv.DictReader(stream))
    except (OSError, csv.Error):
        return failures
    rows_by_condition = {
        condition: [
            row for row in rows if (row.get("condition") or "").strip() == condition
        ]
        for condition in ANDROID_DELIVERY_SCENARIOS
    }
    if expected is not None:
        for condition, matching in rows_by_condition.items():
            metric = expected.get(condition, {})
            if len(matching) != metric.get("required_attempts"):
                failures.append(
                    f"Android 전달 {condition}의 원시 시도 수와 요약 분모가 다릅니다."
                )
            passed = sum(
                1 for row in matching if (row.get("result") or "").strip() == "PASS"
            )
            if passed != metric.get("successful_attempts"):
                failures.append(
                    f"Android 전달 {condition}의 원시 성공 수와 요약 성공 수가 다릅니다."
                )
            try:
                raw_maximum = max(
                    float((row.get("elapsed_seconds") or "").strip())
                    for row in matching
                )
            except (ValueError, TypeError):
                pass
            else:
                summary_maximum = metric.get("maximum_seconds")
                if (
                    not isinstance(summary_maximum, (int, float))
                    or abs(raw_maximum - summary_maximum) > 0.001
                ):
                    failures.append(
                        f"Android 전달 {condition}의 원시 최대 시간과 요약 최대 시간이 다릅니다."
                    )
    for row in rows:
        condition = (row.get("condition") or "").strip()
        if condition not in ANDROID_DELIVERY_SCENARIOS:
            continue
        delivery_run_id = (row.get("delivery_run_id") or "").strip()
        if not delivery_run_id.startswith("ANDROID-DELIVERY-"):
            failures.append(
                f"Android 전달 {condition}의 delivery_run_id가 올바르지 않습니다."
            )
        try:
            elapsed = float((row.get("elapsed_seconds") or "").strip())
            allowed = float((row.get("allowed_seconds") or "").strip())
        except ValueError:
            failures.append(
                f"Android 전달 {condition}의 측정/허용 시간이 숫자가 아닙니다."
            )
            continue
        if elapsed < 0 or allowed <= 0 or elapsed > allowed:
            failures.append(
                f"Android 전달 {condition}의 원시 측정값이 허용 시간을 초과합니다."
            )
        if condition in ("normal", "doze") and allowed != 30:
            failures.append(
                f"Android 전달 {condition}의 원시 허용 시간은 30초여야 합니다."
            )
        if condition == "disconnect_5m":
            try:
                page_seconds = float((row.get("page_seconds") or "").strip())
            except ValueError:
                failures.append("Android 5분 단절 원시 page 시간이 숫자가 아닙니다.")
            else:
                if page_seconds < 0 or allowed != 30 + page_seconds:
                    failures.append(
                        "Android 5분 단절 원시 허용 시간은 30초+page 시간이어야 합니다."
                    )
    return failures


def android_delivery_integrity_csv_failures(
    run_root: Path, run_id: str, expected: dict[str, Any]
) -> list[str]:
    relative_path = "scenario-results/android-delivery-integrity.csv"
    path = run_root / relative_path
    if not path.is_file():
        return [f"Android 전달 무결성: 원시 결과 파일이 없습니다: {relative_path}"]
    try:
        with path.open(newline="", encoding="utf-8-sig") as stream:
            rows = list(csv.DictReader(stream))
    except (OSError, csv.Error) as exc:
        return [f"Android 전달 무결성 CSV를 읽을 수 없습니다: {exc}"]
    if len(rows) != 1:
        return ["Android 전달 무결성 원시 결과 행은 정확히 1개여야 합니다."]
    row = rows[0]
    failures: list[str] = []
    if (row.get("pilot_run_id") or "").strip() != run_id:
        failures.append("Android 전달 무결성의 PILOT run_id가 현재 실행과 다릅니다.")
    if (row.get("result") or "").strip() != "PASS":
        failures.append("Android 전달 무결성 원시 판정이 PASS가 아닙니다.")
    for field in (
        "lost_messages",
        "server_receipt_duplicates",
        "crash_boundary_display_duplicates",
    ):
        try:
            value = int((row.get(field) or "").strip())
        except ValueError:
            failures.append(f"Android 전달 무결성의 {field} 값이 정수가 아닙니다.")
            continue
        if value != expected.get(field):
            failures.append(
                f"Android 전달 무결성의 {field} 원시값과 요약값이 다릅니다."
            )
    evidence = (row.get("evidence") or "").strip()
    failures.extend(evidence_failures(run_root, [evidence], "Android 전달 무결성"))
    return failures


def normalized_identity(value: Any) -> str:
    return value.strip().casefold() if isinstance(value, str) else ""


def identifier_list_failures(values: Any, minimum: int, label: str) -> list[str]:
    if not isinstance(values, list):
        return [f"{label} 목록이 없습니다."]
    identifiers = [value.strip() for value in values if nonempty(value)]
    if len(identifiers) < minimum:
        return [f"{label}는 {minimum}개 이상이어야 합니다."]
    if len(set(value.casefold() for value in identifiers)) != len(identifiers):
        return [f"{label}에 중복 식별자가 있습니다."]
    return []


def evidence_failures(run_root: Path, values: Any, label: str) -> list[str]:
    failures: list[str] = []
    if not isinstance(values, list) or not values:
        return [f"{label}: 증거 목록이 비어 있습니다."]
    for raw in values:
        if not nonempty(raw):
            failures.append(f"{label}: 빈 증거 경로가 있습니다.")
            continue
        evidence = Path(raw)
        if evidence.is_absolute() or ".." in evidence.parts:
            failures.append(
                f"{label}: 증거 경로는 실행 폴더 안의 상대경로여야 합니다: {raw}"
            )
        elif not (run_root / evidence).is_file():
            failures.append(f"{label}: 증거 파일이 없습니다: {raw}")
    return failures


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv_rows(
    run_root: Path, relative_path: str, label: str
) -> tuple[list[dict[str, str]], list[str]]:
    path = run_root / relative_path
    if not path.is_file():
        return [], [f"{label}: 원시 결과 파일이 없습니다: {relative_path}"]
    try:
        with path.open(newline="", encoding="utf-8-sig") as stream:
            return list(csv.DictReader(stream)), []
    except (OSError, csv.Error) as exc:
        return [], [f"{label}: CSV를 읽을 수 없습니다: {exc}"]


def csv_bool(value: Any) -> bool | None:
    normalized = str(value or "").strip().casefold()
    if normalized in ("true", "1", "yes", "y"):
        return True
    if normalized in ("false", "0", "no", "n"):
        return False
    return None


def restore_fault_injection_failures(run_root: Path) -> list[str]:
    return pilot_restore_gate.fault_injection_failures(
        run_root,
        RESTORE_FAULT_CASES,
        read_csv_rows,
        csv_bool,
        evidence_failures,
    )


def role_metrics_csv_failures(
    run_root: Path, expected_roles: dict[str, Any]
) -> list[str]:
    rows, failures = read_csv_rows(
        run_root, "scenario-results/role-metrics.csv", "역할별 원시 지표"
    )
    for role, required_scenarios in ROLE_SCENARIOS.items():
        role_rows = [row for row in rows if (row.get("role") or "").strip() == role]
        required_rows = [
            row for row in role_rows if csv_bool(row.get("required")) is True
        ]
        for scenario_id in required_scenarios:
            scenario_attempts = sum(
                (row.get("scenario_id") or "").strip() == scenario_id
                for row in required_rows
            )
            if scenario_attempts < 2:
                failures.append(
                    f"역할 {role}의 필수 시나리오 {scenario_id}는 동일 조건으로 2회 이상 반복해야 합니다."
                )
        if any(csv_bool(row.get("required")) is None for row in role_rows):
            failures.append(f"역할 {role}의 required 값은 TRUE/FALSE여야 합니다.")

        elapsed_values: list[float] = []
        retries = 0
        help_requests = 0
        screen_transitions = 0
        blockers = 0
        successful = 0
        for index, row in enumerate(required_rows, start=1):
            label = f"역할 {role} 원시 시도 {index}"
            if not nonempty(row.get("participant_id")):
                failures.append(f"{label}의 익명 participant_id가 없습니다.")
            success = csv_bool(row.get("success"))
            blocker = csv_bool(row.get("critical_blocker"))
            if success is None or blocker is None:
                failures.append(
                    f"{label}의 success/critical_blocker 값이 올바르지 않습니다."
                )
            successful += int(success is True)
            blockers += int(blocker is True)
            try:
                elapsed = float((row.get("elapsed_seconds") or "").strip())
                retry = int((row.get("retry_count") or "").strip())
                help_count = int((row.get("help_request_count") or "").strip())
                screen_count = int((row.get("screen_transitions") or "").strip())
                if elapsed < 0 or retry < 0 or help_count < 0 or screen_count < 0:
                    raise ValueError
            except ValueError:
                failures.append(
                    f"{label}의 시간·재시도·도움 요청 값이 올바르지 않습니다."
                )
            else:
                elapsed_values.append(elapsed)
                retries += retry
                help_requests += help_count
                screen_transitions += screen_count
            failures.extend(
                evidence_failures(
                    run_root, [(row.get("evidence") or "").strip()], label
                )
            )

        summary = expected_roles.get(role, {})
        raw_required = len(required_rows)
        raw_rate = successful / raw_required * 100 if raw_required else None
        comparisons = (
            ("required_attempts", raw_required, "분모"),
            ("successful_attempts", successful, "성공 건수"),
            ("retry_count", retries, "재시도 합계"),
            ("help_request_count", help_requests, "도움 요청 합계"),
            ("screen_transition_count", screen_transitions, "화면 이동 합계"),
            ("critical_blockers", blockers, "치명적 blocker 합계"),
        )
        for field, raw_value, label in comparisons:
            if summary.get(field) != raw_value:
                failures.append(f"역할 {role}의 원시 {label}와 요약값이 다릅니다.")
        numeric_comparisons = (
            ("success_rate_percent", raw_rate, "성공률"),
            (
                "median_seconds",
                statistics.median(elapsed_values) if elapsed_values else None,
                "중앙 시간",
            ),
            (
                "maximum_seconds",
                max(elapsed_values) if elapsed_values else None,
                "최대 시간",
            ),
        )
        for field, raw_value, label in numeric_comparisons:
            summary_value = summary.get(field)
            if (
                raw_value is None
                or not isinstance(summary_value, (int, float))
                or abs(summary_value - raw_value) > 0.01
            ):
                failures.append(f"역할 {role}의 원시 {label}과 요약값이 다릅니다.")
    return failures


def ux_csv_failures(run_root: Path, expected: dict[str, Any]) -> list[str]:
    observations, failures = read_csv_rows(
        run_root, "observations/role-observations.csv", "역할별 현장 관찰"
    )
    items, item_failures = read_csv_rows(
        run_root, "observations/development-items.csv", "UX 개발 항목"
    )
    failures.extend(item_failures)
    observation_ids: set[str] = set()
    actionable_ids: set[str] = set()
    observed_roles: set[str] = set()
    observed_gloves_on = False
    observed_disconnected = False
    for index, row in enumerate(observations, start=1):
        observation_id = (row.get("observation_id") or "").strip()
        if not observation_id or observation_id in observation_ids:
            failures.append(f"현장 관찰 {index}의 observation_id가 없거나 중복입니다.")
        observation_ids.add(observation_id)
        role = (row.get("role") or "").strip()
        if role not in REQUIRED_ROLES:
            failures.append(
                f"현장 관찰 {observation_id or index}의 역할이 올바르지 않습니다."
            )
        else:
            observed_roles.add(role)
        for field in (
            "scenario_id",
            "device_id",
            "location",
            "network",
            "gloves",
            "one_hand",
            "lighting",
            "terminal_position",
            "input_moment",
            "terminology_confusion",
            "button_confusion",
            "photo_capture",
            "short_memo",
            "signal_input",
        ):
            if not nonempty(row.get(field)):
                failures.append(
                    f"현장 관찰 {observation_id or index}의 {field} 값이 없습니다."
                )
        network = (row.get("network") or "").strip().upper()
        gloves = (row.get("gloves") or "").strip().upper()
        if network not in ("CONNECTED", "DISCONNECTED"):
            failures.append(
                f"현장 관찰 {observation_id or index}의 network는 CONNECTED/DISCONNECTED여야 합니다."
            )
        if gloves not in ("ON", "OFF"):
            failures.append(
                f"현장 관찰 {observation_id or index}의 gloves는 ON/OFF여야 합니다."
            )
        observed_gloves_on = observed_gloves_on or gloves == "ON"
        observed_disconnected = observed_disconnected or network == "DISCONNECTED"
        for field in (
            "one_hand",
            "terminology_confusion",
            "button_confusion",
            "photo_capture",
            "short_memo",
            "signal_input",
            "success",
        ):
            if csv_bool(row.get(field)) is None:
                failures.append(
                    f"현장 관찰 {observation_id or index}의 {field} 값이 올바르지 않습니다."
                )
        try:
            elapsed = float((row.get("elapsed_seconds") or "").strip())
            retry = int((row.get("retry_count") or "").strip())
            help_count = int((row.get("help_request_count") or "").strip())
            screen_count = int((row.get("screen_transitions") or "").strip())
            if elapsed < 0 or retry < 0 or help_count < 0 or screen_count < 0:
                raise ValueError
        except ValueError:
            failures.append(
                f"현장 관찰 {observation_id or index}의 시간·재시도·도움 요청 값이 올바르지 않습니다."
            )
        actionable = csv_bool(row.get("actionable"))
        if actionable is None:
            failures.append(
                f"현장 관찰 {observation_id or index}의 actionable 값이 올바르지 않습니다."
            )
        elif actionable:
            actionable_ids.add(observation_id)
        failures.extend(
            evidence_failures(
                run_root,
                [(row.get("evidence") or "").strip()],
                f"현장 관찰 {observation_id or index}",
            )
        )

    for role in REQUIRED_ROLES:
        if role not in observed_roles:
            failures.append(f"역할 {role}의 현장 관찰이 없습니다.")
    if not observed_gloves_on:
        failures.append("장갑 착용 상태의 현장 관찰이 없습니다.")
    if not observed_disconnected:
        failures.append("네트워크 단절 상태의 현장 관찰이 없습니다.")

    item_ids: set[str] = set()
    linked_observations: list[str] = []
    priority_counts = {value: 0 for value in UX_PRIORITIES}
    classification_counts = {value: 0 for value in UX_CLASSIFICATIONS}
    for index, row in enumerate(items, start=1):
        item_id = (row.get("item_id") or "").strip()
        observation_id = (row.get("observation_id") or "").strip()
        if not item_id or item_id in item_ids:
            failures.append(f"UX 개발 항목 {index}의 item_id가 없거나 중복입니다.")
        item_ids.add(item_id)
        if observation_id not in observation_ids:
            failures.append(
                f"UX 개발 항목 {item_id or index}가 존재하지 않는 관찰을 참조합니다."
            )
        linked_observations.append(observation_id)
        decision = (row.get("decision") or "").strip()
        if decision not in UX_DECISIONS:
            failures.append(
                f"UX 개발 항목 {item_id or index}의 수용/불수용/검토 결정이 올바르지 않습니다."
            )
        priority = (row.get("priority") or "").strip()
        classification = (row.get("classification") or "").strip()
        if priority not in priority_counts:
            failures.append(
                f"UX 개발 항목 {item_id or index}의 우선순위가 올바르지 않습니다."
            )
        else:
            priority_counts[priority] += 1
        if classification not in classification_counts:
            failures.append(
                f"UX 개발 항목 {item_id or index}의 분류가 올바르지 않습니다."
            )
        else:
            classification_counts[classification] += 1
        for field in (
            "decision_basis",
            "title",
            "acceptance_criteria",
            "owner",
            "due_date",
            "status",
        ):
            if not nonempty(row.get(field)):
                failures.append(
                    f"UX 개발 항목 {item_id or index}의 {field} 값이 없습니다."
                )
        try:
            date.fromisoformat((row.get("due_date") or "").strip())
        except ValueError:
            failures.append(
                f"UX 개발 항목 {item_id or index}의 due_date 형식이 올바르지 않습니다."
            )
        failures.extend(
            evidence_failures(
                run_root,
                [(row.get("evidence") or "").strip()],
                f"UX 개발 항목 {item_id or index}",
            )
        )
    if set(linked_observations) != observation_ids or len(linked_observations) != len(
        observation_ids
    ):
        failures.append(
            "모든 현장 관찰은 수용/불수용/검토와 근거를 가진 개발 항목 하나로 변환되어야 합니다."
        )
    if expected.get("actionable_findings") != len(actionable_ids):
        failures.append("UX 조치 가능 관찰 원시 건수와 요약값이 다릅니다.")
    if expected.get("converted_items") != len(items):
        failures.append("UX 개발 항목 원시 건수와 요약값이 다릅니다.")
    if expected.get("unconverted_actionable_findings") != len(
        actionable_ids - set(linked_observations)
    ):
        failures.append("UX 미변환 관찰 원시 건수와 요약값이 다릅니다.")
    if expected.get("priorities") != priority_counts:
        failures.append("UX 개발 항목의 원시 우선순위 집계와 요약값이 다릅니다.")
    if expected.get("classifications") != classification_counts:
        failures.append("UX 개발 항목의 원시 분류 집계와 요약값이 다릅니다.")
    failures.extend(ux_revalidation_csv_failures(run_root, observations, items))
    return failures


def ux_revalidation_csv_failures(
    run_root: Path,
    observations: list[dict[str, str]],
    items: list[dict[str, str]],
) -> list[str]:
    high_priority_items = [
        row
        for row in items
        if (row.get("decision") or "").strip() == "ACCEPTED"
        and (row.get("priority") or "").strip() in ("P0", "P1")
    ]
    if not high_priority_items:
        return []
    rows, failures = read_csv_rows(
        run_root,
        "scenario-results/role-ux-comparison.csv",
        "P0/P1 UX 수정 전후 재검증",
    )
    observations_by_id = {
        (row.get("observation_id") or "").strip(): row for row in observations
    }
    comparisons: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        comparison_id = (row.get("comparison_id") or "").strip()
        if comparison_id:
            comparisons.setdefault(comparison_id, []).append(row)

    for item in high_priority_items:
        item_id = (item.get("item_id") or "").strip() or "식별자 없음"
        comparison_id = (item.get("comparison_id") or "").strip()
        development_cycle_id = (item.get("development_cycle_id") or "").strip()
        status = (item.get("status") or "").strip().upper()
        if not comparison_id or not development_cycle_id:
            failures.append(
                f"수용한 P0/P1 UX 개발 항목 {item_id}에 development_cycle_id와 comparison_id가 필요합니다."
            )
            continue
        if status not in ("VERIFIED", "CLOSED"):
            failures.append(
                f"수용한 P0/P1 UX 개발 항목 {item_id}의 status는 VERIFIED 또는 CLOSED여야 합니다."
            )
        matching = comparisons.get(comparison_id, [])
        if not matching:
            failures.append(
                f"수용한 P0/P1 UX 개발 항목 {item_id}의 수정 전후 비교 {comparison_id}가 없습니다."
            )
            continue

        observation = observations_by_id.get(
            (item.get("observation_id") or "").strip(), {}
        )
        expected_role = (observation.get("role") or "").strip()
        expected_scenario = (observation.get("scenario_id") or "").strip()
        phases: dict[str, list[dict[str, str]]] = {"BEFORE": [], "AFTER": []}
        identities: set[tuple[str, str, str, str]] = set()
        builds: dict[str, set[str]] = {"BEFORE": set(), "AFTER": set()}
        attempt_keys: set[tuple[str, int]] = set()
        numeric: dict[str, dict[str, list[float]]] = {
            phase: {
                "elapsed_seconds": [],
                "screen_transitions": [],
                "help_request_count": [],
            }
            for phase in phases
        }
        for index, row in enumerate(matching, start=1):
            label = f"UX 비교 {comparison_id} 행 {index}"
            phase = (row.get("ui_phase") or "").strip().upper()
            if phase not in phases:
                failures.append(f"{label}의 ui_phase는 BEFORE 또는 AFTER여야 합니다.")
                continue
            phases[phase].append(row)
            role = (row.get("role") or "").strip()
            participant = (row.get("participant_id") or "").strip()
            scenario = (row.get("scenario_id") or "").strip()
            cycle = (row.get("development_cycle_id") or "").strip()
            build = (row.get("ui_build") or "").strip()
            if not all((role, participant, scenario, cycle, build)):
                failures.append(
                    f"{label}의 역할·익명 참여자·시나리오·개발 주기·UI build가 모두 필요합니다."
                )
            identities.add((role, participant, scenario, cycle))
            if build:
                builds[phase].add(build)
            if role != expected_role or scenario != expected_scenario:
                failures.append(
                    f"{label}가 원 관찰의 역할·시나리오와 다릅니다."
                )
            if cycle != development_cycle_id:
                failures.append(
                    f"{label}의 개발 주기가 UX 개발 항목 {item_id}와 다릅니다."
                )
            try:
                attempt_no = int((row.get("attempt_no") or "").strip())
                if attempt_no < 1 or (phase, attempt_no) in attempt_keys:
                    raise ValueError
            except ValueError:
                failures.append(
                    f"{label}의 attempt_no는 단계 안에서 중복 없는 1 이상의 정수여야 합니다."
                )
            else:
                attempt_keys.add((phase, attempt_no))
            if csv_bool(row.get("success")) is None:
                failures.append(f"{label}의 success 값이 올바르지 않습니다.")
            try:
                elapsed = float((row.get("elapsed_seconds") or "").strip())
                click_count = int((row.get("click_count") or "").strip())
                transitions = int((row.get("screen_transitions") or "").strip())
                help_count = int((row.get("help_request_count") or "").strip())
                if min(elapsed, click_count, transitions, help_count) < 0:
                    raise ValueError
            except ValueError:
                failures.append(
                    f"{label}의 시간·선택·화면 이동·도움 요청 값이 올바르지 않습니다."
                )
            else:
                numeric[phase]["elapsed_seconds"].append(elapsed)
                numeric[phase]["screen_transitions"].append(float(transitions))
                numeric[phase]["help_request_count"].append(float(help_count))
            failures.extend(
                evidence_failures(
                    run_root,
                    [(row.get("screen_capture_evidence") or "").strip()],
                    f"{label} 화면 증거",
                )
            )

        if len(identities) != 1:
            failures.append(
                f"UX 비교 {comparison_id}는 같은 역할·익명 참여자·시나리오·개발 주기로 수행해야 합니다."
            )
        for phase in ("BEFORE", "AFTER"):
            if len(phases[phase]) < 2:
                failures.append(
                    f"UX 비교 {comparison_id}의 {phase} 단계는 2회 이상 수행해야 합니다."
                )
            if len(builds[phase]) != 1:
                failures.append(
                    f"UX 비교 {comparison_id}의 {phase} 단계는 하나의 UI build로 측정해야 합니다."
                )
        if builds["BEFORE"] & builds["AFTER"]:
            failures.append(
                f"UX 비교 {comparison_id}의 BEFORE와 AFTER UI build는 달라야 합니다."
            )
        if phases["AFTER"] and any(
            csv_bool(row.get("success")) is not True for row in phases["AFTER"]
        ):
            failures.append(
                f"UX 비교 {comparison_id}의 AFTER 시도는 모두 성공해야 합니다."
            )
        for field, label in (
            ("elapsed_seconds", "중앙 완료 시간"),
            ("screen_transitions", "중앙 화면 이동 수"),
            ("help_request_count", "중앙 도움 요청 수"),
        ):
            before_values = numeric["BEFORE"][field]
            after_values = numeric["AFTER"][field]
            if (
                before_values
                and after_values
                and statistics.median(after_values)
                > statistics.median(before_values)
            ):
                failures.append(
                    f"UX 비교 {comparison_id}의 AFTER {label}이 BEFORE보다 나빠졌습니다."
                )
    return failures


def restore_comparison_failures(
    run_root: Path, evidence: Any, target: str
) -> list[str]:
    if not isinstance(evidence, list):
        return [f"{target} 복구 비교 증거 목록이 없습니다."]
    candidates = [
        Path(value)
        for value in evidence
        if isinstance(value, str) and value.endswith("-comparison.json")
    ]
    for candidate in candidates:
        try:
            report = json.loads((run_root / candidate).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        manifests: dict[str, dict[str, Any]] = {}
        manifests_ok = True
        for phase in ("before", "after"):
            raw_path = report.get(f"{phase}_manifest")
            manifest_path = Path(raw_path) if isinstance(raw_path, str) else Path(".")
            if (
                not isinstance(raw_path, str)
                or manifest_path.is_absolute()
                or ".." in manifest_path.parts
                or not (run_root / manifest_path).is_file()
            ):
                manifests_ok = False
                break
            try:
                manifests[phase] = json.loads(
                    (run_root / manifest_path).read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError):
                manifests_ok = False
                break
            if sha256(run_root / manifest_path) != report.get(
                f"{phase}_manifest_sha256"
            ):
                manifests_ok = False
                break
        if manifests_ok:
            before_manifest = manifests["before"]
            after_manifest = manifests["after"]
            manifests_ok = (
                before_manifest.get("run_id") == run_root.name
                and after_manifest.get("run_id") == run_root.name
                and before_manifest.get("target") == target
                and after_manifest.get("target") == target
                and before_manifest.get("phase") == "before"
                and after_manifest.get("phase") == "after"
                and before_manifest.get("machine_id") == report.get("source_machine_id")
                and after_manifest.get("machine_id") == report.get("restore_machine_id")
                and before_manifest.get("backup_set_id") == report.get("backup_set_id")
                and after_manifest.get("backup_set_id") == report.get("backup_set_id")
                and before_manifest.get("restore_approval_id")
                == report.get("restore_approval_id")
                and after_manifest.get("restore_approval_id")
                == report.get("restore_approval_id")
            )
        if (
            manifests_ok
            and report.get("run_id") == run_root.name
            and report.get("target") == target
            and report.get("result") == "PASS"
            and report.get("table_counts_equal") is True
            and report.get("table_count_mismatch_count") == 0
            and report.get("file_manifest_equal") is True
            and report.get("file_mismatch_counts")
            == {"missing": 0, "extra": 0, "size": 0, "sha256": 0}
            and nonempty(report.get("source_machine_id"))
            and nonempty(report.get("restore_machine_id"))
            and normalized_identity(report.get("source_machine_id"))
            != normalized_identity(report.get("restore_machine_id"))
            and nonempty(report.get("backup_set_id"))
            and nonempty(report.get("restore_approval_id"))
            and report.get("database_checks", {}).get("before_quick_check_ok") is True
            and report.get("database_checks", {}).get("before_integrity_check_ok")
            is True
            and report.get("database_checks", {}).get(
                "before_foreign_key_violation_count"
            )
            == 0
            and report.get("database_checks", {}).get("after_quick_check_ok") is True
            and report.get("database_checks", {}).get("after_integrity_check_ok")
            is True
            and report.get("database_checks", {}).get(
                "after_foreign_key_violation_count"
            )
            == 0
            and report.get("database_checks", {}).get("before_capture_stable")
            is True
            and report.get("database_checks", {}).get("before_checkpoint_clean")
            is True
            and report.get("database_checks", {}).get("after_capture_stable")
            is True
            and report.get("database_checks", {}).get("after_checkpoint_clean")
            is True
            and report.get("file_capture_checks", {}).get("before_capture_stable")
            is True
            and report.get("file_capture_checks", {}).get("after_capture_stable")
            is True
        ):
            return []
    return [f"{target} 복구 게이트에 같은 run_id의 PASS comparison JSON이 없습니다."]


def restore_set_binding_failures(
    run_root: Path, server_evidence: Any, wpf_evidence: Any
) -> list[str]:
    return pilot_restore_gate.restore_set_binding_failures(
        run_root, server_evidence, wpf_evidence
    )


def verify(args: argparse.Namespace) -> int:
    record_path = args.evidence_root / args.run_id / "pilot-run.json"
    run_root = record_path.parent
    record = json.loads(record_path.read_text(encoding="utf-8"))
    failures: list[str] = []
    if record.get("run_id") != args.run_id:
        failures.append("판정표 run_id가 실행 폴더 run_id와 다릅니다.")
    if record.get("schema_version") != SCHEMA_VERSION:
        failures.append(
            f"pilot-run.json schema_version은 {SCHEMA_VERSION}이어야 합니다."
        )
    profile = record.get("profile")
    if profile not in RUN_PROFILES:
        failures.append("지원하는 파일럿 profile이 아닙니다.")
        profile = "full_pilot"

    environment = record.get("environment", {})
    if environment.get("customer_like_network") is not True:
        failures.append("고객 유사망 실행이 확인되지 않았습니다.")
    required_environment_counts = ["clean_server_count", "clean_windows_client_count"]
    if profile == "full_pilot":
        required_environment_counts.append("approved_android_count")
    for field in required_environment_counts:
        if not isinstance(environment.get(field), int) or environment[field] < 1:
            failures.append(f"environment.{field}는 1 이상이어야 합니다.")

    responsibilities = record.get("responsibilities", {})
    for area in RESPONSIBILITY_AREAS:
        assignment = responsibilities.get(area, {})
        if not nonempty(assignment.get("owner")) or not nonempty(
            assignment.get("approver")
        ):
            failures.append(f"책임 영역 {area}의 담당자와 승인자가 모두 필요합니다.")
        elif normalized_identity(assignment.get("owner")) == normalized_identity(
            assignment.get("approver")
        ):
            failures.append(f"책임 영역 {area}는 담당자와 독립 승인자가 달라야 합니다.")
        for field, label in (
            ("test_scope", "시험 범위"),
            ("stop_criteria", "중단 기준"),
            ("evidence_repository", "증거 저장소"),
        ):
            if not nonempty(assignment.get(field)):
                failures.append(f"책임 영역 {area}의 {label}가 필요합니다.")
        failures.extend(
            evidence_failures(
                run_root,
                assignment.get("approval_evidence"),
                f"책임 영역 {area} 사전 승인",
            )
        )

    authorization = record.get("authorization", {})
    if authorization.get("decision") != "PASS" or not nonempty(
        authorization.get("approved_at")
    ):
        failures.append("리허설 책임·범위 사전 승인의 PASS와 승인 시각이 필요합니다.")
    for field, label in (
        ("run_scope", "통합 시험 범위"),
        ("evidence_repository", "통합 증거 저장소"),
    ):
        if not nonempty(authorization.get(field)):
            failures.append(f"리허설 사전 승인의 {label}가 필요합니다.")
    stop_criteria = authorization.get("stop_criteria")
    if (
        not isinstance(stop_criteria, list)
        or not all(nonempty(value) for value in stop_criteria)
        or len(stop_criteria) < 5
    ):
        failures.append(
            "리허설 사전 승인에는 5개 이상의 구체적 중단 기준이 필요합니다."
        )
    try:
        if not nonempty(authorization.get("retention_until")):
            raise ValueError
        date.fromisoformat(authorization["retention_until"])
    except ValueError:
        failures.append("증거 보존 기한은 YYYY-MM-DD 형식으로 필요합니다.")
    equipment = authorization.get("equipment", {})
    failures.extend(
        identifier_list_failures(equipment.get("server_ids"), 1, "시험 서버")
    )
    failures.extend(
        identifier_list_failures(
            equipment.get("windows_client_ids"), 1, "시험 Windows 클라이언트"
        )
    )
    if profile == "full_pilot":
        failures.extend(
            identifier_list_failures(
                equipment.get("android_device_ids"), 1, "시험 Android 단말"
            )
        )
    for count_field, id_field, label in (
        ("clean_server_count", "server_ids", "시험 서버"),
        ("clean_windows_client_count", "windows_client_ids", "시험 Windows 클라이언트"),
    ):
        ids = equipment.get(id_field)
        if isinstance(ids, list) and environment.get(count_field) != len(ids):
            failures.append(
                f"{label} 식별자 수와 environment.{count_field}가 다릅니다."
            )
    if profile == "full_pilot":
        android_ids = equipment.get("android_device_ids")
        if isinstance(android_ids, list) and environment.get(
            "approved_android_count"
        ) != len(android_ids):
            failures.append(
                "시험 Android 단말 식별자 수와 environment.approved_android_count가 다릅니다."
            )
    versions = authorization.get("previous_approved_versions", {})
    version_targets = (
        ("server", "wpf", "android") if profile == "full_pilot" else ("server", "wpf")
    )
    for target in version_targets:
        if not nonempty(versions.get(target)):
            failures.append(f"리허설 전 {target} 이전 승인 버전 확정이 필요합니다.")
    failures.extend(
        evidence_failures(
            run_root, authorization.get("evidence"), "리허설 통합 사전 승인"
        )
    )

    gates = record.get("gates", {})
    required_gates = (
        REQUIRED_GATES if profile == "full_pilot" else WINDOWS_SERVER_REHEARSAL_GATES
    )
    for gate in required_gates:
        item = gates.get(gate, {})
        if item.get("result") != "PASS":
            failures.append(f"필수 게이트 {gate}가 PASS가 아닙니다.")
        failures.extend(
            evidence_failures(run_root, item.get("evidence"), f"게이트 {gate}")
        )
    if profile == "full_pilot":
        failures.extend(
            restore_comparison_failures(
                run_root,
                gates.get("server_restore_separate_pc", {}).get("evidence"),
                "server",
            )
        )
        failures.extend(restore_fault_injection_failures(run_root))
        failures.extend(
            restore_comparison_failures(
                run_root,
                gates.get("wpf_restore_separate_pc", {}).get("evidence"),
                "wpf",
            )
        )
        failures.extend(
            restore_set_binding_failures(
                run_root,
                gates.get("server_restore_separate_pc", {}).get("evidence"),
                gates.get("wpf_restore_separate_pc", {}).get("evidence"),
            )
        )
    else:
        failures.extend(
            windows_server_evidence.verification_failures(
                run_root,
                args.run_id,
                record,
                evidence_failures,
                restore_comparison_failures,
            )
        )
        failures.extend(
            restore_set_binding_failures(
                run_root,
                gates.get("server_restore_separate_pc", {}).get("evidence"),
                gates.get("wpf_restore_separate_pc", {}).get("evidence"),
            )
        )

    zero_tolerance = record.get("zero_tolerance", {})
    required_zero_metrics = (
        ZERO_TOLERANCE_METRICS
        if profile == "full_pilot"
        else WINDOWS_SERVER_ZERO_TOLERANCE_METRICS
    )
    for metric in required_zero_metrics:
        if zero_tolerance.get(metric) != 0:
            failures.append(f"0건 필수 지표 {metric}이 0이 아닙니다.")

    roles = record.get("roles", {})
    for role in REQUIRED_ROLES if profile == "full_pilot" else ():
        metric = roles.get(role, {})
        required = metric.get("required_attempts")
        successful = metric.get("successful_attempts")
        rate = metric.get("success_rate_percent")
        minimum_rate = metric.get("approved_minimum_percent")
        median = metric.get("median_seconds")
        maximum_median = metric.get("approved_max_median_seconds")
        maximum = metric.get("maximum_seconds")
        approved_maximum = metric.get("approved_maximum_seconds")
        if not isinstance(required, int) or required <= 0:
            failures.append(f"역할 {role}의 필수 시나리오 분모가 없습니다.")
        if (
            not isinstance(successful, int)
            or not isinstance(required, int)
            or not 0 <= successful <= required
        ):
            failures.append(f"역할 {role}의 성공 건수가 올바르지 않습니다.")
        rates_are_numeric = all(
            isinstance(value, (int, float)) for value in (rate, minimum_rate)
        )
        if not rates_are_numeric or not 0 < minimum_rate <= rate <= 100:
            failures.append(
                f"역할 {role}의 성공률이 승인 기준에 미달하거나 미측정입니다."
            )
        elif minimum_rate < 95 or rate < 95:
            failures.append(f"역할 {role}의 성공률은 95% 이상이어야 합니다.")
        if (
            isinstance(required, int)
            and required > 0
            and isinstance(successful, int)
            and 0 <= successful <= required
            and isinstance(rate, (int, float))
            and abs(rate - (successful / required * 100)) > 0.01
        ):
            failures.append(
                f"역할 {role}의 성공률과 성공/분모 계산이 일치하지 않습니다."
            )
        if (
            not all(
                isinstance(value, (int, float)) for value in (median, maximum_median)
            )
            or not 0 <= median <= maximum_median
            or maximum_median <= 0
        ):
            failures.append(
                f"역할 {role}의 중앙 소요 시간이 승인 기준을 초과하거나 미측정입니다."
            )
        if (
            not all(
                isinstance(value, (int, float)) for value in (maximum, approved_maximum)
            )
            or not 0 <= maximum <= approved_maximum
            or approved_maximum <= 0
        ):
            failures.append(
                f"역할 {role}의 최대 소요 시간이 승인 기준을 초과하거나 미측정입니다."
            )
        if (
            isinstance(median, (int, float))
            and isinstance(maximum, (int, float))
            and median > maximum
        ):
            failures.append(
                f"역할 {role}의 중앙 소요 시간이 최대 소요 시간보다 큽니다."
            )
        for count_name, count_label in (
            ("retry_count", "재시도"),
            ("help_request_count", "도움 요청"),
            ("screen_transition_count", "화면 이동"),
        ):
            count = metric.get(count_name)
            if not isinstance(count, int) or count < 0:
                failures.append(f"역할 {role}의 {count_label} 횟수가 미측정입니다.")
        if metric.get("critical_blockers") != 0:
            failures.append(f"역할 {role}의 치명적 blocker가 0이 아닙니다.")
        if not nonempty(metric.get("time_limit_approval_id")) or not nonempty(
            metric.get("time_limit_approved_at")
        ):
            failures.append(
                f"역할 {role}의 실제 관찰값 기반 시간 한도 승인 ID/시각이 없습니다."
            )
        failures.extend(
            evidence_failures(run_root, metric.get("evidence"), f"역할 {role}")
        )
    if profile == "full_pilot":
        failures.extend(role_metrics_csv_failures(run_root, roles))

    android_delivery = record.get("android_delivery", {})
    delivery_scenarios = android_delivery.get("scenarios", {})
    for scenario in ANDROID_DELIVERY_SCENARIOS if profile == "full_pilot" else ():
        metric = delivery_scenarios.get(scenario, {})
        required = metric.get("required_attempts")
        successful = metric.get("successful_attempts")
        maximum = metric.get("maximum_seconds")
        page_seconds = metric.get("page_seconds")
        allowed = metric.get("allowed_seconds")
        if not isinstance(required, int) or required <= 0:
            failures.append(f"Android 전달 시나리오 {scenario}의 분모가 없습니다.")
        if (
            not isinstance(successful, int)
            or not isinstance(required, int)
            or successful != required
        ):
            failures.append(
                f"Android 전달 시나리오 {scenario}가 전건 성공하지 않았습니다."
            )
        if (
            not all(isinstance(value, (int, float)) for value in (maximum, allowed))
            or not 0 <= maximum <= allowed
            or allowed <= 0
        ):
            failures.append(
                f"Android 전달 시나리오 {scenario}가 허용 시간을 초과하거나 미측정입니다."
            )
        if scenario in ("normal", "doze") and allowed != 30:
            failures.append(
                f"Android 전달 시나리오 {scenario}의 허용 시간은 30초여야 합니다."
            )
        if scenario == "disconnect_5m":
            if not isinstance(page_seconds, (int, float)) or page_seconds < 0:
                failures.append("Android 5분 단절 복구의 page 시간이 미측정입니다.")
            elif allowed != 30 + page_seconds:
                failures.append(
                    "Android 5분 단절 복구 허용 시간은 30초+page 시간이어야 합니다."
                )
        failures.extend(
            evidence_failures(
                run_root,
                metric.get("evidence"),
                f"Android 전달 시나리오 {scenario}",
            )
        )
    for metric_name, label in (
        (
            ("lost_messages", "누락 메시지"),
            ("server_receipt_duplicates", "서버 receipt 중복"),
        )
        if profile == "full_pilot"
        else ()
    ):
        if android_delivery.get(metric_name) != 0:
            failures.append(f"Android {label}가 0건이 아닙니다.")
    display_duplicates = android_delivery.get("crash_boundary_display_duplicates")
    if profile == "full_pilot" and (
        not isinstance(display_duplicates, int) or not 0 <= display_duplicates <= 1
    ):
        failures.append("Android crash 경계 표시 중복이 0~1건이 아니거나 미측정입니다.")
    if profile == "full_pilot":
        failures.extend(
            evidence_failures(
                run_root, android_delivery.get("evidence"), "Android 전달 종합"
            )
        )
        failures.extend(android_delivery_csv_failures(run_root, delivery_scenarios))
        failures.extend(
            android_delivery_integrity_csv_failures(
                run_root, args.run_id, android_delivery
            )
        )

    android_security = record.get("android_security", {})
    for check_name in (
        (
            "keystore_token_ciphertext_verified",
            "outbox_ciphertext_verified",
            "encrypted_photo_verified",
            "wrong_key_decryption_failed",
            "secure_cache_cleared_after_exit",
            "flag_secure_verified",
            "external_share_absent",
            "backup_disabled",
        )
        if profile == "full_pilot"
        else ()
    ):
        if android_security.get(check_name) is not True:
            failures.append(f"Android 보안 실기 {check_name}가 확인되지 않았습니다.")
    if profile == "full_pilot":
        failures.extend(
            evidence_failures(
                run_root, android_security.get("evidence"), "Android 보안 실기"
            )
        )
        failures.extend(
            required_android_csv_failures(
                run_root,
                "integrity/android-security.csv",
                "check_id",
                ANDROID_SECURITY_CHECKS,
                "Android 보안 원시 결과",
                ("checked_at", "device_id"),
            )
        )

    device_lifecycle = record.get("android_device_lifecycle", {})
    if (
        profile == "full_pilot"
        and device_lifecycle.get("lost_or_inactive_device_reconnect_blocked")
        is not True
    ):
        failures.append("분실·비활성 Android 단말의 재접속 차단이 확인되지 않았습니다.")
    if (
        profile == "full_pilot"
        and device_lifecycle.get("replacement_history_preserved") is not True
    ):
        failures.append("Android 단말 교체 이력 보존이 확인되지 않았습니다.")
    if profile == "full_pilot":
        failures.extend(
            evidence_failures(
                run_root,
                device_lifecycle.get("evidence"),
                "Android 단말 수명주기",
            )
        )
        failures.extend(
            required_android_csv_failures(
                run_root,
                "scenario-results/android-device-lifecycle.csv",
                "scenario_id",
                ANDROID_DEVICE_LIFECYCLE_CASES,
                "Android 단말 수명주기 원시 결과",
                (
                    "checked_at",
                    "old_device_id",
                    "server_status",
                    "history_event_ids",
                    "mdm_event_id",
                ),
            )
        )
        failures.extend(
            required_android_csv_failures(
                run_root,
                "packages/android-release-approval.csv",
                "artifact_role",
                ("release_candidate", "previous_approved_rollback"),
                "Android 운영 패키지 승인",
                (
                    "artifact_type",
                    "version_name",
                    "version_code",
                    "sha256",
                    "signer_sha256",
                    "mdm_package_id",
                    "rollout_ring",
                    "approval_id",
                ),
            )
        )

    ux_items = record.get("ux_development_items", {})
    actionable = ux_items.get("actionable_findings")
    converted = ux_items.get("converted_items")
    unconverted = ux_items.get("unconverted_actionable_findings")
    if profile == "full_pilot" and (
        not all(
            isinstance(value, int) and value >= 0 for value in (actionable, converted)
        )
        or actionable != converted
        or unconverted != 0
    ):
        failures.append("UX 조치 가능 관찰이 모두 개발 항목으로 변환되지 않았습니다.")
    priorities = ux_items.get("priorities", {})
    classifications = ux_items.get("classifications", {})
    priority_counts = [
        priorities.get(priority) for priority in ("P0", "P1", "P2", "P3")
    ]
    classification_counts = [
        classifications.get(classification)
        for classification in (
            "common_product",
            "device_or_mdm_setting",
            "site_layout_or_training",
        )
    ]
    for counts, label in (
        (
            (priority_counts, "P0~P3 우선순위"),
            (classification_counts, "제품/설정/배치·교육 분류"),
        )
        if profile == "full_pilot"
        else ()
    ):
        if (
            not all(isinstance(value, int) and value >= 0 for value in counts)
            or not isinstance(converted, int)
            or sum(counts) != converted
        ):
            failures.append(f"UX 개발 항목의 {label} 합계가 변환 건수와 다릅니다.")
    if profile == "full_pilot":
        failures.extend(
            evidence_failures(run_root, ux_items.get("evidence"), "UX 개발 항목 변환")
        )
        failures.extend(ux_csv_failures(run_root, ux_items))

    rollback = record.get("rollback", {})
    rollback_targets = (
        ("server", "wpf", "android") if profile == "full_pilot" else ("server", "wpf")
    )
    for target in rollback_targets:
        item = rollback.get(target, {})
        if item.get("result") != "PASS" or item.get("normal_work_resumed") is not True:
            failures.append(f"{target} rollback과 정상 업무 재개가 PASS가 아닙니다.")
        if not nonempty(item.get("previous_approved_version")):
            failures.append(f"{target}의 이전 승인 버전이 없습니다.")
        elif item.get("previous_approved_version") != versions.get(target):
            failures.append(
                f"{target} rollback 버전이 리허설 전 확정한 이전 승인 버전과 다릅니다."
            )
        failures.extend(
            evidence_failures(run_root, item.get("evidence"), f"rollback {target}")
        )

    for index, item in enumerate(record.get("remaining_items", []), start=1):
        if not all(
            nonempty(item.get(field)) for field in ("owner", "due_date", "stop_impact")
        ):
            failures.append(
                f"남은 항목 {index}에 책임자·기한·중단 영향이 모두 필요합니다."
            )
        else:
            try:
                date.fromisoformat(item["due_date"])
            except ValueError:
                failures.append(
                    f"남은 항목 {index}의 기한은 YYYY-MM-DD 형식이어야 합니다."
                )

    approvals = record.get("final_approvals", {})
    for area in REQUIRED_APPROVALS:
        approval = approvals.get(area, {})
        if (
            approval.get("decision") != "PASS"
            or not nonempty(approval.get("signer"))
            or not nonempty(approval.get("signed_at"))
        ):
            failures.append(f"최종 승인 {area}의 PASS 서명이 없습니다.")
        failures.extend(
            evidence_failures(run_root, approval.get("evidence"), f"최종 승인 {area}")
        )
    if record.get("status") != "PASS":
        failures.append("pilot-run.json의 최종 status가 PASS가 아닙니다.")

    report = {
        "schema_version": SCHEMA_VERSION,
        "run_id": args.run_id,
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "result": "PASS" if not failures else "FAIL",
        "failure_count": len(failures),
        "failures": failures,
    }
    output = run_root / "pilot-verification.json"
    write_json(output, report)
    print(f"파일럿 판정: {report['result']}")
    print(f"판정 증거: {output}")
    for failure in failures:
        print(f"FAIL: {failure}", file=sys.stderr)
    return 0 if not failures else 1


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="FlowNote 실제 파일럿 실행 준비·완료 판정 도구"
    )
    commands = result.add_subparsers(dest="command", required=True)
    prepare_parser = commands.add_parser(
        "prepare", help="단일 run_id 증거 구조와 초기 판정표를 만듭니다."
    )
    prepare_parser.add_argument("--run-id", required=True, type=validate_run_id)
    prepare_parser.add_argument("--evidence-root", required=True, type=Path)
    prepare_parser.add_argument("--profile", choices=RUN_PROFILES, default="full_pilot")
    prepare_parser.add_argument("--allow-existing", action="store_true")
    prepare_parser.set_defaults(handler=prepare)
    verify_parser = commands.add_parser(
        "verify", help="필수 게이트와 현장 증거를 엄격히 판정합니다."
    )
    verify_parser.add_argument("--run-id", required=True, type=validate_run_id)
    verify_parser.add_argument("--evidence-root", required=True, type=Path)
    verify_parser.set_defaults(handler=verify)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        return args.handler(args)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
