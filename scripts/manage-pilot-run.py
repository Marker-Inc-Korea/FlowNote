#!/usr/bin/env python3
"""Create and strictly validate a FlowNote PILOT evidence run."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


RUN_ID_PATTERN = re.compile(r"^PILOT-\d{8}-\d{4}-[A-Z0-9_-]+-\d{3}$")
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
REQUIRED_ROLES = ("admin", "line_foreman", "team_lead", "team_member")
REQUIRED_APPROVALS = ("operations", "security", "field_operations")
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


def empty_record(run_id: str) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "run_id": run_id,
        "status": "PENDING",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "customer_like_network": False,
            "clean_server_count": 0,
            "clean_windows_client_count": 0,
            "approved_android_count": 0,
        },
        "responsibilities": {
            area: {"owner": "", "approver": ""} for area in RESPONSIBILITY_AREAS
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
                "critical_blockers": None,
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
            "priorities": {priority: None for priority in ("P0", "P1", "P2", "P3")},
            "classifications": {
                classification: None
                for classification in (
                    "common_product",
                    "device_or_mdm_setting",
                    "site_layout_or_training",
                )
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
        write_json(record_path, empty_record(args.run_id))
    manifest = run_root / "manifest.md"
    if not manifest.exists():
        manifest.write_text(
            f"# {args.run_id}\n\n"
            "- 상태: 대기\n- 현장/라인 코드:\n- 시작 시각/시간대:\n"
            "- 종료 시각/시간대:\n- 이전 승인 서버/WPF/Android 버전:\n"
            "- 최종 판정: 대기\n",
            encoding="utf-8",
        )
    android_delivery_rows = "".join(
        ",".join([scenario_id, condition, *("" for _ in range(9)), "NOT_RUN", ""])
        + "\n"
        for scenario_id, condition in ANDROID_DELIVERY_CASES
    )
    templates = {
        run_root / "scenario-results" / "android-delivery.csv": (
            "scenario_id,condition,delivery_run_id,message_id,created_at_utc,"
            "recovery_ready_at_utc,displayed_at_utc,receipt_at_utc,page_seconds,"
            "elapsed_seconds,allowed_seconds,result,evidence\n" + android_delivery_rows
        ),
        run_root / "scenario-results" / "role-metrics.csv": (
            "role,participant_id,scenario_id,required,success,elapsed_seconds,"
            "retry_count,help_request_count,critical_blocker,evidence\n"
        ),
        run_root / "observations" / "role-observations.csv": (
            "observation_id,role,scenario_id,device_id,location,network,gloves,"
            "one_hand,lighting,input_moment,success,elapsed_seconds,retry_count,"
            "help_request_count,notes\n"
        ),
        run_root / "observations" / "development-items.csv": (
            "item_id,observation_id,priority,classification,title,acceptance_criteria,"
            "owner,due_date,status\n"
        ),
    }
    for path, header in templates.items():
        if not path.exists():
            path.write_text(header, encoding="utf-8")
    print(f"파일럿 실행 폴더 준비: {run_root}")
    print(f"기계 판정표: {record_path}")
    print("초기 판정: PENDING")
    return 0


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


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
        if (
            report.get("run_id") == run_root.name
            and report.get("target") == target
            and report.get("result") == "PASS"
            and report.get("table_counts_equal") is True
            and report.get("file_manifest_equal") is True
        ):
            return []
    return [f"{target} 복구 게이트에 같은 run_id의 PASS comparison JSON이 없습니다."]


def verify(args: argparse.Namespace) -> int:
    record_path = args.evidence_root / args.run_id / "pilot-run.json"
    run_root = record_path.parent
    record = json.loads(record_path.read_text(encoding="utf-8"))
    failures: list[str] = []
    if record.get("run_id") != args.run_id:
        failures.append("판정표 run_id가 실행 폴더 run_id와 다릅니다.")
    if record.get("schema_version") != 2:
        failures.append("pilot-run.json schema_version은 2여야 합니다.")

    environment = record.get("environment", {})
    if environment.get("customer_like_network") is not True:
        failures.append("고객 유사망 실행이 확인되지 않았습니다.")
    for field in (
        "clean_server_count",
        "clean_windows_client_count",
        "approved_android_count",
    ):
        if not isinstance(environment.get(field), int) or environment[field] < 1:
            failures.append(f"environment.{field}는 1 이상이어야 합니다.")

    responsibilities = record.get("responsibilities", {})
    for area in RESPONSIBILITY_AREAS:
        assignment = responsibilities.get(area, {})
        if not nonempty(assignment.get("owner")) or not nonempty(
            assignment.get("approver")
        ):
            failures.append(f"책임 영역 {area}의 담당자와 승인자가 모두 필요합니다.")

    gates = record.get("gates", {})
    for gate in REQUIRED_GATES:
        item = gates.get(gate, {})
        if item.get("result") != "PASS":
            failures.append(f"필수 게이트 {gate}가 PASS가 아닙니다.")
        failures.extend(
            evidence_failures(run_root, item.get("evidence"), f"게이트 {gate}")
        )
    failures.extend(
        restore_comparison_failures(
            run_root,
            gates.get("server_restore_separate_pc", {}).get("evidence"),
            "server",
        )
    )
    failures.extend(
        restore_comparison_failures(
            run_root,
            gates.get("wpf_restore_separate_pc", {}).get("evidence"),
            "wpf",
        )
    )

    zero_tolerance = record.get("zero_tolerance", {})
    for metric in ZERO_TOLERANCE_METRICS:
        if zero_tolerance.get(metric) != 0:
            failures.append(f"0건 필수 지표 {metric}이 0이 아닙니다.")

    roles = record.get("roles", {})
    for role in REQUIRED_ROLES:
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
        ):
            count = metric.get(count_name)
            if not isinstance(count, int) or count < 0:
                failures.append(f"역할 {role}의 {count_label} 횟수가 미측정입니다.")
        if metric.get("critical_blockers") != 0:
            failures.append(f"역할 {role}의 치명적 blocker가 0이 아닙니다.")
        failures.extend(
            evidence_failures(run_root, metric.get("evidence"), f"역할 {role}")
        )

    android_delivery = record.get("android_delivery", {})
    delivery_scenarios = android_delivery.get("scenarios", {})
    for scenario in ANDROID_DELIVERY_SCENARIOS:
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
        ("lost_messages", "누락 메시지"),
        ("server_receipt_duplicates", "서버 receipt 중복"),
    ):
        if android_delivery.get(metric_name) != 0:
            failures.append(f"Android {label}가 0건이 아닙니다.")
    display_duplicates = android_delivery.get("crash_boundary_display_duplicates")
    if not isinstance(display_duplicates, int) or not 0 <= display_duplicates <= 1:
        failures.append("Android crash 경계 표시 중복이 0~1건이 아니거나 미측정입니다.")
    failures.extend(
        evidence_failures(
            run_root, android_delivery.get("evidence"), "Android 전달 종합"
        )
    )

    android_security = record.get("android_security", {})
    for check_name in (
        "keystore_token_ciphertext_verified",
        "outbox_ciphertext_verified",
        "encrypted_photo_verified",
        "wrong_key_decryption_failed",
        "secure_cache_cleared_after_exit",
        "flag_secure_verified",
        "external_share_absent",
        "backup_disabled",
    ):
        if android_security.get(check_name) is not True:
            failures.append(f"Android 보안 실기 {check_name}가 확인되지 않았습니다.")
    failures.extend(
        evidence_failures(
            run_root, android_security.get("evidence"), "Android 보안 실기"
        )
    )

    device_lifecycle = record.get("android_device_lifecycle", {})
    if device_lifecycle.get("lost_or_inactive_device_reconnect_blocked") is not True:
        failures.append("분실·비활성 Android 단말의 재접속 차단이 확인되지 않았습니다.")
    if device_lifecycle.get("replacement_history_preserved") is not True:
        failures.append("Android 단말 교체 이력 보존이 확인되지 않았습니다.")
    failures.extend(
        evidence_failures(
            run_root,
            device_lifecycle.get("evidence"),
            "Android 단말 수명주기",
        )
    )

    ux_items = record.get("ux_development_items", {})
    actionable = ux_items.get("actionable_findings")
    converted = ux_items.get("converted_items")
    unconverted = ux_items.get("unconverted_actionable_findings")
    if (
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
        (priority_counts, "P0~P3 우선순위"),
        (classification_counts, "제품/설정/배치·교육 분류"),
    ):
        if (
            not all(isinstance(value, int) and value >= 0 for value in counts)
            or not isinstance(converted, int)
            or sum(counts) != converted
        ):
            failures.append(f"UX 개발 항목의 {label} 합계가 변환 건수와 다릅니다.")
    failures.extend(
        evidence_failures(run_root, ux_items.get("evidence"), "UX 개발 항목 변환")
    )

    rollback = record.get("rollback", {})
    for target in ("server", "wpf", "android"):
        item = rollback.get(target, {})
        if item.get("result") != "PASS" or item.get("normal_work_resumed") is not True:
            failures.append(f"{target} rollback과 정상 업무 재개가 PASS가 아닙니다.")
        if not nonempty(item.get("previous_approved_version")):
            failures.append(f"{target}의 이전 승인 버전이 없습니다.")
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
        "schema_version": 2,
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
