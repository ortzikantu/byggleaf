"""HTTP smoke test: serve a built site and follow pagination like a browser."""

from __future__ import annotations

import http.client
import re
import socket
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path
from unittest import mock
from urllib.parse import urlparse

from byggleaf.core import scaffold
from byggleaf.core.builder import Builder
from byggleaf.core.config import load_config
from byggleaf.core.server import ServerError, make_server, serve


class HttpSmokeTests(unittest.TestCase):
    def test_missing_directory_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "byggleaf-does-not-exist"
            with self.assertRaises(ServerError):
                make_server(missing)
            with self.assertRaises(ServerError):
                serve(missing)

    def test_preview_server_follows_pagination_and_serves_feeds(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scaffold.init_site(root)
            config_path = root / "byggleaf.toml"
            config_path.write_text(
                config_path.read_text(encoding="utf-8").replace(
                    "posts_per_page = 5", "posts_per_page = 1"
                ),
                encoding="utf-8",
            )
            (root / "content/posts/second.md").write_text(
                "+++\ntitle = \"Second\"\ndate = 2025-02-01\n+++\n\nSecond body.\n",
                encoding="utf-8",
            )
            Builder(root, load_config(config_path)).build()

            httpd = make_server(root / "public", host="127.0.0.1", port=0)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{httpd.server_address[1]}"
            try:
                first = urllib.request.urlopen(f"{base}/", timeout=5)
                try:
                    self.assertEqual(first.status, 200)
                    self.assertEqual(first.headers["Cache-Control"], "no-store")
                    html = first.read().decode("utf-8")
                finally:
                    first.close()

                next_match = re.search(
                    r'<a class="pagination-next" href="([^"]+)"', html
                )
                self.assertIsNotNone(next_match)
                next_path = urlparse(next_match.group(1)).path or "/"
                second = urllib.request.urlopen(
                    f"{base}{next_path}", timeout=5
                )
                try:
                    self.assertEqual(second.status, 200)
                    self.assertIn(
                        "Hello, World", second.read().decode("utf-8")
                    )
                finally:
                    second.close()

                for path in ("/rss.xml", "/sitemap.xml"):
                    response = urllib.request.urlopen(f"{base}{path}", timeout=5)
                    try:
                        self.assertEqual(response.status, 200)
                        self.assertTrue(response.read().startswith(b"<?xml"))
                    finally:
                        response.close()
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=5)


class ServerErrorPathTests(unittest.TestCase):
    def test_busy_port_raises_server_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            blocker = socket.socket()
            try:
                blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                blocker.bind(("127.0.0.1", 0))
                blocker.listen(1)
                port = blocker.getsockname()[1]
                with self.assertRaises(ServerError):
                    make_server(Path(directory), host="127.0.0.1", port=port)
            finally:
                blocker.close()


class _StubHttpServer:
    """A stand-in for ThreadingHTTPServer used to test serve()'s URL logic."""

    def __init__(self, host: str, port: int) -> None:
        self.server_address = (host, port)
        self.served = False

    def __enter__(self) -> _StubHttpServer:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def serve_forever(self) -> None:
        self.served = True


