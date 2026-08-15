from __future__ import annotations

import unittest
from pathlib import Path

from scripts.check_public_tree import check_text, check_tracked_path


class PublicTreePathTests(unittest.TestCase):
    def test_allows_only_api_data_placeholders(self) -> None:
        self.assertEqual([], check_tracked_path(Path("services/api/data/.gitkeep")))
        self.assertEqual([], check_tracked_path(Path("services/api/storage/.gitkeep")))

    def test_rejects_root_and_api_runtime_data(self) -> None:
        for path in (
            Path("data/local/result.txt"),
            Path("Data/Files/photo.jpg"),
            Path("storage/reports/report.txt"),
            Path("services/api/data/result.json"),
            Path("services/api/storage/uploads/document.txt"),
        ):
            with self.subTest(path=path):
                self.assertTrue(check_tracked_path(path))

    def test_rejects_wpf_runtime_data(self) -> None:
        path = Path("apps/windows/src/FlowNote.Windows.App/Data/Files/sample.txt")
        self.assertTrue(check_tracked_path(path))


class PublicTreeTextTests(unittest.TestCase):
    def test_allows_explicit_example_user_paths(self) -> None:
        text = "/Users/example/input.txt C:\\Users\\example-user\\input.txt"
        self.assertEqual([], check_text(Path("tests/fixture.txt"), text))

    def test_rejects_machine_local_user_paths(self) -> None:
        for text in (
            "/Users/" + "real-user/private/input.txt",
            "/home/" + "developer/private/input.txt",
            "C:\\Users\\" + r"local-user\private\input.txt",
        ):
            with self.subTest(text=text):
                errors = check_text(Path("docs/example.md"), text)
                self.assertTrue(
                    any("machine-local user path" in error for error in errors)
                )

    def test_allows_only_reserved_or_noreply_email_addresses(self) -> None:
        text = "security@flownote.example contributor@users.noreply.github.com"
        self.assertEqual([], check_text(Path("SECURITY.md"), text))

        private_email = "person" + "@private-company.test"
        errors = check_text(Path("docs/contact.md"), private_email)
        self.assertTrue(any("non-example email address" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
