from __future__ import annotations

import argparse
import contextlib
import csv
import importlib.util
import io
import unittest
import uuid
from pathlib import Path


SCRIPT_PATH = Path(__file__).with_name("manage-pilot-run.py")
SPEC = importlib.util.spec_from_file_location("manage_pilot_run_android", SCRIPT_PATH)
assert SPEC and SPEC.loader
manage_pilot_run = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manage_pilot_run)


class AndroidFieldUxEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.evidence_root = (
            SCRIPT_PATH.parent.parent
            / "data"
            / "local"
            / "pilot-tool-tests"
            / f"manage-pilot-run-android-{uuid.uuid4().hex}"
        )
        self.run_id = "PILOT-20260731-ANDROID-UX-001"
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
        (self.run_root / "proof.txt").write_text(
            "preserved Android field UX evidence\n", encoding="utf-8"
        )

    def write_pass_rows(self) -> Path:
        path = self.run_root / "scenario-results" / "android-field-ux.csv"
        fieldnames = [
            "scenario_id",
            "condition",
            "input_kind",
            "participant_code",
            "attempt",
            "success",
            "elapsed_seconds",
            "help_requests",
            "critical_blockers",
            "source_id",
            "handover_id",
            "evidence",
            "result",
        ]
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames)
            writer.writeheader()
            for index, (scenario_id, condition, input_kind) in enumerate(
                manage_pilot_run.ANDROID_FIELD_UX_CASES,
                start=1,
            ):
                writer.writerow(
                    {
                        "scenario_id": scenario_id,
                        "condition": condition,
                        "input_kind": input_kind,
                        "participant_code": "FIELD-01",
                        "attempt": 1,
                        "success": "TRUE",
                        "elapsed_seconds": index,
                        "help_requests": 0,
                        "critical_blockers": 0,
                        "source_id": f"source_{index}",
                        "handover_id": (
                            f"handover_{index}" if input_kind == "handover" else ""
                        ),
                        "evidence": "proof.txt",
                        "result": "PASS",
                    }
                )
        return path

    def test_prepare_requires_all_ten_field_input_conditions(self) -> None:
        path = self.run_root / "scenario-results" / "android-field-ux.csv"
        with path.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))

        self.assertEqual(10, len(rows))
        self.assertEqual(
            {item[0] for item in manage_pilot_run.ANDROID_FIELD_UX_CASES},
            {row["scenario_id"] for row in rows},
        )
        self.assertTrue(manage_pilot_run.android_field_ux_csv_failures(self.run_root))

    def test_all_field_input_rows_must_pass_with_source_evidence(self) -> None:
        path = self.write_pass_rows()
        self.assertEqual(
            [], manage_pilot_run.android_field_ux_csv_failures(self.run_root)
        )

        with path.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        rows[0]["critical_blockers"] = "1"
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)

        self.assertTrue(
            any(
                "치명적 blocker" in failure
                for failure in manage_pilot_run.android_field_ux_csv_failures(
                    self.run_root
                )
            )
        )


if __name__ == "__main__":
    unittest.main()