class ServeWrapperTests(unittest.TestCase):
    def test_path_traversal_requests_are_confined_to_public(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scaffold.init_site(root)
            Builder(root, load_config(root / "byggleaf.toml")).build()

            httpd = make_server(root / "public", host="127.0.0.1", port=0)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            port = httpd.server_address[1]
            try:
                for path in (
                    "/../../etc/passwd",
                    "/..%2f..%2fetc%2fpasswd",
                    "/%2e%2e/%2e%2e/etc/passwd",
                ):
                    with self.subTest(path=path):
                        connection = http.client.HTTPConnection(
                            "127.0.0.1", port, timeout=5
                        )
                        try:
                            connection.request("GET", path)
                            response = connection.getresponse()
                            self.assertEqual(response.status, 404)
                            body = response.read().decode("utf-8")
                        finally:
                            connection.close()
                        self.assertNotIn("root:", body)
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=5)

    def test_missing_paths_serve_the_built_404_page_with_status_404(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scaffold.init_site(root)
            Builder(root, load_config(root / "byggleaf.toml")).build()

            httpd = make_server(root / "public", host="127.0.0.1", port=0)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            port = httpd.server_address[1]
            try:
                connection = http.client.HTTPConnection(
                    "127.0.0.1", port, timeout=5
                )
                try:
                    connection.request("GET", "/definitely-missing/")
                    response = connection.getresponse()
                    self.assertEqual(response.status, 404)
                    body = response.read().decode("utf-8")
                finally:
                    connection.close()
                # The default scaffold config is zh-CN.
                self.assertIn("页面未找到", body)
                self.assertIn("<html", body)

                with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/robots.txt", timeout=5
                ) as response:
                    self.assertEqual(response.status, 200)
                    self.assertIn(
                        "User-agent: *", response.read().decode("utf-8")
                    )

                with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/404.html", timeout=5
                ) as response:
                    self.assertEqual(response.status, 200)
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=5)

    def test_serve_serves_requests_and_reports_the_bound_url(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text(
                "<p>preview works</p>", encoding="utf-8"
            )
            real = make_server(root, host="127.0.0.1", port=0)
            observed: dict[str, object] = {}

            def on_ready(url: str) -> None:
                observed["url"] = url

                def probe_then_stop() -> None:
                    with urllib.request.urlopen(url, timeout=5) as response:
                        observed["status"] = response.status
                        observed["body"] = response.read().decode("utf-8")
                    real.shutdown()

                threading.Thread(target=probe_then_stop, daemon=True).start()

            with mock.patch(
                "byggleaf.core.server.make_server",
                side_effect=lambda *args, **kwargs: real,
            ):
                serve(root, host="127.0.0.1", port=0, on_ready=on_ready)

            self.assertEqual(
                observed["url"],
                f"http://127.0.0.1:{real.server_address[1]}/",
            )
            self.assertEqual(observed["status"], 200)
            self.assertIn("preview works", str(observed["body"]))

    def test_missing_path_without_a_404_page_uses_the_plain_404(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("<p>only</p>", encoding="utf-8")
            httpd = make_server(root, host="127.0.0.1", port=0)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            port = httpd.server_address[1]
            try:
                connection = http.client.HTTPConnection(
                    "127.0.0.1", port, timeout=5
                )
                try:
                    connection.request("GET", "/missing/")
                    response = connection.getresponse()
                    self.assertEqual(response.status, 404)
                    response.read()
                finally:
                    connection.close()
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=5)

    def test_serve_without_a_ready_callback_still_runs(self) -> None:
        stub = _StubHttpServer("127.0.0.1", 6789)
        with mock.patch(
            "byggleaf.core.server.make_server", side_effect=lambda *a, **k: stub
        ):
            serve(Path("."), host="127.0.0.1", port=6789, on_ready=None)
        self.assertTrue(stub.served)

    def test_wildcard_and_ipv6_hosts_get_a_reachable_display_url(self) -> None:
        cases = (
            ("0.0.0.0", "127.0.0.1"),
            ("::", "127.0.0.1"),
            ("::1", "[::1]"),
            ("127.0.0.1", "127.0.0.1"),
        )
        stubs: list[_StubHttpServer] = []

        def stub_factory(directory, *, host, port):
            stub = _StubHttpServer(host, port)
            stubs.append(stub)
            return stub

        for host, display in cases:
            with self.subTest(host=host):
                seen: list[str] = []
                with mock.patch(
                    "byggleaf.core.server.make_server",
                    side_effect=stub_factory,
                ):
                    serve(Path("."), host=host, port=6789, on_ready=seen.append)
                self.assertEqual(seen, [f"http://{display}:6789/"])

        self.assertEqual(len(stubs), len(cases))
        self.assertTrue(all(stub.served for stub in stubs))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
