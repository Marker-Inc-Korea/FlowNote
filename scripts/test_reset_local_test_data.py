from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.reset_local_test_data import run


class ResetLocalTestDataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_directory.name)
        for marker in (
            Path(".gitignore"),
            Path("services/api/pyproject.toml"),
            Path("apps/windows/src/FlowNote.Windows.Core/marker.txt"),
            Path("apps/android/settings.gradle"),
        ):
            target = self.root / marker
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("marker", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def write_file(self, relative: str, content: str = "test") -> Path:
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    def test_dry_run_does_not_remove_anything(self) -> None:
        database = self.write_file("data/local/flownote.local.sqlite")
        result = run(apply=False, root=self.root)
        self.assertEqual(0, result)
        self.assertTrue(database.exists())

    def test_apply_removes_generated_data_but_preserves_source_and_settings(self) -> None:
        self.write_file("data/local/flownote.local.sqlite")
        self.write_file("tmp/smoke/run.log")
        self.write_file("artifacts/wpf-msi/app.msi")
        self.write_file("services/api/data/.gitkeep", "")
        self.write_file("services/api/data/flownote.test.sqlite3")
        self.write_file("services/api/storage/.gitkeep", "")
        self.write_file("services/api/storage/test/document.txt")
        self.write_file("services/api/.env", "KEEP=1")
        test_source = self.write_file("services/api/tests/test_example.py", "def test_ok(): pass")
        self.write_file("services/api/tests/__pycache__/test_example.pyc")

        result = run(apply=True, root=self.root)

        self.assertEqual(0, result)
        self.assertFalse((self.root / "data").exists())
        self.assertFalse((self.root / "tmp").exists())
        self.assertFalse((self.root / "artifacts").exists())
        self.assertTrue((self.root / "services/api/data/.gitkeep").exists())
        self.assertEqual(
            [".gitkeep"],
            sorted(path.name for path in (self.root / "services/api/data").iterdir()),
        )
        self.assertTrue((self.root / "services/api/storage/.gitkeep").exists())
        self.assertTrue((self.root / "services/api/.env").exists())
        self.assertTrue(test_source.exists())
        self.assertFalse((self.root / "services/api/tests/__pycache__").exists())

    def test_refuses_a_directory_without_repository_markers(self) -> None:
        empty_root = self.root / "not-a-repository"
        empty_root.mkdir()
        with self.assertRaises(RuntimeError):
            run(apply=True, root=empty_root)


if __name__ == "__main__":
    unittest.main()
