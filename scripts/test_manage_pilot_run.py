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


SCRIPT_PATH = Path(__file__).with_name("manage-pilot-run.py")
SPEC = importlib.util.spec_from_file_location("manage_pilot_run", SCRIPT_PATH)
assert SPEC and SPEC.loader
manage_pilot_run = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manage_pilot_run)


class WindowsServerRehearsalVerificationTests(unittest.TestCase):
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
        return record

    def test_prepare_creates_schema_three_authorization_templates(self) -> None:
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
        self.assertEqual(3, record["schema_version"])
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
                self.evidence_root / run_id / "approvals" / "rehearsal-authorization.md"
            ).is_file()
        )

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

    def test_owner_cannot_self_approve(self) -> None:
        record = self.complete_record()
        record["responsibilities"]["server"]["approver"] = " OWNER-0 "

        result, report = self.verify(record)

        self.assertEqual(1, result)
        self.assertIn(
            "책임 영역 server는 담당자와 독립 승인자가 달라야 합니다.",
            report["failures"],
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
            "evidence",
        ]
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames)
            writer.writeheader()
            for case in manage_pilot_run.RESTORE_FAULT_CASES:
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
                        "evidence": "proof.txt",
                    }
                )

        self.assertEqual(
            [], manage_pilot_run.restore_fault_injection_failures(self.run_root)
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
            "critical_blocker",
            "evidence",
        ]
        expected = {}
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames)
            writer.writeheader()
            for role, scenarios in manage_pilot_run.ROLE_SCENARIOS.items():
                for scenario in scenarios:
                    writer.writerow(
                        {
                            "role": role,
                            "participant_id": f"PARTICIPANT-{role}",
                            "scenario_id": scenario,
                            "required": "TRUE",
                            "success": "TRUE",
                            "elapsed_seconds": "10",
                            "retry_count": "0",
                            "help_request_count": "0",
                            "critical_blocker": "FALSE",
                            "evidence": "proof.txt",
                        }
                    )
                expected[role] = {
                    "required_attempts": len(scenarios),
                    "successful_attempts": len(scenarios),
                    "success_rate_percent": 100,
                    "median_seconds": 10,
                    "maximum_seconds": 10,
                    "retry_count": 0,
                    "help_request_count": 0,
                    "critical_blockers": 0,
                }

        self.assertEqual(
            [], manage_pilot_run.role_metrics_csv_failures(self.run_root, expected)
        )

    def test_actionable_observations_convert_one_to_one_to_owned_items(self) -> None:
        observations_path = self.run_root / "observations" / "role-observations.csv"
        observations_path.parent.mkdir(parents=True)
        observation_fields = [
            "observation_id",
            "role",
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
            "actionable",
            "success",
            "elapsed_seconds",
            "retry_count",
            "help_request_count",
            "notes",
            "evidence",
        ]
        with observations_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=observation_fields)
            writer.writeheader()
            for index, role in enumerate(manage_pilot_run.REQUIRED_ROLES):
                writer.writerow(
                    {
                        "observation_id": f"OBS-{index}",
                        "role": role,
                        "scenario_id": manage_pilot_run.ROLE_SCENARIOS[role][0],
                        "device_id": "DEVICE-01",
                        "location": "LINE-01",
                        "network": "DISCONNECTED" if index == 0 else "CONNECTED",
                        "gloves": "ON" if index == 0 else "OFF",
                        "one_hand": "TRUE",
                        "lighting": "NORMAL",
                        "terminal_position": "FIXED-STAND",
                        "input_moment": "AFTER-TASK",
                        "terminology_confusion": "FALSE",
                        "button_confusion": "FALSE",
                        "actionable": "TRUE" if index == 0 else "FALSE",
                        "success": "TRUE",
                        "elapsed_seconds": "10",
                        "retry_count": "0",
                        "help_request_count": "0",
                        "notes": "anonymous observation",
                        "evidence": "proof.txt",
                    }
                )

        items_path = self.run_root / "observations" / "development-items.csv"
        item_fields = [
            "item_id",
            "observation_id",
            "priority",
            "classification",
            "title",
            "acceptance_criteria",
            "owner",
            "due_date",
            "status",
            "evidence",
        ]
        with items_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=item_fields)
            writer.writeheader()
            writer.writerow(
                {
                    "item_id": "UX-001",
                    "observation_id": "OBS-0",
                    "priority": "P2",
                    "classification": "common_product",
                    "title": "장갑 입력 개선",
                    "acceptance_criteria": "같은 조건에서 첫 시도 성공",
                    "owner": "product-owner",
                    "due_date": "2026-08-31",
                    "status": "OPEN",
                    "evidence": "proof.txt",
                }
            )
        expected = {
            "actionable_findings": 1,
            "converted_items": 1,
            "unconverted_actionable_findings": 0,
            "priorities": {"P0": 0, "P1": 0, "P2": 1, "P3": 0},
            "classifications": {
                "common_product": 1,
                "device_or_mdm_setting": 0,
                "site_layout_or_training": 0,
            },
        }

        self.assertEqual([], manage_pilot_run.ux_csv_failures(self.run_root, expected))


if __name__ == "__main__":
    unittest.main()
