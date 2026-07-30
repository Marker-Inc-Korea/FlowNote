from __future__ import annotations

import argparse
import contextlib
import hashlib
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
        return self.capture_target(
            "server", phase, machine_id, database, files
        )

    def capture_target(
        self,
        target: str,
        phase: str,
        machine_id: str,
        database: Path,
        files: Path,
    ) -> Path:
        args = argparse.Namespace(
            run_id=self.run_id,
            target=target,
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
        return self.root / self.run_id / "backup-restore" / f"{target}-{phase}.json"

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
        self.assertTrue(report["database_checks"]["before_capture_stable"])
        self.assertTrue(report["database_checks"]["before_checkpoint_clean"])
        self.assertTrue(report["database_checks"]["after_capture_stable"])
        self.assertTrue(report["file_capture_checks"]["after_capture_stable"])
        self.assertTrue(report["responsibility_table_fingerprints_equal"])
        self.assertEqual(
            {"before": 0, "after": 0},
            report["responsibility_check_violation_counts"],
        )

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

    def test_same_row_count_with_changed_responsibility_data_fails(self) -> None:
        before_db, before_files = self.create_set("source")
        after_db, after_files = self.create_set("restore")
        with sqlite3.connect(after_db) as connection:
            connection.execute("UPDATE documents SET title = 'changed'")
        before = self.capture(
            "before", "SERVER-SOURCE-01", before_db, before_files
        )
        after = self.capture(
            "after", "SERVER-RESTORE-02", after_db, after_files
        )
        output = (
            self.root
            / self.run_id
            / "backup-restore"
            / "server-responsibility-fail.json"
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
        self.assertEqual(0, report["table_count_mismatch_count"])
        self.assertEqual(1, report["responsibility_table_fingerprint_mismatch_count"])
        self.assertEqual(["documents"], report["responsibility_table_fingerprint_mismatches"])

    def test_database_reference_to_missing_file_fails_capture(self) -> None:
        database, files = self.create_set("missing-reference")
        payload = (files / "document.bin").read_bytes()
        with sqlite3.connect(database) as connection:
            connection.execute(
                """
                CREATE TABLE file_objects (
                    storage_key TEXT NOT NULL,
                    size_bytes INTEGER,
                    hash_sha256 TEXT
                )
                """
            )
            connection.execute(
                "INSERT INTO file_objects VALUES (?, ?, ?)",
                (
                    "document.bin",
                    len(payload),
                    hashlib.sha256(payload).hexdigest(),
                ),
            )
        (files / "document.bin").unlink()
        args = argparse.Namespace(
            run_id=self.run_id,
            target="server",
            phase="after",
            database=database,
            files=files,
            machine_id="SERVER-RESTORE-02",
            backup_set_id="BACKUP-SET-007",
            restore_approval_id="APPROVAL-007",
            evidence_root=self.root,
        )

        with contextlib.redirect_stdout(io.StringIO()):
            result = verify_pilot_restore.capture(args)

        evidence = json.loads(
            (
                self.root
                / self.run_id
                / "backup-restore"
                / "server-after.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(1, result)
        self.assertEqual(1, evidence["referenced_file_checks"]["missing_count"])

    def test_wpf_files_relative_prefix_resolves_against_files_root(self) -> None:
        database, files = self.create_set("wpf-files-reference")
        with sqlite3.connect(database) as connection:
            connection.execute("ALTER TABLE documents ADD COLUMN document_id TEXT")
            connection.execute("ALTER TABLE documents ADD COLUMN local_path TEXT")
            connection.execute(
                "UPDATE documents SET document_id = 'doc-local', "
                r"local_path = 'Files\document.bin'"
            )
        args = argparse.Namespace(
            run_id=self.run_id,
            target="wpf",
            phase="after",
            database=database,
            files=files,
            machine_id="WPF-RESTORE-02",
            backup_set_id="BACKUP-SET-007",
            restore_approval_id="APPROVAL-007",
            evidence_root=self.root,
        )

        with contextlib.redirect_stdout(io.StringIO()):
            result = verify_pilot_restore.capture(args)

        evidence = json.loads(
            (
                self.root
                / self.run_id
                / "backup-restore"
                / "wpf-after.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(0, result)
        self.assertEqual(1, evidence["referenced_file_checks"]["reference_count"])
        self.assertEqual(0, evidence["referenced_file_checks"]["missing_count"])

    def test_server_and_wpf_must_share_backup_set_and_restore_approval(self) -> None:
        comparisons: dict[str, Path] = {}
        for target in ("server", "wpf"):
            before_db, before_files = self.create_set(f"{target}-source")
            after_db, after_files = self.create_set(f"{target}-restore")
            before = self.capture_target(
                target, "before", f"{target}-source-01", before_db, before_files
            )
            after = self.capture_target(
                target, "after", f"{target}-restore-02", after_db, after_files
            )
            output = (
                self.root
                / self.run_id
                / "backup-restore"
                / f"{target}-comparison.json"
            )
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    0,
                    verify_pilot_restore.compare(
                        argparse.Namespace(
                            before=before, after=after, output=output
                        )
                    ),
                )
            comparisons[target] = output

        output = (
            self.root
            / self.run_id
            / "backup-restore"
            / "restore-set-comparison.json"
        )
        with contextlib.redirect_stdout(io.StringIO()):
            result = verify_pilot_restore.compare_set(
                argparse.Namespace(
                    server=comparisons["server"],
                    wpf=comparisons["wpf"],
                    output=output,
                )
            )

        report = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(0, result)
        self.assertEqual("PASS", report["result"])
        self.assertEqual("BACKUP-SET-007", report["backup_set_id"])
        self.assertEqual("APPROVAL-007", report["restore_approval_id"])

    def test_existing_evidence_is_never_overwritten(self) -> None:
        database, files = self.create_set("source")
        self.capture("before", "SERVER-SOURCE-01", database, files)

        with self.assertRaisesRegex(ValueError, "덮어쓸 수 없습니다"):
            self.capture("before", "SERVER-SOURCE-01", database, files)


if __name__ == "__main__":
    unittest.main()
