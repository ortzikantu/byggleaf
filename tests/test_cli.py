"""CLI parsing and dependency-injected dispatch."""

from __future__ import annotations

import contextlib
import io
import unittest
from pathlib import Path

from byggleaf import cli
from byggleaf.core import server


class CliTests(unittest.TestCase):
    def handlers(self, captured: dict[str, object]) -> cli.Handlers:
        def init(options: cli.InitOptions) -> int:
            captured["init"] = options
            return 0

        def build(options: cli.BuildOptions) -> int:
            captured["build"] = options
            return 0

        def clean(options: cli.CleanOptions) -> int:
            captured["clean"] = options
            return 0

        def new(options: cli.NewOptions) -> int:
            captured["new"] = options
            return 0

        def serve(options: cli.ServeOptions) -> int:
            captured["serve"] = options
            return 0

        return cli.Handlers(
            init=init,
            build=build,
            clean=clean,
            new=new,
            serve=serve,
        )

    def test_build_dispatch_uses_cwd(self) -> None:
        captured: dict[str, object] = {}
        code = cli.main(["build"], handlers=self.handlers(captured))
        self.assertEqual(code, 0)
        options = captured["build"]
        self.assertIsInstance(options, cli.BuildOptions)
        self.assertEqual(options.root, Path.cwd())

    def test_init_force_flag(self) -> None:
        captured: dict[str, object] = {}
        code = cli.main(["init", "--force"], handlers=self.handlers(captured))
        self.assertEqual(code, 0)
        options = captured["init"]
        self.assertIsInstance(options, cli.InitOptions)
        self.assertTrue(options.force)

    def test_clean_dispatch_uses_cwd(self) -> None:
        captured: dict[str, object] = {}
        code = cli.main(["clean"], handlers=self.handlers(captured))
        self.assertEqual(code, 0)
        options = captured["clean"]
        self.assertIsInstance(options, cli.CleanOptions)
        self.assertEqual(options.root, Path.cwd())

    def test_new_content_dispatch(self) -> None:
        captured: dict[str, object] = {}
        code = cli.main(["new", "content"], handlers=self.handlers(captured))
        self.assertEqual(code, 0)
        options = captured["new"]
        self.assertIsInstance(options, cli.NewOptions)
        self.assertEqual(options.root, Path.cwd())
        self.assertEqual(options.kind, "content")

    def test_serve_defaults_to_loopback_port_6789(self) -> None:
        captured: dict[str, object] = {}
        code = cli.main(["serve"], handlers=self.handlers(captured))
        self.assertEqual(code, 0)
        options = captured["serve"]
        self.assertIsInstance(options, cli.ServeOptions)
        self.assertEqual(options.host, "127.0.0.1")
        self.assertEqual(options.port, 6789)

    def test_serve_custom_bind_and_port(self) -> None:
        captured: dict[str, object] = {}
        code = cli.main(
            ["serve", "--bind", "0.0.0.0", "--port", "9000"],
            handlers=self.handlers(captured),
        )
        self.assertEqual(code, 0)
        options = captured["serve"]
        self.assertEqual(options.host, "0.0.0.0")
        self.assertEqual(options.port, 9000)

    def test_serve_host_alias_still_works(self) -> None:
        captured: dict[str, object] = {}
        code = cli.main(
            ["serve", "--host", "0.0.0.0", "--port", "9001"],
            handlers=self.handlers(captured),
        )
        self.assertEqual(code, 0)
        options = captured["serve"]
        self.assertEqual(options.host, "0.0.0.0")
        self.assertEqual(options.port, 9001)

    def test_cli_and_server_defaults_agree(self) -> None:
        self.assertEqual(cli.DEFAULT_HOST, server.DEFAULT_HOST)
        self.assertEqual(cli.DEFAULT_PORT, server.DEFAULT_PORT)
        self.assertEqual(server.DEFAULT_PORT, 6789)

    def test_invalid_port_is_rejected(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                cli.main(["serve", "--port", "70000"], handlers=self.handlers({}))
        self.assertEqual(raised.exception.code, 2)

    def test_missing_assembly_fails_politely(self) -> None:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = cli.main(["build"], handlers=None)
        self.assertEqual(code, 2)
        self.assertIn("application assembly missing", stderr.getvalue())

    def test_version_flag_uses_the_injected_version(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            with self.assertRaises(SystemExit) as raised:
                cli.main(["--version"], handlers=None, version="9.8.7")
        self.assertEqual(raised.exception.code, 0)
        self.assertIn("ByggLeaf 9.8.7", stdout.getvalue())

    def test_console_uses_ansi_when_enabled(self) -> None:
        stream = io.StringIO()
        console = cli.Console(stream, colour=True)
        console.heading("build")
        console.success("done")
        output = stream.getvalue()
        self.assertIn(cli.FOREST_GREEN, output)
        self.assertIn(cli.TERRACOTTA, output)
        self.assertIn(cli.RESET, output)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
