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
        self.assertIn("version_code=2", summary)

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


if __name__ == "__main__":
    unittest.main()
