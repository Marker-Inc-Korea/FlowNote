"""Windows/server rehearsal evidence templates and strict raw-result validation."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any, Callable


PACKAGE_ROLES = (
    "server_candidate",
    "wpf_msi_candidate",
    "wpf_exe_candidate",
    "server_previous",
    "wpf_msi_previous",
)
INSTALL_CASES = (
    "server_clean_install",
    "wpf_clean_install",
    "wpf_upgrade",
    "wpf_remove",
    "wpf_reinstall",
)
RUNTIME_CASES = (
    "dotnet_desktop_present",
    "dotnet_desktop_absent",
    "webview2_present",
    "webview2_absent",
)
FAULT_CASES = (
    "server_task_scheduler",
    "server_reboot_autostart",
    "certificate_renewal",
    "certificate_revoked",
    "certificate_expired",
    "certificate_untrusted",
    "firewall_port_block",
    "dns_change",
    "fixed_address_change",
    "time_sync_drift",
    "transfer_during_server_reboot",
    "interrupted_upgrade",
    "invalid_package_signature",
)
RECOVERY_TARGETS = ("server_restore", "wpf_restore", "rollback")
ROLLBACK_WORKFLOWS = (
    "login",
    "document_view",
    "field_comment",
    "synchronization",
    "notification",
    "audit_log",
)
PROMOTION_TARGETS = ("server", "wpf")
SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


def authorization_defaults() -> dict[str, Any]:
    return {
        "rollback_decision_authority": "",
        "emergency_contact_flow": "",
        "recovery_objectives": {
            target: {
                "rto_seconds": None,
                "rpo_seconds": None,
            }
            for target in RECOVERY_TARGETS
        },
        "previous_approved_packages": {
            target: {
                "version": "",
                "sha256": "",
                "signer_sha256": "",
            }
            for target in PROMOTION_TARGETS
        },
    }


def templates(run_id: str) -> dict[str, str]:
    package_rows = "".join(
        ",".join(
            (
                run_id,
                role,
                *("" for _ in range(12)),
                "NOT_RUN",
                "",
            )
        )
        + "\n"
        for role in PACKAGE_ROLES
    )
    install_rows = "".join(
        f"{run_id},{case},,,,,,NOT_RUN,\n" for case in INSTALL_CASES
    )
    runtime_rows = "".join(
        f"{run_id},{case},,,,,NOT_RUN,\n" for case in RUNTIME_CASES
    )
    fault_rows = "".join(
        f"{run_id},{case},,,,,,,,NOT_RUN,\n" for case in FAULT_CASES
    )
    recovery_rows = "".join(
        f"{run_id},{target},,,,,,NOT_RUN,\n" for target in RECOVERY_TARGETS
    )
    rollback_rows = "".join(
        f"{run_id},{workflow},,,NOT_RUN,\n" for workflow in ROLLBACK_WORKFLOWS
    )
    promotion_rows = "".join(
        f"{run_id},{target},,,,,,,,,NOT_RUN,\n" for target in PROMOTION_TARGETS
    )
    return {
        "packages/windows-server-packages.csv": (
            "pilot_run_id,artifact_role,artifact_name,version,sha256,"
            "approved_sha256,signer_sha256,approved_signer_sha256,"
            "signature_status,chain_status,timestamp_status,secret_count,"
            "sqlite_count,customer_file_count,result,evidence\n"
            + package_rows
        ),
        "install/windows-lifecycle.csv": (
            "pilot_run_id,case_id,machine_id,package_version,exit_code,"
            "data_preserved,observed_version,result,evidence\n"
            + install_rows
        ),
        "install/windows-runtime-matrix.csv": (
            "pilot_run_id,case_id,machine_id,dependency_mode,detected_version,"
            "expected_behavior_observed,result,evidence\n"
            + runtime_rows
        ),
        "scenario-results/windows-server-fault-injections.csv": (
            "pilot_run_id,case_id,machine_id,failure_detected,"
            "unauthorized_client_blocked,approved_client_reconnected,"
            "normal_work_resumed,"
            "resumed_at,change_approval_id,result,evidence\n"
            + fault_rows
        ),
        "scenario-results/recovery-objectives.csv": (
            "pilot_run_id,target,approved_rto_seconds,measured_rto_seconds,"
            "approved_rpo_seconds,measured_rpo_seconds,resumed_at,result,evidence\n"
            + recovery_rows
        ),
        "scenario-results/rollback-workflows.csv": (
            "pilot_run_id,workflow_id,audit_event_id,checked_at,result,evidence\n"
            + rollback_rows
        ),
        "approvals/package-promotion-and-rollback.csv": (
            "pilot_run_id,target,candidate_version,previous_version,"
            "previous_sha256,previous_signer_sha256,coordinated_backup_set_id,"
            "promotion_approval_id,rollback_decision_authority,"
            "emergency_contact_flow_id,result,evidence\n"
            + promotion_rows
        ),
    }


def write_templates(run_root: Path, run_id: str) -> None:
    for relative_path, content in templates(run_id).items():
        path = run_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(content, encoding="utf-8")


def _read_rows(
    run_root: Path, relative_path: str, label: str
) -> tuple[list[dict[str, str]], list[str]]:
    path = run_root / relative_path
    if not path.is_file():
        return [], [f"{label}: 원시 결과 파일이 없습니다: {relative_path}"]
    try:
        with path.open(newline="", encoding="utf-8-sig") as stream:
            return list(csv.DictReader(stream)), []
    except (OSError, csv.Error) as error:
        return [], [f"{label}: CSV를 읽을 수 없습니다: {error}"]


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _boolean(value: Any) -> bool | None:
    normalized = str(value or "").strip().casefold()
    if normalized in ("true", "1", "yes", "y"):
        return True
    if normalized in ("false", "0", "no", "n"):
        return False
    return None


def _number(value: Any) -> float | None:
    try:
        result = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return result if result >= 0 else None


def _required_rows(
    rows: list[dict[str, str]],
    id_column: str,
    required_ids: tuple[str, ...],
    label: str,
) -> tuple[dict[str, dict[str, str]], list[str]]:
    failures: list[str] = []
    result: dict[str, dict[str, str]] = {}
    for required_id in required_ids:
        matching = [
            row
            for row in rows
            if (row.get(id_column) or "").strip() == required_id
        ]
        if len(matching) != 1:
            failures.append(f"{label} {required_id} 행은 정확히 1개여야 합니다.")
        elif matching:
            result[required_id] = matching[0]
    return result, failures


def _base_row_failures(
    run_root: Path,
    run_id: str,
    row: dict[str, str],
    label: str,
    evidence_failures: Callable[[Path, Any, str], list[str]],
) -> list[str]:
    failures: list[str] = []
    if (row.get("pilot_run_id") or "").strip() != run_id:
        failures.append(f"{label}의 run_id가 현재 실행과 다릅니다.")
    if (row.get("result") or "").strip() != "PASS":
        failures.append(f"{label}의 원시 판정이 PASS가 아닙니다.")
    evidence = (row.get("evidence") or "").strip()
    failures.extend(evidence_failures(run_root, [evidence], label))
    return failures


def _package_failures(
    run_root: Path,
    run_id: str,
    authorization: dict[str, Any],
    evidence_failures: Callable[[Path, Any, str], list[str]],
) -> list[str]:
    rows, failures = _read_rows(
        run_root, "packages/windows-server-packages.csv", "Windows/서버 패키지"
    )
    required, row_failures = _required_rows(
        rows, "artifact_role", PACKAGE_ROLES, "Windows/서버 패키지"
    )
    failures.extend(row_failures)
    previous = authorization.get("previous_approved_packages", {})
    previous_mapping = {
        "server_previous": previous.get("server", {}),
        "wpf_msi_previous": previous.get("wpf", {}),
    }
    for role, row in required.items():
        label = f"Windows/서버 패키지 {role}"
        failures.extend(
            _base_row_failures(run_root, run_id, row, label, evidence_failures)
        )
        for field in ("artifact_name", "version"):
            if not _nonempty(row.get(field)):
                failures.append(f"{label}의 {field} 값이 없습니다.")
        for field in (
            "sha256",
            "approved_sha256",
            "signer_sha256",
            "approved_signer_sha256",
        ):
            if not SHA256_PATTERN.fullmatch((row.get(field) or "").strip()):
                failures.append(f"{label}의 {field}가 SHA-256 형식이 아닙니다.")
        if (row.get("sha256") or "").casefold() != (
            row.get("approved_sha256") or ""
        ).casefold():
            failures.append(f"{label}의 패키지 hash가 승인값과 다릅니다.")
        if (row.get("signer_sha256") or "").casefold() != (
            row.get("approved_signer_sha256") or ""
        ).casefold():
            failures.append(f"{label}의 signer가 승인값과 다릅니다.")
        for field in ("signature_status", "chain_status", "timestamp_status"):
            if (row.get(field) or "").strip() != "PASS":
                failures.append(f"{label}의 {field}가 PASS가 아닙니다.")
        for field in ("secret_count", "sqlite_count", "customer_file_count"):
            try:
                count = int((row.get(field) or "").strip())
            except ValueError:
                count = -1
            if count != 0:
                failures.append(f"{label}의 {field}가 0이 아닙니다.")
        baseline = previous_mapping.get(role)
        if baseline:
            for field in ("version", "sha256", "signer_sha256"):
                if (row.get(field) or "").strip().casefold() != str(
                    baseline.get(field) or ""
                ).strip().casefold():
                    failures.append(
                        f"{label}의 {field}가 사전 승인 rollback 기준선과 다릅니다."
                    )
    return failures


def _simple_case_failures(
    run_root: Path,
    run_id: str,
    relative_path: str,
    label: str,
    id_column: str,
    required_ids: tuple[str, ...],
    required_fields: tuple[str, ...],
    true_fields: tuple[str, ...],
    evidence_failures: Callable[[Path, Any, str], list[str]],
) -> list[str]:
    rows, failures = _read_rows(run_root, relative_path, label)
    required, row_failures = _required_rows(rows, id_column, required_ids, label)
    failures.extend(row_failures)
    for case_id, row in required.items():
        row_label = f"{label} {case_id}"
        failures.extend(
            _base_row_failures(run_root, run_id, row, row_label, evidence_failures)
        )
        for field in required_fields:
            if not _nonempty(row.get(field)):
                failures.append(f"{row_label}의 {field} 값이 없습니다.")
        for field in true_fields:
            if _boolean(row.get(field)) is not True:
                failures.append(f"{row_label}의 {field}가 TRUE가 아닙니다.")
    return failures


def _install_failures(
    run_root: Path,
    run_id: str,
    evidence_failures: Callable[[Path, Any, str], list[str]],
) -> list[str]:
    relative_path = "install/windows-lifecycle.csv"
    rows, failures = _read_rows(run_root, relative_path, "설치 수명주기")
    required, row_failures = _required_rows(
        rows, "case_id", INSTALL_CASES, "설치 수명주기"
    )
    failures.extend(row_failures)
    for case_id, row in required.items():
        label = f"설치 수명주기 {case_id}"
        failures.extend(
            _base_row_failures(run_root, run_id, row, label, evidence_failures)
        )
        for field in ("machine_id", "package_version", "observed_version"):
            if not _nonempty(row.get(field)):
                failures.append(f"{label}의 {field} 값이 없습니다.")
        try:
            exit_code = int((row.get("exit_code") or "").strip())
        except ValueError:
            exit_code = -1
        if exit_code != 0:
            failures.append(f"{label}의 설치 종료 코드가 0이 아닙니다.")
        if _boolean(row.get("data_preserved")) is not True:
            failures.append(f"{label}의 data_preserved가 TRUE가 아닙니다.")
        observed = (row.get("observed_version") or "").strip()
        package_version = (row.get("package_version") or "").strip()
        if case_id == "wpf_remove":
            if observed != "NOT_INSTALLED":
                failures.append(f"{label} 후 패키지가 제거되지 않았습니다.")
        elif observed != package_version:
            failures.append(f"{label}의 설치 버전이 패키지 버전과 다릅니다.")
    return failures


def _runtime_failures(
    run_root: Path,
    run_id: str,
    evidence_failures: Callable[[Path, Any, str], list[str]],
) -> list[str]:
    failures = _simple_case_failures(
        run_root,
        run_id,
        "install/windows-runtime-matrix.csv",
        "Windows 의존 runtime matrix",
        "case_id",
        RUNTIME_CASES,
        ("machine_id", "dependency_mode", "detected_version"),
        ("expected_behavior_observed",),
        evidence_failures,
    )
    rows, _ = _read_rows(
        run_root, "install/windows-runtime-matrix.csv", "Windows 의존 runtime matrix"
    )
    required, _ = _required_rows(
        rows, "case_id", RUNTIME_CASES, "Windows 의존 runtime matrix"
    )
    for case_id, row in required.items():
        version = (row.get("detected_version") or "").strip()
        if case_id.endswith("_absent") and version != "NOT_INSTALLED":
            failures.append(
                f"Windows 의존 runtime matrix {case_id}는 NOT_INSTALLED여야 합니다."
            )
        if case_id.endswith("_present") and version == "NOT_INSTALLED":
            failures.append(
                f"Windows 의존 runtime matrix {case_id}의 설치 버전이 없습니다."
            )
    return failures


def _recovery_failures(
    run_root: Path,
    run_id: str,
    authorization: dict[str, Any],
    evidence_failures: Callable[[Path, Any, str], list[str]],
) -> list[str]:
    rows, failures = _read_rows(
        run_root, "scenario-results/recovery-objectives.csv", "복구 목표 실측"
    )
    required, row_failures = _required_rows(
        rows, "target", RECOVERY_TARGETS, "복구 목표 실측"
    )
    failures.extend(row_failures)
    objectives = authorization.get("recovery_objectives", {})
    for target, row in required.items():
        label = f"복구 목표 실측 {target}"
        failures.extend(
            _base_row_failures(run_root, run_id, row, label, evidence_failures)
        )
        if not _nonempty(row.get("resumed_at")):
            failures.append(f"{label}의 업무 재개 시각이 없습니다.")
        objective = objectives.get(target, {})
        for metric in ("rto", "rpo"):
            approved = _number(row.get(f"approved_{metric}_seconds"))
            measured = _number(row.get(f"measured_{metric}_seconds"))
            summary = objective.get(f"{metric}_seconds")
            if approved is None or approved <= 0:
                failures.append(f"{label}의 승인 {metric.upper()}가 없습니다.")
            elif not isinstance(summary, (int, float)) or approved != float(summary):
                failures.append(
                    f"{label}의 승인 {metric.upper()}가 사전 승인값과 다릅니다."
                )
            if measured is None or approved is None or measured > approved:
                failures.append(
                    f"{label}의 실측 {metric.upper()}가 "
                    "승인 목표를 초과하거나 없습니다."
                )
    return failures


def _promotion_failures(
    run_root: Path,
    run_id: str,
    authorization: dict[str, Any],
    evidence_failures: Callable[[Path, Any, str], list[str]],
) -> list[str]:
    rows, failures = _read_rows(
        run_root,
        "approvals/package-promotion-and-rollback.csv",
        "패키지 승격·rollback 승인",
    )
    required, row_failures = _required_rows(
        rows, "target", PROMOTION_TARGETS, "패키지 승격·rollback 승인"
    )
    failures.extend(row_failures)
    package_rows, package_read_failures = _read_rows(
        run_root, "packages/windows-server-packages.csv", "Windows/서버 패키지"
    )
    failures.extend(package_read_failures)
    package_by_role = {
        (row.get("artifact_role") or "").strip(): row for row in package_rows
    }
    candidate_roles = {
        "server": "server_candidate",
        "wpf": "wpf_msi_candidate",
    }
    backup_ids: set[str] = set()
    previous = authorization.get("previous_approved_packages", {})
    authority = authorization.get("rollback_decision_authority")
    emergency_flow = authorization.get("emergency_contact_flow")
    for target, row in required.items():
        label = f"패키지 승격·rollback 승인 {target}"
        failures.extend(
            _base_row_failures(run_root, run_id, row, label, evidence_failures)
        )
        for field in (
            "candidate_version",
            "coordinated_backup_set_id",
            "promotion_approval_id",
            "rollback_decision_authority",
            "emergency_contact_flow_id",
        ):
            if not _nonempty(row.get(field)):
                failures.append(f"{label}의 {field} 값이 없습니다.")
        package_version = (
            package_by_role.get(candidate_roles[target], {}).get("version") or ""
        ).strip()
        if (row.get("candidate_version") or "").strip() != package_version:
            failures.append(f"{label}의 후보 버전이 검증한 패키지와 다릅니다.")
        baseline = previous.get(target, {})
        for field in ("version", "sha256", "signer_sha256"):
            row_field = f"previous_{field}"
            if (row.get(row_field) or "").strip().casefold() != str(
                baseline.get(field) or ""
            ).strip().casefold():
                failures.append(f"{label}의 {row_field}가 사전 승인값과 다릅니다.")
        if (row.get("rollback_decision_authority") or "").strip() != authority:
            failures.append(
                f"{label}의 rollback 의사결정권자가 사전 승인과 다릅니다."
            )
        if (row.get("emergency_contact_flow_id") or "").strip() != emergency_flow:
            failures.append(f"{label}의 비상 연락 흐름이 사전 승인과 다릅니다.")
        backup_id = (row.get("coordinated_backup_set_id") or "").strip()
        if backup_id:
            backup_ids.add(backup_id.casefold())
    if len(backup_ids) != 1:
        failures.append(
            "서버와 WPF rollback은 같은 시점의 통합 백업 세트를 써야 합니다."
        )
    return failures


def authorization_failures(authorization: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for field, label in (
        ("rollback_decision_authority", "rollback 의사결정권자"),
        ("emergency_contact_flow", "비상 연락 흐름"),
    ):
        if not _nonempty(authorization.get(field)):
            failures.append(f"리허설 사전 승인의 {label}가 필요합니다.")
    objectives = authorization.get("recovery_objectives", {})
    for target in RECOVERY_TARGETS:
        objective = objectives.get(target, {})
        for metric in ("rto_seconds", "rpo_seconds"):
            value = objective.get(metric)
            if not isinstance(value, (int, float)) or value <= 0:
                failures.append(
                    f"리허설 사전 승인의 {target} {metric}가 0보다 커야 합니다."
                )
    previous = authorization.get("previous_approved_packages", {})
    versions = authorization.get("previous_approved_versions", {})
    for target in PROMOTION_TARGETS:
        baseline = previous.get(target, {})
        if not _nonempty(baseline.get("version")):
            failures.append(f"{target} 이전 승인 패키지 버전이 필요합니다.")
        elif baseline.get("version") != versions.get(target):
            failures.append(
                f"{target} 이전 승인 패키지 버전이 이전 승인 버전과 다릅니다."
            )
        for field in ("sha256", "signer_sha256"):
            if not SHA256_PATTERN.fullmatch(str(baseline.get(field) or "").strip()):
                failures.append(
                    f"{target} 이전 승인 패키지 {field}가 SHA-256 형식이 아닙니다."
                )
    return failures


def _comparison_backup_failures(
    run_root: Path, record: dict[str, Any]
) -> list[str]:
    promotion_rows, _ = _read_rows(
        run_root,
        "approvals/package-promotion-and-rollback.csv",
        "패키지 승격·rollback 승인",
    )
    backup_ids = {
        (row.get("coordinated_backup_set_id") or "").strip().casefold()
        for row in promotion_rows
        if (row.get("coordinated_backup_set_id") or "").strip()
    }
    if len(backup_ids) != 1:
        return []
    approved_backup_id = next(iter(backup_ids))
    failures: list[str] = []
    gates = record.get("gates", {})
    for target in ("server", "wpf"):
        evidence = gates.get(f"{target}_restore_separate_pc", {}).get("evidence", [])
        reports = [
            run_root / value
            for value in evidence
            if isinstance(value, str) and value.endswith("-comparison.json")
        ]
        matching = False
        for path in reports:
            try:
                report = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if (
                report.get("result") == "PASS"
                and str(report.get("backup_set_id") or "").strip().casefold()
                == approved_backup_id
            ):
                matching = True
                break
        if not matching:
            failures.append(
                f"{target} 복구 comparison의 백업 세트가 "
                "승인된 통합 rollback 세트와 다릅니다."
            )
    return failures


def verification_failures(
    run_root: Path,
    run_id: str,
    record: dict[str, Any],
    evidence_failures: Callable[[Path, Any, str], list[str]],
    restore_comparison_failures: Callable[[Path, Any, str], list[str]],
) -> list[str]:
    authorization = record.get("authorization", {})
    failures = authorization_failures(authorization)
    failures.extend(
        _package_failures(run_root, run_id, authorization, evidence_failures)
    )
    failures.extend(_install_failures(run_root, run_id, evidence_failures))
    failures.extend(_runtime_failures(run_root, run_id, evidence_failures))
    failures.extend(
        _simple_case_failures(
            run_root,
            run_id,
            "scenario-results/windows-server-fault-injections.csv",
            "Windows/서버 장애 주입",
            "case_id",
            FAULT_CASES,
            ("machine_id", "resumed_at", "change_approval_id"),
            (
                "failure_detected",
                "unauthorized_client_blocked",
                "approved_client_reconnected",
                "normal_work_resumed",
            ),
            evidence_failures,
        )
    )
    failures.extend(_recovery_failures(run_root, run_id, authorization, evidence_failures))
    failures.extend(
        _simple_case_failures(
            run_root,
            run_id,
            "scenario-results/rollback-workflows.csv",
            "rollback 후 핵심 업무",
            "workflow_id",
            ROLLBACK_WORKFLOWS,
            ("audit_event_id", "checked_at"),
            (),
            evidence_failures,
        )
    )
    failures.extend(
        _promotion_failures(run_root, run_id, authorization, evidence_failures)
    )
    failures.extend(_comparison_backup_failures(run_root, record))
    gates = record.get("gates", {})
    for target in ("server", "wpf"):
        gate = f"{target}_restore_separate_pc"
        failures.extend(
            restore_comparison_failures(
                run_root, gates.get(gate, {}).get("evidence"), target
            )
        )
    return failures
