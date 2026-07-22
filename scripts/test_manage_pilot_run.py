from __future__ import annotations

import argparse
import contextlib
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
        record = manage_pilot_run.empty_record(
            self.run_id, "windows_server_rehearsal"
        )
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
            (self.evidence_root / run_id / "pilot-run.json").read_text(
                encoding="utf-8"
            )
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
                self.evidence_root
                / run_id
                / "approvals"
                / "rehearsal-authorization.md"
            ).is_file()
        )

    def verify(self, record: dict) -> tuple[int, dict]:
        path = self.run_root / "pilot-run.json"
        path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
            io.StringIO()
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


if __name__ == "__main__":
    unittest.main()
