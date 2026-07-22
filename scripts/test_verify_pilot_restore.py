from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import sqlite3
import unittest
import uuid
from pathlib import Path


SCRIPT_PATH = Path(__file__).with_name("verify-pilot-restore.py")
SPEC = importlib.util.spec_from_file_location("verify_pilot_restore", SCRIPT_PATH)
assert SPEC and SPEC.loader
verify_pilot_restore = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify_pilot_restore)


class PilotRestoreVerificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = (
            SCRIPT_PATH.parent.parent
            / "data"
            / "local"
            / "pilot-tool-tests"
            / f"verify-pilot-restore-{uuid.uuid4().hex}"
        )
        self.root.mkdir(parents=True)
        self.run_id = "PILOT-20260722-1500-LOCALCHECK-007"

    def create_set(self, name: str, payload: bytes = b"same-file") -> tuple[Path, Path]:
        root = self.root / name
        files = root / "storage"
        files.mkdir(parents=True)
        (files / "document.bin").write_bytes(payload)
        database = root / "flownote.sqlite3"
        with sqlite3.connect(database) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(
                "CREATE TABLE documents (id INTEGER PRIMARY KEY, title TEXT NOT NULL)"
            )
            connection.execute("INSERT INTO documents(title) VALUES ('test')")
        return database, files

    def capture(self, phase: str, machine_id: str, database: Path, files: Path) -> Path:
        args = argparse.Namespace(
            run_id=self.run_id,
            target="server",
            phase=phase,
            database=database,
            files=files,
            machine_id=machine_id,
            backup_set_id="BACKUP-SET-007",
            restore_approval_id="APPROVAL-007",
            evidence_root=self.root,
        )
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(0, verify_pilot_restore.capture(args))
        return self.root / self.run_id / "backup-restore" / f"server-{phase}.json"

    def test_separate_machine_lossless_restore_passes_with_zero_mismatches(
        self,
    ) -> None:
        before_db, before_files = self.create_set("source")
        after_db, after_files = self.create_set("restore")
        before = self.capture("before", "SERVER-SOURCE-01", before_db, before_files)
        after = self.capture("after", "SERVER-RESTORE-02", after_db, after_files)
        output = self.root / self.run_id / "backup-restore" / "server-comparison.json"

        with contextlib.redirect_stdout(io.StringIO()):
            result = verify_pilot_restore.compare(
                argparse.Namespace(before=before, after=after, output=output)
            )

        report = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(0, result)
        self.assertEqual("PASS", report["result"])
        self.assertEqual(0, report["table_count_mismatch_count"])
        self.assertEqual(
            {"missing": 0, "extra": 0, "size": 0, "sha256": 0},
            report["file_mismatch_counts"],
        )
        self.assertTrue(report["database_checks"]["after_integrity_check_ok"])

    def test_same_machine_or_hash_mismatch_fails_closed(self) -> None:
        before_db, before_files = self.create_set("source")
        after_db, after_files = self.create_set("restore", b"changed-file")
        before = self.capture("before", "SERVER-SAME-01", before_db, before_files)
        after = self.capture("after", "SERVER-SAME-01", after_db, after_files)
        output = (
            self.root / self.run_id / "backup-restore" / "server-comparison-fail.json"
        )

        with (
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            result = verify_pilot_restore.compare(
                argparse.Namespace(before=before, after=after, output=output)
            )

        report = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(1, result)
        self.assertEqual("FAIL", report["result"])
        self.assertEqual(1, report["file_mismatch_counts"]["size"])
        self.assertEqual(1, report["file_mismatch_counts"]["sha256"])
        self.assertTrue(any("별도 PC" in failure for failure in report["failures"]))


if __name__ == "__main__":
    unittest.main()
