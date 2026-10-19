"""HTTP smoke test: serve a built site and follow pagination like a browser."""

from __future__ import annotations

import re
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path
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


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
