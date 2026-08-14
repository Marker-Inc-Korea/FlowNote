from __future__ import annotations

import unittest

from pathlib import Path

from scripts.bootstrap_local_evaluation import render_environment, validate_output_path


class BootstrapLocalEvaluationTests(unittest.TestCase):
    TEMPLATE = "\n".join(
        (
            "FLOWNOTE_ENV=local",
            "FLOWNOTE_INITIAL_ADMIN_PASSWORD=",
            "FLOWNOTE_ACCESS_TOKEN_SECRET=replace-with-a-long-site-specific-secret",
            "FLOWNOTE_AI_EXTERNAL_CALL_ENABLED=false",
            "",
        )
    )

    def test_render_environment_replaces_public_placeholders(self) -> None:
        rendered = render_environment(
            self.TEMPLATE,
            admin_password="generated-admin-password",
            token_secret="generated-token-secret-with-more-than-32-characters",
        )

        self.assertIn("FLOWNOTE_ENV=local\n", rendered)
        self.assertIn("FLOWNOTE_INITIAL_ADMIN_PASSWORD=generated-admin-password\n", rendered)
        self.assertIn(
            "FLOWNOTE_ACCESS_TOKEN_SECRET=generated-token-secret-with-more-than-32-characters\n",
            rendered,
        )
        self.assertNotIn("replace-with-a-long-site-specific-secret", rendered)
        self.assertIn("FLOWNOTE_AI_EXTERNAL_CALL_ENABLED=false\n", rendered)

    def test_render_environment_rejects_missing_required_setting(self) -> None:
        with self.assertRaisesRegex(ValueError, "FLOWNOTE_INITIAL_ADMIN_PASSWORD"):
            render_environment(
                "FLOWNOTE_ENV=local\nFLOWNOTE_ACCESS_TOKEN_SECRET=placeholder\n",
                admin_password="generated-admin-password",
                token_secret="generated-token-secret-with-more-than-32-characters",
            )

    def test_render_environment_rejects_duplicate_required_setting(self) -> None:
        duplicate = self.TEMPLATE + "FLOWNOTE_ENV=local\n"

        with self.assertRaisesRegex(ValueError, "FLOWNOTE_ENV"):
            render_environment(
                duplicate,
                admin_password="generated-admin-password",
                token_secret="generated-token-secret-with-more-than-32-characters",
            )

    def test_output_path_must_use_git_ignored_environment_name(self) -> None:
        validate_output_path(Path("/tmp/flow-note/.env"))
        validate_output_path(Path("/tmp/flow-note/test.env.local"))
        with self.assertRaisesRegex(ValueError, "Git-ignored environment filename"):
            validate_output_path(Path("/tmp/flow-note/settings.txt"))


if __name__ == "__main__":
    unittest.main()
