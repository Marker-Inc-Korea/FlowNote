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
SPEC = importlib.util.spec_from_file_location("manage_pilot_run_readiness", SCRIPT_PATH)
assert SPEC and SPEC.loader
manage_pilot_run = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manage_pilot_run)


class PilotReadinessLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.evidence_root = (
            SCRIPT_PATH.parent.parent
            / "data"
            / "local"
            / "pilot-tool-tests"
            / f"pilot-readiness-{uuid.uuid4().hex}"
        )
        self.run_id = "PILOT-20260801-0900-FULLPILOT-901"
        with contextlib.redirect_stdout(io.StringIO()):
            manage_pilot_run.prepare(
                argparse.Namespace(
                    run_id=self.run_id,
                    evidence_root=self.evidence_root,
                    profile="full_pilot",
                    allow_existing=False,
                )
            )
        self.run_root = self.evidence_root / self.run_id
        self.record_path = self.run_root / "pilot-run.json"

    def _write_csv(
        self, relative: str, fieldnames: list[str], rows: list[dict[str, object]]
    ) -> None:
        path = self.run_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def complete_contract(self) -> dict:
        record = json.loads(self.record_path.read_text(encoding="utf-8"))
        proof = self.run_root / "approvals" / "contract-proof.txt"
        proof.write_text("preserved approval evidence\n", encoding="utf-8")
        repository = "CONTROLLED-PILOT-EVIDENCE-01"
        responsibility_rows = []
        for index, area in enumerate(manage_pilot_run.RESPONSIBILITY_AREAS):
            assignment = record["responsibilities"][area]
            assignment.update(
                {
                    "owner": f"ROLE-{area.upper()}-OWNER",
                    "approver": f"ROLE-{area.upper()}-APPROVER",
                    "test_scope": f"{area} approved scope",
                    "stop_criteria": f"stop {area} on approved critical condition",
                    "evidence_repository": repository,
                    "approved_at": f"2026-08-01T08:{index:02}:00+09:00",
                    "approval_reference": f"APPROVAL-{area.upper()}-001",
                    "approval_evidence": ["approvals/contract-proof.txt"],
                }
            )
            responsibility_rows.append(
                {
                    "area": area,
                    **{
                        field: assignment[field]
                        for field in (
                            "owner",
                            "approver",
                            "test_scope",
                            "stop_criteria",
                            "evidence_repository",
                            "approved_at",
                            "approval_reference",
                        )
                    },
                    "approval_evidence": "approvals/contract-proof.txt",
                }
            )
        self._write_csv(
            "approvals/responsibility-assignments.csv",
            list(responsibility_rows[0]),
            responsibility_rows,
        )
        authorization = record["authorization"]
        authorization.update(
            {
                "decision": "PASS",
                "approved_at": "2026-08-01T09:00:00+09:00",
                "run_scope": "single full pilot approved scope",
                "stop_criteria": [
                    "data loss detected",
                    "permission bypass detected",
                    "unauthorized disclosure detected",
                    "database integrity failure detected",
                    "rollback or core workflow recovery failed",
                ],
                "evidence_repository": repository,
                "retention_until": "2027-08-01",
                "equipment": {
                    "server_ids": ["SRV-PILOT-01"],
                    "windows_client_ids": ["WIN-PILOT-01"],
                    "android_device_ids": ["AND-PILOT-01"],
                },
                "previous_approved_versions": {
                    "server": "server-approved-1",
                    "wpf": "wpf-approved-1",
                    "android": "android-approved-1",
                },
                "rollback_decision_authority": "ROLE-ROLLBACK-01",
                "emergency_contact_flow": "FLOW-EMERGENCY-01",
                "recovery_objectives": {
                    target: {"rto_seconds": 300, "rpo_seconds": 60}
                    for target in ("server_restore", "wpf_restore", "rollback")
                },
                "previous_approved_packages": {
                    target: {
                        "version": f"{target}-approved-1",
                        "sha256": "a" * 64,
                        "signer_sha256": "b" * 64,
                    }
                    for target in ("server", "wpf", "android")
                },
                "evidence": ["approvals/contract-proof.txt"],
            }
        )
        signature_rows = []
        for index, area in enumerate(manage_pilot_run.REQUIRED_APPROVALS):
            approval = authorization["approvals"][area]
            approval.update(
                {
                    "decision": "PASS",
                    "signer": f"ROLE-{area.upper()}-SIGNER-{index}",
                    "signed_at": f"2026-08-01T08:5{index}:00+09:00",
                    "approval_reference": f"PILOT-{area.upper()}-APPROVAL-001",
                    "evidence": ["approvals/contract-proof.txt"],
                }
            )
            signature_rows.append(
                {
                    "area": area,
                    "decision": approval["decision"],
                    "signer": approval["signer"],
                    "signed_at": approval["signed_at"],
                    "approval_reference": approval["approval_reference"],
                    "evidence": "approvals/contract-proof.txt",
                }
            )
        record["environment"].update(
            {
                "customer_like_network": True,
                "clean_server_count": 1,
                "clean_windows_client_count": 1,
                "approved_android_count": 1,
            }
        )
        self._write_csv(
            "approvals/pilot-approval-signatures.csv",
            list(signature_rows[0]),
            signature_rows,
        )
        self.record_path.write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return record

    def authorize(self) -> int:
        with (
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            return manage_pilot_run.authorize_command(
                argparse.Namespace(run_id=self.run_id, evidence_root=self.evidence_root)
            )

    def test_prepare_blocks_operational_inputs_before_approval(self) -> None:
        self.assertFalse((self.run_root / "install").exists())
        self.assertFalse((self.run_root / "backup-restore").exists())
        self.assertFalse(
            (self.run_root / "packages" / "android-release-approval.csv").exists()
        )
        self.assertEqual(
            "DRAFT", manage_pilot_run.pilot_readiness.authorization_status(self.run_root)
        )
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
        self.assertEqual(1, result)
        self.assertTrue(
            any("운영 입력이 잠겨" in failure for failure in report["failures"])
        )

    def test_authorize_binds_contract_to_run_and_opens_templates(self) -> None:
        self.complete_contract()

        self.assertEqual(0, self.authorize())
        events = manage_pilot_run.pilot_readiness.read_events(self.run_root)
        self.assertEqual("AUTHORIZED", events[-1]["event"])
        self.assertEqual(self.run_id, events[-1]["run_id"])
        self.assertTrue(events[-1]["contract_sha256"])
        self.assertTrue((self.run_root / "install").is_dir())
        self.assertTrue((self.run_root / "backup-restore").is_dir())
        self.assertTrue(
            (self.run_root / "packages" / "android-release-approval.csv").is_file()
        )

    def test_revocation_relocks_inputs_and_preserves_raw_evidence(self) -> None:
        record = self.complete_contract()
        self.assertEqual(0, self.authorize())
        raw = self.run_root / "scenario-results" / "preserved-raw.txt"
        raw.write_text("never delete this evidence\n", encoding="utf-8")

        manage_pilot_run.pilot_readiness.transition(
            self.run_root,
            record,
            "REVOKED",
            "ROLE-SECURITY-SIGNER",
            "approval scope withdrawn",
        )

        failures = manage_pilot_run.pilot_readiness.execution_access_failures(
            self.run_root, record
        )
        self.assertTrue(any("REVOKED" in failure for failure in failures))
        self.assertEqual("never delete this evidence\n", raw.read_text(encoding="utf-8"))

    def test_stop_and_resume_require_approved_criterion_and_rollback_authority(self) -> None:
        record = self.complete_contract()
        self.assertEqual(0, self.authorize())
        criterion = record["authorization"]["stop_criteria"][0]
        manage_pilot_run.pilot_readiness.transition(
            self.run_root,
            record,
            "STOPPED",
            "ROLE-FIELD-OWNER",
            "criterion observed",
            criterion=criterion,
        )
        with self.assertRaisesRegex(ValueError, "rollback 결정권자"):
            manage_pilot_run.pilot_readiness.transition(
                self.run_root,
                record,
                "RESUMED",
                "ROLE-OTHER",
                "resume requested",
                approval_reference="RESUME-APPROVAL-001",
            )
        manage_pilot_run.pilot_readiness.transition(
            self.run_root,
            record,
            "RESUMED",
            "ROLE-ROLLBACK-01",
            "rollback state verified",
            approval_reference="RESUME-APPROVAL-001",
        )
        self.assertEqual(
            [],
            manage_pilot_run.pilot_readiness.execution_access_failures(
                self.run_root, record
            ),
        )


if __name__ == "__main__":
    unittest.main()
