"""Application assembly tests: exercise the real CLI through app.main()."""

from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from byggleaf import app


class AppTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.cwd = mock.patch("byggleaf.cli.Path.cwd", return_value=self.root)
        self.cwd.start()

    def tearDown(self) -> None:
        self.cwd.stop()
        self.tempdir.cleanup()

    def run_app(self, *args: str) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = app.main(list(args))
        return code, stdout.getvalue(), stderr.getvalue()

    def test_init_build_new_and_clean_lifecycle(self) -> None:
        code, output, error = self.run_app("init")
        self.assertEqual(code, 0, error)
        self.assertIn("The garden is ready.", output)
        self.assertTrue((self.root / "byggleaf.toml").is_file())

        code, output, error = self.run_app("build")
        self.assertEqual(code, 0, error)
        self.assertIn("Built in", output)
        self.assertTrue((self.root / "public/index.html").is_file())

        code, output, error = self.run_app("new", "content")
        self.assertEqual(code, 0, error)
        self.assertIn("Created a new article.", output)
        self.assertTrue(list((self.root / "content/posts").glob("new-article*.md")))

        code, output, error = self.run_app("clean")
        self.assertEqual(code, 0, error)
        self.assertIn("Removed public/", output)
        self.assertFalse((self.root / "public").exists())

        code, output, error = self.run_app("serve")
        self.assertEqual(code, 1)
        self.assertIn("public/ does not exist", error)

    def test_build_failure_returns_one_and_reports_errors(self) -> None:
        self.assertEqual(self.run_app("init")[0], 0)
        broken = self.root / "content/posts/broken.md"
        broken.write_text("+++\ntitle = \"Broken\"\n+++\n", encoding="utf-8")

        code, _, error = self.run_app("build")
        self.assertEqual(code, 1)
        self.assertIn("error:", error)
        self.assertIn("date", error)
        self.assertFalse((self.root / "public").exists())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
