from __future__ import annotations

import argparse
import contextlib
import csv
import importlib.util
import io
import json
import unittest
import uuid
from pathlib import Path

from scripts.manage_pilot_run_ux_test_mixin import ManagePilotRunUxTestMixin


SCRIPT_PATH = Path(__file__).with_name("manage-pilot-run.py")
SPEC = importlib.util.spec_from_file_location("manage_pilot_run", SCRIPT_PATH)
assert SPEC and SPEC.loader
manage_pilot_run = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manage_pilot_run)


class WindowsServerRehearsalVerificationTests(
    ManagePilotRunUxTestMixin, unittest.TestCase
):
    def setUp(self) -> None:
        self.evidence_root = (
            SCRIPT_PATH.parent.parent
            / "data"
            / "local"
            / "pilot-tool-tests"
            / f"manage-pilot-run-{uuid.uuid4().hex}"
        )
        self.evidence_root.mkdir(parents=True)
        self.run_id = "PILOT-20260722-1300-LOCALCHECK-001"
        self.run_root = self.evidence_root / self.run_id
        self.run_root.mkdir()
        (self.run_root / "proof.txt").write_text("test evidence\n", encoding="utf-8")

    def complete_record(self) -> dict:
        record = manage_pilot_run.empty_record(self.run_id, "windows_server_rehearsal")
        record["status"] = "PASS"
        record["environment"].update(
            {
                "customer_like_network": True,
                "clean_server_count": 1,
                "clean_windows_client_count": 1,
            }
        )
        for index, assignment in enumerate(record["responsibilities"].values()):
            assignment.update(
                {
                    "owner": f"owner-{index}",
                    "approver": f"approver-{index}",
                    "test_scope": "approved scope",
                    "stop_criteria": "stop on any critical event",
                    "evidence_repository": "controlled-store-01",
                    "approval_evidence": ["proof.txt"],
                }
            )
        record["authorization"].update(
            {
                "decision": "PASS",
                "approved_at": "2026-07-22T13:00:00+09:00",
                "run_scope": "Windows and server rehearsal",
                "stop_criteria": [
                    "data loss",
                    "permission bypass",
                    "unauthorized disclosure",
                    "database integrity failure",
                    "rollback failure",
                ],
                "evidence_repository": "controlled-store-01",
                "retention_until": "2027-07-22",
                "equipment": {
                    "server_ids": ["SRV-01"],
                    "windows_client_ids": ["WIN-01"],
                    "android_device_ids": [],
                },
                "previous_approved_versions": {
                    "server": "server-approved-1",
                    "wpf": "wpf-approved-1",
                    "android": "",
                },
                "rollback_decision_authority": "ROLE-ROLLBACK-01",
                "emergency_contact_flow": "FLOW-EMERGENCY-01",
                "recovery_objectives": {
                    target: {"rto_seconds": 300, "rpo_seconds": 60}
                    for target in manage_pilot_run.windows_server_evidence.RECOVERY_TARGETS
                },
                "previous_approved_packages": {
                    target: {
                        "version": f"{target}-approved-1",
                        "sha256": "a" * 64,
                        "signer_sha256": "b" * 64,
                    }
                    for target in ("server", "wpf")
                },
                "evidence": ["proof.txt"],
            }
        )
        for gate in manage_pilot_run.WINDOWS_SERVER_REHEARSAL_GATES:
            record["gates"][gate] = {"result": "PASS", "evidence": ["proof.txt"]}
        for metric in manage_pilot_run.WINDOWS_SERVER_ZERO_TOLERANCE_METRICS:
            record["zero_tolerance"][metric] = 0
        for target in ("server", "wpf"):
            record["rollback"][target].update(
                {
                    "result": "PASS",
                    "previous_approved_version": f"{target}-approved-1",
                    "normal_work_resumed": True,
                    "evidence": ["proof.txt"],
                }
            )
        for approval in record["final_approvals"].values():
            approval.update(
                {
                    "decision": "PASS",
                    "signer": "independent-signer",
                    "signed_at": "2026-07-22T18:00:00+09:00",
                    "evidence": ["proof.txt"],
                }
            )
        self.write_windows_server_raw_evidence(record)
        return record

    def write_csv(self, relative_path: str, fieldnames: list[str], rows: list[dict]) -> None:
        path = self.run_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def write_restore_comparison(self, target: str) -> str:
        restore_root = self.run_root / "backup-restore"
        restore_root.mkdir(parents=True, exist_ok=True)
        manifests = {}
        for phase, machine_id in (("before", "SOURCE-01"), ("after", "RESTORE-02")):
            path = restore_root / f"{target}-{phase}.json"
            path.write_text(
                json.dumps(
                    {
                        "run_id": self.run_id,
                        "target": target,
                        "phase": phase,
                        "machine_id": machine_id,
                        "backup_set_id": "BACKUP-001",
                        "restore_approval_id": "APPROVAL-001",
                    }
                ),
                encoding="utf-8",
            )
            manifests[phase] = path
        relative = f"backup-restore/{target}-comparison.json"
        (self.run_root / relative).write_text(
            json.dumps(
                {
                    "run_id": self.run_id,
                    "target": target,
                    "result": "PASS",
                    "before_manifest": f"backup-restore/{target}-before.json",
                    "after_manifest": f"backup-restore/{target}-after.json",
                    "before_manifest_sha256": manage_pilot_run.sha256(
                        manifests["before"]
                    ),
                    "after_manifest_sha256": manage_pilot_run.sha256(
                        manifests["after"]
                    ),
                    "source_machine_id": "SOURCE-01",
                    "restore_machine_id": "RESTORE-02",
                    "backup_set_id": "BACKUP-001",
                    "restore_approval_id": "APPROVAL-001",
                    "table_counts_equal": True,
                    "table_count_mismatch_count": 0,
                    "file_manifest_equal": True,
                    "file_mismatch_counts": {
                        "missing": 0,
                        "extra": 0,
                        "size": 0,
                        "sha256": 0,
                    },
                    "database_checks": {
                        "before_quick_check_ok": True,
                        "before_integrity_check_ok": True,
                        "before_foreign_key_violation_count": 0,
                        "after_quick_check_ok": True,
                        "after_integrity_check_ok": True,
                        "after_foreign_key_violation_count": 0,
                        "before_capture_stable": True,
                        "before_checkpoint_clean": True,
                        "after_capture_stable": True,
                        "after_checkpoint_clean": True,
                    },
                    "file_capture_checks": {
                        "before_capture_stable": True,
                        "after_capture_stable": True,
                    },
                }
            ),
            encoding="utf-8",
        )
        return relative

    def write_windows_server_raw_evidence(self, record: dict) -> None:
        windows = manage_pilot_run.windows_server_evidence
        package_rows = []
        for role in windows.PACKAGE_ROLES:
            previous_target = (
                "server"
                if role == "server_previous"
                else "wpf" if role == "wpf_msi_previous" else None
            )
            baseline = (
                record["authorization"]["previous_approved_packages"][previous_target]
                if previous_target
                else {
                    "version": "candidate-2",
                    "sha256": "c" * 64,
                    "signer_sha256": "d" * 64,
                }
            )
            package_rows.append(
                {
                    "pilot_run_id": self.run_id,
                    "artifact_role": role,
                    "artifact_name": f"{role}.bin",
                    "version": baseline["version"],
                    "sha256": baseline["sha256"],
                    "approved_sha256": baseline["sha256"],
                    "signer_sha256": baseline["signer_sha256"],
                    "approved_signer_sha256": baseline["signer_sha256"],
                    "signature_status": "PASS",
                    "chain_status": "PASS",
                    "timestamp_status": "PASS",
                    "secret_count": 0,
                    "sqlite_count": 0,
                    "customer_file_count": 0,
                    "result": "PASS",
                    "evidence": "proof.txt",
                }
            )
        self.write_csv(
            "packages/windows-server-packages.csv",
            list(package_rows[0]),
            package_rows,
        )
        install_rows = [
            {
                "pilot_run_id": self.run_id,
                "case_id": case,
                "machine_id": "WIN-01",
                "package_version": "candidate-2",
                "exit_code": "0",
                "data_preserved": "TRUE",
                "observed_version": (
                    "NOT_INSTALLED" if case == "wpf_remove" else "candidate-2"
                ),
                "result": "PASS",
                "evidence": "proof.txt",
            }
            for case in windows.INSTALL_CASES
        ]
        self.write_csv("install/windows-lifecycle.csv", list(install_rows[0]), install_rows)
        runtime_rows = [
            {
                "pilot_run_id": self.run_id,
                "case_id": case,
                "machine_id": "WIN-01",
                "dependency_mode": (
                    "framework-dependent"
                    if case.startswith("framework_")
                    else "self-contained"
                    if case.startswith("self_contained_")
                    else ""
                ),
                "detected_version": "NOT_INSTALLED" if case.endswith("_absent") else "10.0",
                "expected_behavior_observed": "TRUE",
                "result": "PASS",
                "evidence": "proof.txt",
            }
            for case in windows.RUNTIME_CASES
        ]
        self.write_csv(
            "install/windows-runtime-matrix.csv", list(runtime_rows[0]), runtime_rows
        )
        startup_ux_rows = [
            {
                "pilot_run_id": self.run_id,
                "role": role,
                "attempt_no": str(attempt),
                "scenario_id": scenario,
                "participant_id": f"{role}-{attempt}",
                "missing_item_identified": "TRUE",
                "preserved_data_identified": "TRUE",
                "owner_identified": "TRUE",
                "next_action_selected": "TRUE",
                "selected_action": "승인된 안내에 따라 복구",
                "result": "PASS",
                "evidence": "proof.txt",
            }
            for role, attempt, scenario in (
                ("admin", 1, "dotnet_desktop_absent"),
                ("admin", 2, "certificate_validation_error"),
                ("general_user", 1, "webview2_absent"),
                ("general_user", 2, "invalid_server_address"),
            )
        ]
        self.write_csv(
            "install/windows-startup-ux.csv",
            list(startup_ux_rows[0]),
            startup_ux_rows,
        )
        fault_rows = [
            {
                "pilot_run_id": self.run_id,
                "case_id": case,
                "machine_id": "WIN-01",
                "failure_detected": "TRUE",
                "unauthorized_client_blocked": "TRUE",
                "approved_client_reconnected": "TRUE",
                "normal_work_resumed": "TRUE",
                "resumed_at": "2026-07-22T17:00:00+09:00",
                "change_approval_id": "CHANGE-001",
                "result": "PASS",
                "evidence": "proof.txt",
            }
            for case in windows.FAULT_CASES
        ]
        self.write_csv(
            "scenario-results/windows-server-fault-injections.csv",
            list(fault_rows[0]),
            fault_rows,
        )
        recovery_rows = [
            {
                "pilot_run_id": self.run_id,
                "target": target,
                "approved_rto_seconds": 300,
                "measured_rto_seconds": 240,
                "approved_rpo_seconds": 60,
                "measured_rpo_seconds": 30,
                "resumed_at": "2026-07-22T17:30:00+09:00",
                "result": "PASS",
                "evidence": "proof.txt",
            }
            for target in windows.RECOVERY_TARGETS
        ]
        self.write_csv(
            "scenario-results/recovery-objectives.csv",
            list(recovery_rows[0]),
            recovery_rows,
        )
        workflow_rows = [
            {
                "pilot_run_id": self.run_id,
                "workflow_id": workflow,
                "audit_event_id": f"AUDIT-{workflow}",
                "checked_at": "2026-07-22T17:40:00+09:00",
                "result": "PASS",
                "evidence": "proof.txt",
            }
            for workflow in windows.ROLLBACK_WORKFLOWS
        ]
        self.write_csv(
            "scenario-results/rollback-workflows.csv",
            list(workflow_rows[0]),
            workflow_rows,
        )
        promotion_rows = []
        for target in windows.PROMOTION_TARGETS:
            baseline = record["authorization"]["previous_approved_packages"][target]
            promotion_rows.append(
                {
                    "pilot_run_id": self.run_id,
                    "target": target,
                    "candidate_version": "candidate-2",
                    "previous_version": baseline["version"],
                    "previous_sha256": baseline["sha256"],
                    "previous_signer_sha256": baseline["signer_sha256"],
                    "coordinated_backup_set_id": "BACKUP-001",
                    "promotion_approval_id": "PROMOTION-001",
                    "rollback_decision_authority": "ROLE-ROLLBACK-01",
                    "emergency_contact_flow_id": "FLOW-EMERGENCY-01",
                    "result": "PASS",
                    "evidence": "proof.txt",
                }
            )
        self.write_csv(
            "approvals/package-promotion-and-rollback.csv",
            list(promotion_rows[0]),
            promotion_rows,
        )
        for target in ("server", "wpf"):
            comparison = self.write_restore_comparison(target)
            record["gates"][f"{target}_restore_separate_pc"]["evidence"] = [
                "proof.txt",
                comparison,
            ]

    def test_prepare_creates_schema_eight_windows_server_templates(self) -> None:
        run_id = "PILOT-20260722-1310-LOCALCHECK-002"
        with contextlib.redirect_stdout(io.StringIO()):
            result = manage_pilot_run.prepare(
                argparse.Namespace(
                    run_id=run_id,
                    evidence_root=self.evidence_root,
                    profile="windows_server_rehearsal",
                    allow_existing=False,
                )
            )

        record = json.loads(
            (self.evidence_root / run_id / "pilot-run.json").read_text(encoding="utf-8")
        )
        self.assertEqual(0, result)
        self.assertEqual(8, record["schema_version"])
        self.assertEqual("windows_server_rehearsal", record["profile"])
        self.assertTrue(
            (
                self.evidence_root
                / run_id
                / "approvals"
                / "responsibility-assignments.csv"
            ).is_file()
        )
        self.assertTrue(
            (
                self.evidence_root
                / run_id
                / "install"
                / "windows-startup-ux.csv"
            ).is_file()
        )
        self.assertTrue(
            (
                self.evidence_root / run_id / "approvals" / "rehearsal-authorization.md"
            ).is_file()
        )
        self.assertTrue(
            (
                self.evidence_root
                / run_id
                / "packages"
                / "windows-server-packages.csv"
            ).is_file()
        )

    def test_windows_server_profile_has_exact_required_fault_matrix(self) -> None:
        fault_cases = manage_pilot_run.windows_server_evidence.FAULT_CASES

        self.assertEqual(13, len(fault_cases))
        self.assertEqual(len(fault_cases), len(set(fault_cases)))
        self.assertIn("certificate_renewal", fault_cases)
        self.assertIn("certificate_validation_error", fault_cases)
        self.assertIn("firewall_port_block", fault_cases)
        self.assertIn("fixed_address_change", fault_cases)
        self.assertIn("time_sync_drift", fault_cases)
        self.assertIn("disk_space_low", fault_cases)
        self.assertIn("long_network_disconnect", fault_cases)

    def verify(self, record: dict) -> tuple[int, dict]:
        path = self.run_root / "pilot-run.json"
        path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        with (
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            result = manage_pilot_run.verify(
                argparse.Namespace(run_id=self.run_id, evidence_root=self.evidence_root)
            )
        report = json.loads(
            (self.run_root / "pilot-verification.json").read_text(encoding="utf-8")
        )
        return result, report

    def test_windows_server_profile_passes_without_android_execution(self) -> None:
        result, report = self.verify(self.complete_record())

        self.assertEqual(0, result)
        self.assertEqual("PASS", report["result"])

    def test_startup_ux_requires_owner_and_next_action_identification(self) -> None:
        record = self.complete_record()
        path = self.run_root / "install" / "windows-startup-ux.csv"
        with path.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        rows[0]["owner_identified"] = "FALSE"
        rows[0]["next_action_selected"] = "FALSE"
        self.write_csv("install/windows-startup-ux.csv", list(rows[0]), rows)

        result, report = self.verify(record)

        self.assertEqual(1, result)
        self.assertTrue(
            any("owner_identified가 TRUE가 아닙니다" in item for item in report["failures"])
        )
        self.assertTrue(
            any(
                "next_action_selected가 TRUE가 아닙니다" in item
                for item in report["failures"]
            )
        )

    def test_owner_cannot_self_approve(self) -> None:
        record = self.complete_record()
        record["responsibilities"]["server"]["approver"] = " OWNER-0 "

        result, report = self.verify(record)

        self.assertEqual(1, result)
        self.assertIn(
            "책임 영역 server는 담당자와 독립 승인자가 달라야 합니다.",
            report["failures"],
        )

    def test_windows_package_hash_mismatch_fails_closed(self) -> None:
        record = self.complete_record()
        path = self.run_root / "packages" / "windows-server-packages.csv"
        with path.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        rows[0]["sha256"] = "e" * 64
        self.write_csv(
            "packages/windows-server-packages.csv", list(rows[0]), rows
        )

        result, report = self.verify(record)

        self.assertEqual(1, result)
        self.assertTrue(
            any(
                "패키지 hash가 승인값과 다릅니다" in item
                for item in report["failures"]
            )
        )

    def test_recovery_measurement_over_approved_rto_fails_closed(self) -> None:
        record = self.complete_record()
        path = self.run_root / "scenario-results" / "recovery-objectives.csv"
        with path.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        rows[0]["measured_rto_seconds"] = "301"
        self.write_csv(
            "scenario-results/recovery-objectives.csv", list(rows[0]), rows
        )

        result, report = self.verify(record)

        self.assertEqual(1, result)
        self.assertTrue(
            any("실측 RTO가 승인 목표를 초과" in item for item in report["failures"])
        )

    def test_rollback_requires_all_six_workflows_in_same_run(self) -> None:
        record = self.complete_record()
        path = self.run_root / "scenario-results" / "rollback-workflows.csv"
        with path.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        rows = [row for row in rows if row["workflow_id"] != "audit_log"]
        rows[0]["pilot_run_id"] = "PILOT-20260722-1300-OTHER-001"
        self.write_csv(
            "scenario-results/rollback-workflows.csv", list(rows[0]), rows
        )

        result, report = self.verify(record)

        self.assertEqual(1, result)
        self.assertTrue(
            any("audit_log 행은 정확히 1개" in item for item in report["failures"])
        )
        self.assertTrue(
            any("run_id가 현재 실행과 다릅니다" in item for item in report["failures"])
        )

    def test_full_pilot_prepare_creates_android_raw_evidence_templates(self) -> None:
        run_id = "PILOT-20260722-1320-LOCALCHECK-003"
        with contextlib.redirect_stdout(io.StringIO()):
            manage_pilot_run.prepare(
                argparse.Namespace(
                    run_id=run_id,
                    evidence_root=self.evidence_root,
                    profile="full_pilot",
                    allow_existing=False,
                )
            )
        run_root = self.evidence_root / run_id

        self.assertTrue((run_root / "integrity" / "android-security.csv").is_file())
        self.assertTrue(
            (run_root / "scenario-results" / "android-delivery-integrity.csv").is_file()
        )
        self.assertTrue(
            (run_root / "scenario-results" / "android-device-lifecycle.csv").is_file()
        )
        self.assertTrue(
            (run_root / "packages" / "android-release-approval.csv").is_file()
        )
        self.assertTrue(
            (run_root / "scenario-results" / "restore-fault-injections.csv").is_file()
        )
        with (
            run_root / "scenario-results" / "role-ux-comparison.csv"
        ).open(newline="", encoding="utf-8") as stream:
            self.assertEqual(
                [
                    "comparison_id",
                    "development_cycle_id",
                    "attempt_no",
                    "role",
                    "participant_id",
                    "scenario_id",
                    "condition_id",
                    "network",
                    "gloves",
                    "one_hand",
                    "terminal_position",
                    "ui_phase",
                    "ui_build",
                    "success",
                    "elapsed_seconds",
                    "click_count",
                    "screen_transitions",
                    "help_request_count",
                    "source_preservation_understood",
                    "next_action_understood",
                    "source_loss_count",
                    "receipt_loss_count",
                    "duplicate_creation_count",
                    "critical_blocker",
                    "screen_capture_evidence",
                    "notes",
                ],
                next(csv.reader(stream)),
            )
        failures = manage_pilot_run.android_delivery_csv_failures(run_root)
        self.assertTrue(any("PASS가 아닙니다" in failure for failure in failures))

    def test_android_delivery_raw_results_require_all_eight_timed_passes(self) -> None:
        path = self.run_root / "scenario-results" / "android-delivery.csv"
        path.parent.mkdir(parents=True)
        fieldnames = [
            "scenario_id",
            "condition",
            "delivery_run_id",
            "message_id",
            "created_at_utc",
            "recovery_ready_at_utc",
            "displayed_at_utc",
            "receipt_at_utc",
            "page_seconds",
            "elapsed_seconds",
            "allowed_seconds",
            "result",
            "evidence",
        ]
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames)
            writer.writeheader()
            for scenario_id, condition in manage_pilot_run.ANDROID_DELIVERY_CASES:
                page_seconds = "2" if condition == "disconnect_5m" else "0"
                allowed = "32" if condition == "disconnect_5m" else "30"
                writer.writerow(
                    {
                        "scenario_id": scenario_id,
                        "condition": condition,
                        "delivery_run_id": "ANDROID-DELIVERY-test",
                        "page_seconds": page_seconds,
                        "elapsed_seconds": "1",
                        "allowed_seconds": allowed,
                        "result": "PASS",
                        "evidence": "proof.txt",
                    }
                )

        self.assertEqual(
            [], manage_pilot_run.android_delivery_csv_failures(self.run_root)
        )

        integrity_path = (
            self.run_root / "scenario-results" / "android-delivery-integrity.csv"
        )
        with integrity_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=[
                    "pilot_run_id",
                    "lost_messages",
                    "server_receipt_duplicates",
                    "crash_boundary_display_duplicates",
                    "result",
                    "evidence",
                ],
            )
            writer.writeheader()
            writer.writerow(
                {
                    "pilot_run_id": self.run_id,
                    "lost_messages": 0,
                    "server_receipt_duplicates": 0,
                    "crash_boundary_display_duplicates": 1,
                    "result": "PASS",
                    "evidence": "proof.txt",
                }
            )
        self.assertEqual(
            [],
            manage_pilot_run.android_delivery_integrity_csv_failures(
                self.run_root,
                self.run_id,
                {
                    "lost_messages": 0,
                    "server_receipt_duplicates": 0,
                    "crash_boundary_display_duplicates": 1,
                },
            ),
        )

    def test_restore_fault_injections_require_fail_closed_and_approved_rebind(
        self,
    ) -> None:
        path = self.run_root / "scenario-results" / "restore-fault-injections.csv"
        path.parent.mkdir(parents=True)
        fieldnames = [
            "injection_id",
            "target",
            "automatic_send_blocked",
            "polling_blocked",
            "reconciliation_required",
            "admin_approved_rebind",
            "normal_operation_resumed",
            "result",
            "screen_evidence",
            "wpf_log_evidence",
            "server_audit_evidence",
        ]
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames)
            writer.writeheader()
            for case in manage_pilot_run.RESTORE_FAULT_CASES:
                screen = f"{case}-screen.png"
                wpf_log = f"{case}-wpf.log"
                server_audit = f"{case}-server-audit.json"
                (self.run_root / screen).write_bytes(b"screen")
                (self.run_root / wpf_log).write_text(
                    "blocked\nresumed\n", encoding="utf-8"
                )
                (self.run_root / server_audit).write_text(
                    '{"status":"APPLIED"}\n', encoding="utf-8"
                )
                writer.writerow(
                    {
                        "injection_id": case,
                        "target": "both",
                        "automatic_send_blocked": "TRUE",
                        "polling_blocked": "TRUE",
                        "reconciliation_required": "TRUE",
                        "admin_approved_rebind": "TRUE",
                        "normal_operation_resumed": "TRUE",
                        "result": "PASS",
                        "screen_evidence": screen,
                        "wpf_log_evidence": wpf_log,
                        "server_audit_evidence": server_audit,
                    }
                )

        self.assertEqual(
            [], manage_pilot_run.restore_fault_injection_failures(self.run_root)
        )

    def test_server_and_wpf_restore_comparisons_must_share_both_ids(self) -> None:
        server = self.write_restore_comparison("server")
        wpf = self.write_restore_comparison("wpf")
        self.assertEqual(
            [],
            manage_pilot_run.restore_set_binding_failures(
                self.run_root, [server], [wpf]
            ),
        )

        wpf_path = self.run_root / wpf
        report = json.loads(wpf_path.read_text(encoding="utf-8"))
        report["restore_approval_id"] = "APPROVAL-OTHER"
        wpf_path.write_text(json.dumps(report), encoding="utf-8")
        self.assertTrue(
            manage_pilot_run.restore_set_binding_failures(
                self.run_root, [server], [wpf]
            )
        )

    def test_restore_comparison_is_bound_to_both_manifest_hashes(self) -> None:
        restore_root = self.run_root / "backup-restore"
        restore_root.mkdir(parents=True)
        manifests = {}
        for phase, machine_id in (("before", "SOURCE-01"), ("after", "RESTORE-02")):
            path = restore_root / f"server-{phase}.json"
            path.write_text(
                json.dumps(
                    {
                        "run_id": self.run_id,
                        "target": "server",
                        "phase": phase,
                        "machine_id": machine_id,
                        "backup_set_id": "BACKUP-001",
                        "restore_approval_id": "APPROVAL-001",
                    }
                ),
                encoding="utf-8",
            )
            manifests[phase] = path
        comparison = restore_root / "server-comparison.json"
        comparison.write_text(
            json.dumps(
                {
                    "run_id": self.run_id,
                    "target": "server",
                    "result": "PASS",
                    "before_manifest": "backup-restore/server-before.json",
                    "after_manifest": "backup-restore/server-after.json",
                    "before_manifest_sha256": manage_pilot_run.sha256(
                        manifests["before"]
                    ),
                    "after_manifest_sha256": manage_pilot_run.sha256(
                        manifests["after"]
                    ),
                    "source_machine_id": "SOURCE-01",
                    "restore_machine_id": "RESTORE-02",
                    "backup_set_id": "BACKUP-001",
                    "restore_approval_id": "APPROVAL-001",
                    "table_counts_equal": True,
                    "table_count_mismatch_count": 0,
                    "file_manifest_equal": True,
                    "file_mismatch_counts": {
                        "missing": 0,
                        "extra": 0,
                        "size": 0,
                        "sha256": 0,
                    },
                    "database_checks": {
                        "database_file_equal": True,
                        "before_quick_check_ok": True,
                        "before_integrity_check_ok": True,
                        "before_foreign_key_violation_count": 0,
                        "after_quick_check_ok": True,
                        "after_integrity_check_ok": True,
                        "after_foreign_key_violation_count": 0,
                        "before_capture_stable": True,
                        "before_checkpoint_clean": True,
                        "after_capture_stable": True,
                        "after_checkpoint_clean": True,
                    },
                    "file_capture_checks": {
                        "before_capture_stable": True,
                        "after_capture_stable": True,
                    },
                }
            ),
            encoding="utf-8",
        )
        evidence = ["backup-restore/server-comparison.json"]

        self.assertEqual(
            [],
            manage_pilot_run.restore_comparison_failures(
                self.run_root, evidence, "server"
            ),
        )

        manifests["after"].write_text("{}", encoding="utf-8")
        self.assertTrue(
            manage_pilot_run.restore_comparison_failures(
                self.run_root, evidence, "server"
            )
        )

    def test_role_metrics_raw_rows_must_match_summary(self) -> None:
        path = self.run_root / "scenario-results" / "role-metrics.csv"
        path.parent.mkdir(parents=True)
        fieldnames = [
            "role",
            "participant_id",
            "scenario_id",
            "required",
            "success",
            "elapsed_seconds",
            "retry_count",
            "help_request_count",
            "screen_transitions",
            "critical_blocker",
            "evidence",
        ]
        expected = {}
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames)
            writer.writeheader()
            for role, scenarios in manage_pilot_run.ROLE_SCENARIOS.items():
                for scenario in scenarios:
                    for attempt in range(2):
                        writer.writerow(
                            {
                                "role": role,
                                "participant_id": f"PARTICIPANT-{role}-{attempt}",
                                "scenario_id": scenario,
                                "required": "TRUE",
                                "success": "TRUE",
                                "elapsed_seconds": "10",
                                "retry_count": "0",
                                "help_request_count": "0",
                                "screen_transitions": "2",
                                "critical_blocker": "FALSE",
                                "evidence": "proof.txt",
                            }
                        )
                expected[role] = {
                    "required_attempts": len(scenarios) * 2,
                    "successful_attempts": len(scenarios) * 2,
                    "success_rate_percent": 100,
                    "median_seconds": 10,
                    "maximum_seconds": 10,
                    "retry_count": 0,
                    "help_request_count": 0,
                    "screen_transition_count": len(scenarios) * 4,
                    "critical_blockers": 0,
                }

        self.assertEqual(
            [], manage_pilot_run.role_metrics_csv_failures(self.run_root, expected)
        )

if __name__ == "__main__":
    unittest.main()
