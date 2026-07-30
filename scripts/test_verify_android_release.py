from __future__ import annotations

import os
import subprocess
import unittest
import uuid
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPOSITORY_ROOT / "scripts" / "verify-android-release.sh"


class AndroidReleaseVerifierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = (
            REPOSITORY_ROOT
            / "data"
            / "local"
            / "pilot-tool-tests"
            / f"verify-android-release-{uuid.uuid4().hex}"
        )
        self.bin = self.root / "bin"
        self.bin.mkdir(parents=True)
        self.artifact = self.root / "candidate.apk"
        self.artifact.write_bytes(b"preserved fake signed APK fixture\n")
        self.run_id = "PILOT-20260722-1400-LOCALCHECK-004"
        self._stub(
            "apksigner",
            "printf '%s\\n' 'Signer #1 certificate SHA-256 digest: AA:BB:CC'",
        )
        self._stub(
            "aapt",
            "printf \"%s\\n\" \"package: name='com.flownote.fieldapp' versionCode='2' versionName='0.2.0'\"",
        )
        self._stub(
            "apkanalyzer",
            "printf '%s\\n' '<application android:allowBackup=\"false\" android:usesCleartextTraffic=\"false\" />'",
        )

    def _stub(self, name: str, body: str) -> None:
        path = self.bin / name
        path.write_text(f"#!/usr/bin/env bash\nset -eu\n{body}\n", encoding="utf-8")
        path.chmod(0o755)

    def _configure_device_stubs(self) -> tuple[Path, dict[str, str]]:
        previous = self.root / "previous.apk"
        previous.write_bytes(b"preserved previous approved APK fixture\n")
        nonce_file = self.root / "outbox-audit-nonce.txt"
        self._stub(
            "aapt",
            """
case "$*" in
  *previous.apk*) version_code=1; version_name=0.1.0 ;;
  *) version_code=2; version_name=0.2.0 ;;
esac
printf "package: name='com.flownote.fieldapp' versionCode='%s' versionName='%s'\\n" \
  "$version_code" "$version_name"
""".strip(),
        )
        self._stub(
            "adb",
            """
case "$*" in
  *" get-state") printf '%s\\n' device ;;
  *" shell am start "*)
    printf '%s\\n' "${!#}" > "$ADB_AUDIT_NONCE_FILE"
    printf '%s\\n' "Status: ok"
    ;;
  *" logcat -d -v brief FlowNoteOutbox:I "*)
    nonce="$(cat "$ADB_AUDIT_NONCE_FILE")"
    printf 'I/FlowNoteOutbox: audit_nonce=%s pending=%s blocked=0\\n' \
      "$nonce" "$ADB_OUTBOX_PENDING"
    ;;
  *" install -r -d "*) printf '%s\\n' Success ;;
  *" install -r "*) printf '%s\\n' Success ;;
  *) printf '%s\\n' ok ;;
esac
""".strip(),
        )
        environment = os.environ.copy()
        environment["PATH"] = f"{self.bin}:{environment['PATH']}"
        environment["ADB_AUDIT_NONCE_FILE"] = str(nonce_file)
        return previous, environment

    def test_offline_apk_verification_preserves_manifest_signature_and_hash(self) -> None:
        environment = os.environ.copy()
        environment["PATH"] = f"{self.bin}:{environment['PATH']}"
        completed = subprocess.run(
            [str(SCRIPT), self.run_id, str(self.artifact), str(self.root / "evidence")],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        packages = self.root / "evidence" / self.run_id / "packages"
        self.assertTrue((packages / "android-package-sha256.txt").is_file())
        self.assertTrue((packages / "android-signature.txt").is_file())
        summary = (packages / "android-release-verification.txt").read_text(
            encoding="utf-8"
        )
        self.assertIn("result=PASS", summary)
        self.assertIn("operational_scenarios=NOT_RUN", summary)
        self.assertIn("version_code=2", summary)
        scenario_dir = (
            self.root / "evidence" / self.run_id / "scenario-results"
        )
        delivery = (scenario_dir / "android-delivery.csv").read_text(encoding="utf-8")
        ux = (scenario_dir / "android-field-ux.csv").read_text(encoding="utf-8")
        self.assertIn("AND-HANDOVER-IDEMPOTENCY", delivery)
        self.assertIn("AND-OUTBOX-DEVICE-INACTIVE", delivery)
        self.assertIn("AND-UX-GLOVE-HANDOVER", ux)
        self.assertIn("AND-UX-PHOTO-RESET", ux)

    def test_install_requires_explicit_approved_device_serial(self) -> None:
        environment = os.environ.copy()
        environment["PATH"] = f"{self.bin}:{environment['PATH']}"
        completed = subprocess.run(
            [
                str(SCRIPT),
                self.run_id,
                str(self.artifact),
                str(self.root / "evidence"),
                "--install",
            ],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )

        self.assertNotEqual(0, completed.returncode)
        self.assertIn("--device-serial is required", completed.stderr)

    def test_rollback_is_blocked_until_real_device_outbox_is_empty(self) -> None:
        previous, environment = self._configure_device_stubs()
        environment["ADB_OUTBOX_PENDING"] = "2"
        completed = subprocess.run(
            [
                str(SCRIPT),
                self.run_id,
                str(self.artifact),
                str(self.root / "evidence"),
                "--device-serial",
                "approved-device-01",
                "--rollback",
                str(previous),
            ],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )

        self.assertNotEqual(0, completed.returncode)
        self.assertIn("2 pending outbox item", completed.stderr)

    def test_rollback_preserves_zero_outbox_audit_as_evidence(self) -> None:
        previous, environment = self._configure_device_stubs()
        environment["ADB_OUTBOX_PENDING"] = "0"
        completed = subprocess.run(
            [
                str(SCRIPT),
                self.run_id,
                str(self.artifact),
                str(self.root / "evidence"),
                "--device-serial",
                "approved-device-01",
                "--rollback",
                str(previous),
            ],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        audit = (
            self.root
            / "evidence"
            / self.run_id
            / "integrity"
            / "android-outbox-before-rollback.txt"
        ).read_text(encoding="utf-8")
        self.assertIn("pending=0", audit)


if __name__ == "__main__":
    unittest.main()
