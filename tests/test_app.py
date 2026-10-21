"""Application assembly tests: exercise the real CLI through app.main()."""

from __future__ import annotations

import importlib.abc
import io
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from byggleaf import app
from byggleaf.core.clean import CleanError
from byggleaf.core.server import ServerError


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

    def test_build_failure_preserves_the_previous_site(self) -> None:
        self.assertEqual(self.run_app("init")[0], 0)
        self.assertEqual(self.run_app("build")[0], 0)
        (self.root / "content/posts/broken.md").write_text(
            '+++\ntitle = "Broken"\n+++\n\nBody.\n', encoding="utf-8"
        )

        code, _, error = self.run_app("build")
        self.assertEqual(code, 1)
        self.assertIn("preserved", error)
        self.assertTrue((self.root / "public/index.html").is_file())

    def test_build_without_favicon_omits_the_favicon_summary(self) -> None:
        self.assertEqual(self.run_app("init")[0], 0)
        (self.root / "assets/img/favicon.ico").unlink()

        code, output, _ = self.run_app("build")
        self.assertEqual(code, 0)
        self.assertNotIn("favicon", output)

    def test_init_refuses_an_existing_garden(self) -> None:
        self.assertEqual(self.run_app("init")[0], 0)

        code, _, error = self.run_app("init")
        self.assertEqual(code, 1)
        self.assertIn("already exists", error)

    def test_init_keeps_existing_user_files(self) -> None:
        posts = self.root / "content/posts"
        posts.mkdir(parents=True)
        (posts / "hello-world.md").write_text("user text", encoding="utf-8")

        code, output, error = self.run_app("init")
        self.assertEqual(code, 0, error)
        self.assertIn("keep", output)
        self.assertEqual(
            (posts / "hello-world.md").read_text(encoding="utf-8"), "user text"
        )

    def test_clean_reports_nothing_to_do_when_public_is_absent(self) -> None:
        code, output, _ = self.run_app("clean")
        self.assertEqual(code, 0)
        self.assertIn("nothing to do", output)

    def test_clean_unlinks_a_public_symlink_without_following_it(self) -> None:
        outside = self.root.parent / f"byggleaf-outside-{self.root.name}"
        outside.mkdir()
        try:
            (self.root / "public").symlink_to(outside, target_is_directory=True)
            code, output, error = self.run_app("clean")
            self.assertEqual(code, 0, error)
            self.assertIn("Removed public/", output)
            self.assertFalse((self.root / "public").exists())
            self.assertTrue(outside.is_dir())
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_clean_error_is_reported(self) -> None:
        with mock.patch(
            "byggleaf.core.clean.clean_output", side_effect=CleanError("boom")
        ):
            code, _, error = self.run_app("clean")
        self.assertEqual(code, 1)
        self.assertIn("boom", error)

    def test_new_outside_a_garden_is_rejected(self) -> None:
        code, _, error = self.run_app("new", "content")
        self.assertEqual(code, 1)
        self.assertIn("init", error)

    def test_display_prefers_root_relative_paths(self) -> None:
        self.assertEqual(app._display(self.root / "public", self.root), "public")
        self.assertEqual(
            app._display(Path("/etc/hostname"), self.root), "/etc/hostname"
        )

    def test_serve_warns_when_baseurl_is_remote(self) -> None:
        self.assertEqual(self.run_app("init")[0], 0)
        self.assertEqual(self.run_app("build")[0], 0)

        def fake_serve(directory, *, host, port, on_ready=None):
            on_ready(f"http://127.0.0.1:{port}/")

        with mock.patch("byggleaf.core.server.serve", side_effect=fake_serve):
            code, output, error = self.run_app("serve")
        self.assertEqual(code, 0, error)
        self.assertIn("note: pages use baseurl", output)

    def test_serve_matches_when_baseurl_is_the_local_preview(self) -> None:
        self.assertEqual(self.run_app("init")[0], 0)
        self.assertEqual(self.run_app("build")[0], 0)
        config_path = self.root / "byggleaf.toml"
        config_path.write_text(
            config_path.read_text(encoding="utf-8").replace(
                "https://example.com", "http://127.0.0.1:6789"
            ),
            encoding="utf-8",
        )

        def fake_serve(directory, *, host, port, on_ready=None):
            on_ready(f"http://127.0.0.1:{port}/")

        with mock.patch("byggleaf.core.server.serve", side_effect=fake_serve):
            code, output, error = self.run_app("serve")
        self.assertEqual(code, 0, error)
        self.assertNotIn("note: pages use baseurl", output)

    def test_serve_warns_about_a_wildcard_bind(self) -> None:
        self.assertEqual(self.run_app("init")[0], 0)
        self.assertEqual(self.run_app("build")[0], 0)

        def fake_serve(directory, *, host, port, on_ready=None):
            on_ready(f"http://{host}:{port}/")

        with mock.patch("byggleaf.core.server.serve", side_effect=fake_serve):
            code, output, error = self.run_app("serve", "--bind", "0.0.0.0")
        self.assertEqual(code, 0, error)
        self.assertIn("Bound to all interfaces", output)

    def test_serve_tolerates_an_unreadable_config(self) -> None:
        self.assertEqual(self.run_app("init")[0], 0)
        self.assertEqual(self.run_app("build")[0], 0)
        (self.root / "byggleaf.toml").write_text(
            "this is not [ valid toml", encoding="utf-8"
        )

        def fake_serve(directory, *, host, port, on_ready=None):
            on_ready(f"http://127.0.0.1:{port}/")

        with mock.patch("byggleaf.core.server.serve", side_effect=fake_serve):
            code, _, error = self.run_app("serve")
        self.assertEqual(code, 0, error)

    def test_serve_reports_bind_errors(self) -> None:
        self.assertEqual(self.run_app("init")[0], 0)
        self.assertEqual(self.run_app("build")[0], 0)

        with mock.patch(
            "byggleaf.core.server.serve", side_effect=ServerError("cannot serve")
        ):
            code, _, error = self.run_app("serve")
        self.assertEqual(code, 1)
        self.assertIn("cannot serve", error)

    def test_serve_reports_os_errors(self) -> None:
        self.assertEqual(self.run_app("init")[0], 0)
        self.assertEqual(self.run_app("build")[0], 0)

        with mock.patch(
            "byggleaf.core.server.serve", side_effect=OSError("permission denied")
        ):
            code, _, error = self.run_app("serve")
        self.assertEqual(code, 1)
        self.assertIn("permission denied", error)


