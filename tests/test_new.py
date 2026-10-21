"""Creating empty articles from the packaged template."""

from __future__ import annotations

import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from byggleaf.core.markdown import parse_post
from byggleaf.core.new import ARTICLE_TEMPLATE, NewError, create_article


class NewArticleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        (self.root / "byggleaf.toml").write_text(
            '[site]\ntitle = "Garden"\nbaseurl = ""\n',
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_packaged_template_is_the_example_article(self) -> None:
        self.assertTrue(ARTICLE_TEMPLATE.is_file())
        self.assertEqual(ARTICLE_TEMPLATE.name, "article.example.md")

    def test_creates_article_with_automatic_datetime_and_empty_metadata(self) -> None:
        published = dt.datetime(2026, 10, 18, 14, 30, 45)
        result = create_article(self.root, now=published)

        self.assertEqual(result.path, self.root / "content/posts/new-article.md")
        text = result.path.read_text(encoding="utf-8")
        self.assertIn('title = "New Article"', text)
        self.assertIn("date = 2026-10-18T14:30:45", text)
        self.assertIn('updated = ""', text)
        self.assertIn('author = ""', text)
        self.assertIn("tags = []", text)

        post = parse_post(result.path)
        self.assertEqual(post.title, "New Article")
        self.assertEqual(post.date, published)
        self.assertIsNone(post.updated)
        self.assertEqual(post.author, "")
        self.assertEqual(post.tags, ())

    def test_repeated_calls_do_not_overwrite(self) -> None:
        first = create_article(self.root)
        second = create_article(self.root)

        self.assertEqual(first.path.name, "new-article.md")
        self.assertEqual(second.path.name, "new-article-2.md")
        self.assertTrue(first.path.is_file())
        self.assertTrue(second.path.is_file())

    def test_requires_an_initialized_workspace(self) -> None:
        (self.root / "byggleaf.toml").unlink()
        with self.assertRaisesRegex(NewError, "byggleaf.toml"):
            create_article(self.root)

    def test_unreadable_template_is_reported(self) -> None:
        with mock.patch(
            "byggleaf.core.new.ARTICLE_TEMPLATE", self.root / "missing.md"
        ):
            with self.assertRaisesRegex(NewError, "cannot read article template"):
                create_article(self.root)

    def test_template_without_placeholder_is_reported(self) -> None:
        template = self.root / "template.md"
        template.write_text("no placeholder here", encoding="utf-8")
        with mock.patch("byggleaf.core.new.ARTICLE_TEMPLATE", template):
            with self.assertRaisesRegex(NewError, "placeholder"):
                create_article(self.root)

    def test_unwritable_posts_directory_is_reported(self) -> None:
        (self.root / "content").mkdir()
        (self.root / "content/posts").write_text("x", encoding="utf-8")
        with self.assertRaisesRegex(NewError, "cannot create article"):
            create_article(self.root)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
