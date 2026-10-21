"""Structural HTML and accessibility checks for generated pages."""

from __future__ import annotations

import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

from byggleaf.core import scaffold
from byggleaf.core.builder import Builder
from byggleaf.core.config import load_config


class _Document(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, dict[str, str]]] = []
        self.ids: list[str] = []
        self.title_parts: list[str] = []
        self._in_title = False

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        attributes = {key: value or "" for key, value in attrs}
        self.tags.append((tag.lower(), attributes))
        if "id" in attributes:
            self.ids.append(attributes["id"])
        if tag.lower() == "title":
            self._in_title = True

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)


class HtmlQualityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        scaffold.init_site(self.root)
        config = self.root / "byggleaf.toml"
        text = config.read_text(encoding="utf-8")
        text = text.replace("posts_per_page = 5", "posts_per_page = 1")
        config.write_text(text, encoding="utf-8")
        (self.root / "content/posts/second.md").write_text(
            "+++\ntitle = \"Second\"\ndate = 2025-02-01\n+++\n\nSecond body.\n",
            encoding="utf-8",
        )
        Builder(self.root, load_config(config)).build()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_every_page_has_core_seo_and_accessibility_structure(self) -> None:
        pages = sorted((self.root / "public").rglob("*.html"))
        self.assertGreaterEqual(len(pages), 5)
        for path in pages:
            with self.subTest(page=path.relative_to(self.root)):
                document = _Document()
                document.feed(path.read_text(encoding="utf-8"))
                tags = [tag for tag, _ in document.tags]
                attrs_by_tag = {tag: attrs for tag, attrs in document.tags}

                self.assertIn("html", tags)
                self.assertTrue(attrs_by_tag["html"].get("lang"))
                self.assertTrue("".join(document.title_parts).strip())
                self.assertEqual(tags.count("h1"), 1)
                self.assertEqual(len(document.ids), len(set(document.ids)))
                self.assertIn("main", tags)
                self.assertEqual(attrs_by_tag["main"].get("id"), "main")
                self.assertNotIn("script", tags)

                meta = {
                    attrs.get("name") or attrs.get("property"): attrs.get("content")
                    for tag, attrs in document.tags
                    if tag == "meta"
                }

                links = [attrs for tag, attrs in document.tags if tag == "link"]
                rels = {attrs.get("rel") for attrs in links}

                if path.name == "404.html":
                    # Error pages are neither indexed nor shared.
                    self.assertIsNone(meta.get("description"))
                    self.assertIsNone(meta.get("og:title"))
                    self.assertIsNone(meta.get("og:description"))
                    self.assertIsNone(meta.get("og:url"))
                    self.assertIsNone(meta.get("og:type"))
                    self.assertNotIn("canonical", rels)
                else:
                    self.assertTrue(meta.get("description"))
                    self.assertTrue(meta.get("og:title"))
                    self.assertTrue(meta.get("og:description"))
                    self.assertTrue(meta.get("og:url"))
                    self.assertTrue(meta.get("og:type"))
                    self.assertIn("canonical", rels)

                self.assertIn("alternate", rels)
                self.assertIn("sitemap", rels)

                for tag, attrs in document.tags:
                    if tag == "img":
                        self.assertIn("alt", attrs)

                nav = [
                    attrs
                    for tag, attrs in document.tags
                    if tag == "nav" and "site-nav" in attrs.get("class", "")
                ]
                self.assertEqual(len(nav), 1)
                self.assertTrue(nav[0].get("aria-label"))

    def test_error_page_keeps_chrome_without_seo_metadata(self) -> None:
        page = self.root / "public/404.html"
        document = _Document()
        document.feed(page.read_text(encoding="utf-8"))
        tags = [tag for tag, _ in document.tags]
        attrs_by_tag = {tag: attrs for tag, attrs in document.tags}

        self.assertTrue("".join(document.title_parts).strip())
        self.assertEqual(tags.count("h1"), 1)
        self.assertIn("main", tags)
        self.assertTrue(attrs_by_tag["html"].get("lang"))

        meta = {
            attrs.get("name") or attrs.get("property"): attrs.get("content")
            for tag, attrs in document.tags
            if tag == "meta"
        }
        for key in ("description", "og:title", "og:description", "og:url", "og:type"):
            self.assertIsNone(meta.get(key))

        rels = {
            attrs.get("rel") for tag, attrs in document.tags if tag == "link"
        }
        self.assertNotIn("canonical", rels)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