class _BlockedDependencies(importlib.abc.MetaPathFinder):
    """A meta-path finder that makes third-party dependencies unimportable."""

    def __init__(self, *names: str) -> None:
        self._names = frozenset(names)

    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".", 1)[0] in self._names:
            raise ModuleNotFoundError(f"blocked by test: {fullname}")
        return None


class DependencyFreeEntryTests(unittest.TestCase):
    def test_version_and_help_work_without_runtime_dependencies(self) -> None:
        cached = {
            name: sys.modules.pop(name)
            for name in list(sys.modules)
            if name.split(".", 1)[0] in {"markdown", "jinja2", "markupsafe"}
        }
        finder = _BlockedDependencies("markdown", "jinja2", "markupsafe")
        sys.meta_path.insert(0, finder)
        try:
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                with self.assertRaises(SystemExit) as raised:
                    app.main(["--version"])
            self.assertEqual(raised.exception.code, 0)
            self.assertIn("ByggLeaf", stdout.getvalue())

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                with self.assertRaises(SystemExit) as raised_help:
                    app.main(["--help"])
            self.assertEqual(raised_help.exception.code, 0)
            self.assertIn("usage:", stdout.getvalue())
        finally:
            sys.meta_path.remove(finder)
            sys.modules.update(cached)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
