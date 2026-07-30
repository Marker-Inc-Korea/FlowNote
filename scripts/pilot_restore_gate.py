"""Validate restore fault evidence and shared restore-set bindings."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any, Callable, Optional


ReadRows = Callable[[Path, str, str], tuple[list[dict[str, str]], list[str]]]
ParseBoolean = Callable[[Any], Optional[bool]]
CheckEvidence = Callable[[Path, Any, str], list[str]]


def fault_injection_failures(
    run_root: Path,
    cases: tuple[str, ...],
    read_rows: ReadRows,
    parse_boolean: ParseBoolean,
    check_evidence: CheckEvidence,
) -> list[str]:
    rows, failures = read_rows(
        run_root,
        "scenario-results/restore-fault-injections.csv",
        "복구 장애 주입",
    )
    grouped = {case: [] for case in cases}
    used_evidence: dict[str, str] = {}
    used_fault_run_ids: set[str] = set()
    used_reconciliation_run_ids: set[str] = set()
    shared_backup_set_id: str | None = None
    shared_restore_approval_id: str | None = None
    for row in rows:
        injection_id = (row.get("injection_id") or "").strip()
        if injection_id in grouped:
            grouped[injection_id].append(row)
    for case, matching in grouped.items():
        if len(matching) != 1:
            failures.append(f"복구 장애 주입 {case} 행은 정확히 1개여야 합니다.")
            continue
        row = matching[0]
        fault_run_id = (row.get("fault_run_id") or "").strip()
        if (
            not re.fullmatch(
                r"PILOT-\d{8}-\d{4}-[A-Z0-9_-]+-\d{3}",
                fault_run_id,
            )
            or fault_run_id == run_root.name
        ):
            failures.append(
                f"복구 장애 주입 {case}의 fault_run_id는 정상 복구와 다른 새 PILOT run ID여야 합니다."
            )
        elif fault_run_id in used_fault_run_ids:
            failures.append(
                f"복구 장애 주입 {case}의 fault_run_id가 다른 장애와 중복됩니다."
            )
        else:
            used_fault_run_ids.add(fault_run_id)
        reconciliation_run_id = (row.get("reconciliation_run_id") or "").strip()
        if not reconciliation_run_id:
            failures.append(f"복구 장애 주입 {case}의 reconciliation_run_id가 없습니다.")
        elif reconciliation_run_id in used_reconciliation_run_ids:
            failures.append(
                f"복구 장애 주입 {case}의 reconciliation_run_id가 다른 장애와 중복됩니다."
            )
        else:
            used_reconciliation_run_ids.add(reconciliation_run_id)
        if not (row.get("responsible_owner") or "").strip():
            failures.append(f"복구 장애 주입 {case}의 담당자가 없습니다.")
        backup_set_id = (row.get("backup_set_id") or "").strip()
        restore_approval_id = (row.get("restore_approval_id") or "").strip()
        if not backup_set_id:
            failures.append(f"복구 장애 주입 {case}의 backup_set_id가 없습니다.")
        elif shared_backup_set_id is None:
            shared_backup_set_id = backup_set_id
        elif shared_backup_set_id != backup_set_id:
            failures.append("네 복구 장애의 backup_set_id가 서로 다릅니다.")
        if not restore_approval_id:
            failures.append(f"복구 장애 주입 {case}의 restore_approval_id가 없습니다.")
        elif shared_restore_approval_id is None:
            shared_restore_approval_id = restore_approval_id
        elif shared_restore_approval_id != restore_approval_id:
            failures.append("네 복구 장애의 restore_approval_id가 서로 다릅니다.")
        if (row.get("target") or "").strip() != "both":
            failures.append(
                f"복구 장애 주입 {case}는 server와 wpf를 함께 검증해야 합니다."
            )
        for field in (
            "automatic_send_blocked",
            "polling_blocked",
            "reconciliation_required",
            "admin_approved_rebind",
            "normal_operation_resumed",
        ):
            if parse_boolean(row.get(field)) is not True:
                failures.append(f"복구 장애 주입 {case}의 {field}가 TRUE가 아닙니다.")
        if (row.get("result") or "").strip() != "PASS":
            failures.append(f"복구 장애 주입 {case}의 원시 판정이 PASS가 아닙니다.")
        for field, label in (
            ("automatic_overwrite_count", "승인 전 자동 덮어쓰기"),
            ("data_loss_count", "데이터 손실"),
            ("duplicate_mutation_count", "중복 mutation"),
            ("permission_bypass_count", "권한 우회"),
        ):
            try:
                count = int((row.get(field) or "").strip())
            except ValueError:
                count = -1
            if count != 0:
                failures.append(f"복구 장애 주입 {case}의 {label} 건수가 0이 아닙니다.")
        fault_evidence: list[str] = []
        for field, label in (
            ("screen_evidence", "차단·재결합 화면"),
            ("wpf_log_evidence", "WPF 차단·재개 로그"),
            ("server_audit_evidence", "서버 reconciliation 감사"),
        ):
            value = (row.get(field) or "").strip()
            fault_evidence.append(value)
            expected_prefix = f"fault-runs/{fault_run_id}/"
            if fault_run_id and not value.startswith(expected_prefix):
                failures.append(
                    f"복구 장애 주입 {case}의 {label}는 {expected_prefix} 아래에 있어야 합니다."
                )
            if value and value in used_evidence:
                failures.append(
                    f"복구 장애 주입 {case}의 {label}가 "
                    f"{used_evidence[value]} 장애 증거를 재사용합니다."
                )
            elif value:
                used_evidence[value] = case
            failures.extend(
                check_evidence(
                    run_root,
                    [value],
                    f"복구 장애 주입 {case} {label}",
                )
            )
        if len(set(fault_evidence)) != len(fault_evidence):
            failures.append(
                f"복구 장애 주입 {case}의 화면·WPF 로그·서버 감사는 "
                "서로 다른 증거 파일이어야 합니다."
            )
    return failures


def restore_set_binding_failures(
    run_root: Path, server_evidence: Any, wpf_evidence: Any
) -> list[str]:
    def reports(evidence: Any, target: str) -> list[dict[str, Any]]:
        if not isinstance(evidence, list):
            return []
        loaded: list[dict[str, Any]] = []
        for value in evidence:
            if not isinstance(value, str) or not value.endswith("-comparison.json"):
                continue
            path = Path(value)
            if path.is_absolute() or ".." in path.parts:
                continue
            try:
                report = json.loads((run_root / path).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if (
                report.get("run_id") == run_root.name
                and report.get("target") == target
                and report.get("result") == "PASS"
                and report.get("responsibility_table_fingerprints_equal") is True
                and report.get("responsibility_check_violation_counts")
                == {"before": 0, "after": 0}
                and report.get("referenced_file_check_mismatch_counts")
                == {
                    "before": {
                        "missing_count": 0,
                        "size_mismatch_count": 0,
                        "sha256_mismatch_count": 0,
                    },
                    "after": {
                        "missing_count": 0,
                        "size_mismatch_count": 0,
                        "sha256_mismatch_count": 0,
                    },
                }
            ):
                loaded.append(report)
        return loaded

    server_reports = reports(server_evidence, "server")
    wpf_reports = reports(wpf_evidence, "wpf")
    for server in server_reports:
        for wpf in wpf_reports:
            if (
                _nonempty(server.get("backup_set_id"))
                and server.get("backup_set_id") == wpf.get("backup_set_id")
                and _nonempty(server.get("restore_approval_id"))
                and server.get("restore_approval_id")
                == wpf.get("restore_approval_id")
            ):
                return []
    return [
        "server와 wpf 복구 comparison의 backup_set_id와 "
        "restore_approval_id가 같은 통합 복구 세트가 아닙니다."
    ]


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())
