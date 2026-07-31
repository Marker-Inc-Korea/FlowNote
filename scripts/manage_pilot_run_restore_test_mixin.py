from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).with_name("manage-pilot-run.py")
SPEC = importlib.util.spec_from_file_location("manage_pilot_run_restore_mixin", SCRIPT_PATH)
assert SPEC and SPEC.loader
manage_pilot_run = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manage_pilot_run)


class ManagePilotRunRestoreTestMixin:
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
                        "host_identity": {
                            "source": "unit-test-host",
                            "sha256": (
                                "a" * 64 if phase == "before" else "b" * 64
                            ),
                        },
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
                    "source_host_identity": {
                        "source": "unit-test-host",
                        "sha256": "a" * 64,
                    },
                    "restore_host_identity": {
                        "source": "unit-test-host",
                        "sha256": "b" * 64,
                    },
                    "backup_set_id": "BACKUP-001",
                    "restore_approval_id": "APPROVAL-001",
                    "table_counts_equal": True,
                    "table_count_mismatch_count": 0,
                    "responsibility_table_fingerprints_equal": True,
                    "responsibility_table_fingerprint_mismatch_count": 0,
                    "responsibility_check_violation_counts": {
                        "before": 0,
                        "after": 0,
                    },
                    "referenced_file_check_mismatch_counts": {
                        phase: {
                            "missing_count": 0,
                            "size_mismatch_count": 0,
                            "sha256_mismatch_count": 0,
                        }
                        for phase in ("before", "after")
                    },
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
