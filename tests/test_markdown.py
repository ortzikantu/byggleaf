"""Markdown、front matter、baseurl 重写与页面标题行为。"""

from __future__ import annotations

import datetime as dt
import tempfile
import unittest
from pathlib import Path
from xml.etree.ElementTree import Element

from byggleaf.core.markdown import (
    MarkdownError,
    _BaseurlTreeprocessor,
    extract_leading_heading,
    parse_post,
    render_markdown,
    render_page,
    summarize_html,
)

POST = """\
+++
title = "Hello, World"
date = 2025-02-03
+++
# Hello, World

This is the *first* paragraph with a [link](/somewhere).

## A heading

More text.
"""


class MarkdownTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def write(self, text: str, name: str = "post.md") -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_toml_front_matter_and_duplicate_heading_removal(self) -> None:
        post = parse_post(self.write(POST))
        self.assertEqual(post.title, "Hello, World")
        self.assertEqual(post.date, dt.date(2025, 2, 3))
        self.assertIn("<em>first</em>", post.html)
        self.assertNotIn("<h1>Hello, World</h1>", post.html)
        self.assertEqual(
            post.summary,
            "This is the first paragraph with a link.",
        )
        self.assertEqual(post.url, "/posts/post/")

    def test_yaml_compatibility_front_matter(self) -> None:
        path = self.write(
            "---\n"
            'title: "A YAML Post"\n'
            "date: 2024-12-31\n"
            "---\n"
            "\n"
            "Body.\n"
        )
        post = parse_post(path)
        self.assertEqual(post.title, "A YAML Post")
        self.assertEqual(post.date, dt.date(2024, 12, 31))

    def test_optional_metadata_and_datetime(self) -> None:
        path = self.write(
            "+++\n"
            'title = "Extended"\n'
            "date = 2026-10-18T14:30:45\n"
            "updated = 2026-10-19T09:15:00\n"
            'author = "Ada Lovelace"\n'
            'tags = ["python", "notes"]\n'
            "+++\n"
            "\n"
            "First paragraph.\n"
        )
        post = parse_post(path)
        self.assertEqual(post.date, dt.datetime(2026, 10, 18, 14, 30, 45))
        self.assertEqual(post.updated, dt.datetime(2026, 10, 19, 9, 15))
        self.assertEqual(post.author, "Ada Lovelace")
        self.assertEqual(post.tags, ("python", "notes"))
        self.assertEqual(post.summary, "First paragraph.")

    def test_single_tag_string_is_supported(self) -> None:
        path = self.write(
            "+++\n"
            'title = "Tagged"\n'
            "date = 2026-01-01\n"
            'tag = "one, two"\n'
            "+++\n"
            "\n"
            "Body.\n"
        )
        post = parse_post(path)
        self.assertEqual(post.tags, ("one", "two"))

    def test_mixed_date_and_datetime_are_sortable(self) -> None:
        day = parse_post(
            self.write(
                "+++\ntitle = \"Day\"\ndate = 2026-01-01\n+++\n\nBody.\n",
                name="day.md",
            )
        )
        moment = parse_post(
            self.write(
                "+++\ntitle = \"Moment\"\ndate = 2026-01-01T12:00:00\n+++\n\nBody.\n",
                name="moment.md",
            )
        )
        self.assertGreater(moment.published_timestamp, day.published_timestamp)

    def test_missing_title_is_rejected(self) -> None:
        path = self.write("+++\ndate = 2025-01-01\n+++\nBody\n")
        with self.assertRaisesRegex(MarkdownError, "title"):
            parse_post(path)

    def test_missing_date_is_rejected(self) -> None:
        path = self.write('+++\ntitle = "No date"\n+++\nBody\n')
        with self.assertRaisesRegex(MarkdownError, "date"):
            parse_post(path)

    def test_bad_date_is_rejected(self) -> None:
        path = self.write('+++\ntitle = "Bad date"\ndate = "not-a-date"\n+++\nBody\n')
        with self.assertRaisesRegex(MarkdownError, "invalid date"):
            parse_post(path)

    def test_unterminated_front_matter_is_rejected(self) -> None:
        path = self.write('+++\ntitle = "Broken"\n')
        with self.assertRaisesRegex(MarkdownError, "unterminated"):
            parse_post(path)

    def test_invalid_utf8_is_a_markdown_error(self) -> None:
        path = self.root / "bad.md"
        path.write_bytes(b"\xff\xfe+++\n")
        with self.assertRaisesRegex(MarkdownError, "cannot read"):
            parse_post(path)

    def test_raw_html_is_passed_through_unchanged(self) -> None:
        # ByggLeaf 不过滤作者写入的原始 HTML：输出就是
        # Markdown 渲染器产出的内容。
        fragment = render_markdown(
            "<script>alert(1)</script>\n\n"
            '<img src="x" onerror="alert(2)">\n\n'
            "[bad](javascript:alert(3))\n\n"
            "Plain paragraph.\n"
        )
        self.assertIn("<script>alert(1)</script>", fragment)
        self.assertIn('onerror="alert(2)"', fragment)
        self.assertIn('href="javascript:alert(3)"', fragment)
        self.assertIn("Plain paragraph.", fragment)

    def test_leading_heading_extraction(self) -> None:
        title, body = extract_leading_heading("\n\n# Team\n\nWe build things.\n")
        self.assertEqual(title, "Team")
        self.assertTrue(body.startswith("We build things."))

    def test_leading_heading_is_optional(self) -> None:
        title, body = extract_leading_heading("Just text.\n")
        self.assertIsNone(title)
        self.assertEqual(body, "Just text.\n")

    def test_nested_page_route_and_no_duplicate_title(self) -> None:
        path = self.write("# Team\n\nWe build things.\n", "content/about/team/index.md")
        page = render_page(path, route="about/team")
        self.assertEqual(page.title, "Team")
        self.assertEqual(page.route, "about/team")
        self.assertEqual(page.url, "/about/team/")
        self.assertNotIn("<h1>", page.html)
        self.assertIn("We build things.", page.html)
        self.assertEqual(page.summary, "We build things.")

    def test_utf8_bom_does_not_defeat_the_page_title(self) -> None:
        path = self.write("# About Me\n\nText.\n", "index.md")
        path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
        page = render_page(path, route="about")
        self.assertEqual(page.title, "About Me")
        self.assertNotIn("\ufeff", page.html)

    def test_summary_is_shortened_on_a_boundary(self) -> None:
        source = " ".join(["word"] * 100)
        fragment = render_markdown(source)
        summary = summarize_html(fragment, limit=40)
        self.assertLessEqual(len(summary), 41)
        self.assertTrue(summary.endswith("…"))

    def test_markdown_fenced_code_and_tables_survive(self) -> None:
        fragment = render_markdown(
            "```python\nprint('hi')\n```\n\n"
            "| A | B |\n| - | - |\n| 1 | 2 |\n"
        )
        self.assertIn('<code class="language-python">', fragment)
        self.assertIn("<table>", fragment)

    def test_local_markdown_urls_use_baseurl(self) -> None:
        fragment = render_markdown(
            "![leaf](assets/img/leaf.jpg)\n\n"
            "[root link](/posts/)\n\n"
            "[relative link](../elsewhere/)\n\n"
            "[external](https://example.org/x)\n\n"
            "[anchor](#top)\n",
            baseurl="https://example.com/garden",
        )
        self.assertIn(
            'src="https://example.com/garden/assets/img/leaf.jpg"', fragment
        )
        self.assertIn('href="https://example.com/garden/posts/"', fragment)
        self.assertIn('href="../elsewhere/"', fragment)
        self.assertIn('href="https://example.org/x"', fragment)
        self.assertIn('href="#top"', fragment)


class BaseurlUrlTests(unittest.TestCase):
    """本地 URL 跟随 baseurl；其他 URL 保持原样。"""

    def test_subpath_baseurl_rewrites_root_relative_links_and_assets(self) -> None:
        fragment = render_markdown(
            "[root link](/posts/)\n\n"
            "![leaf](assets/img/leaf.jpg)\n\n"
            "[asset](/assets/img/leaf.jpg)\n",
            baseurl="https://example.com/garden",
        )
        self.assertIn('href="https://example.com/garden/posts/"', fragment)
        self.assertIn(
            'src="https://example.com/garden/assets/img/leaf.jpg"', fragment
        )
        self.assertIn(
            'href="https://example.com/garden/assets/img/leaf.jpg"', fragment
        )

    def test_external_and_non_local_urls_are_left_alone(self) -> None:
        fragment = render_markdown(
            "[external](https://example.org/x)\n\n"
            "[mail](mailto:a@example.org)\n\n"
            "[cdn](//cdn.example.org/y)\n\n"
            "[anchor](#top)\n\n"
            "[query](?q=1)\n\n"
            "[relative](../elsewhere/)\n",
            baseurl="https://example.com/garden",
        )
        self.assertIn('href="https://example.org/x"', fragment)
        self.assertIn('href="mailto:a@example.org"', fragment)
        self.assertIn('href="//cdn.example.org/y"', fragment)
        self.assertIn('href="#top"', fragment)
        self.assertIn('href="?q=1"', fragment)
        self.assertIn('href="../elsewhere/"', fragment)

    def test_empty_baseurl_keeps_local_urls_root_relative(self) -> None:
        fragment = render_markdown("[root](/posts/)\n\n![leaf](assets/x.jpg)\n")
        self.assertIn('href="/posts/"', fragment)
        self.assertIn('src="/assets/x.jpg"', fragment)


class FrontMatterErrorTests(unittest.TestCase):
    """front matter 校验错误应明确且可操作。"""

    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def write(self, text: str, name: str = "post.md") -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_post_without_front_matter_is_rejected(self) -> None:
        with self.assertRaisesRegex(MarkdownError, "title"):
            parse_post(self.write("Just a body.\n"))

    def test_invalid_toml_front_matter_is_rejected(self) -> None:
        with self.assertRaisesRegex(MarkdownError, "invalid TOML"):
            parse_post(self.write("+++\nthis is not toml\n+++\n\nBody.\n"))

    def test_yaml_front_matter_skips_blank_and_comment_lines(self) -> None:
        post = parse_post(
            self.write(
                "---\n"
                "# a comment\n"
                "\n"
                'title: "YAML Post"\n'
                "date: 2024-12-31\n"
                "---\n\nBody.\n"
            )
        )
        self.assertEqual(post.title, "YAML Post")

    def test_yaml_front_matter_lines_are_taken_as_written(self) -> None:
        """``---`` 块只做机械切分，格式错了也不拦构建。"""

        post = parse_post(
            self.write(
                '---\ntitle: "X"\ndate: 2024-01-01\nbroken\n: value\n'
                'quote: "unterminated\ncalc: "a" + "b"\n---\n\nBody.\n'
            )
        )
        self.assertEqual(post.title, "X")
        self.assertEqual(post.meta["broken"], "")
        self.assertEqual(post.meta[""], "value")
        self.assertEqual(post.meta["quote"], '"unterminated')
        self.assertEqual(post.meta["calc"], '"a" + "b"')

    def test_empty_date_is_rejected(self) -> None:
        with self.assertRaisesRegex(MarkdownError, "invalid date"):
            parse_post(self.write('+++\ntitle = "X"\ndate = ""\n+++\n\nBody.\n'))

    def test_quoted_datetime_string_is_parsed(self) -> None:
        post = parse_post(
            self.write(
                '+++\ntitle = "X"\ndate = "2026-10-18T14:30:45"\n+++\n\nBody.\n'
            )
        )
        self.assertEqual(post.date, dt.datetime(2026, 10, 18, 14, 30, 45))

    def test_non_date_value_is_rejected(self) -> None:
        with self.assertRaisesRegex(MarkdownError, "date or date-time"):
            parse_post(self.write('+++\ntitle = "X"\ndate = 123\n+++\n\nBody.\n'))

    def test_non_string_author_is_ignored(self) -> None:
        post = parse_post(
            self.write('+++\ntitle = "X"\ndate = 2024-01-01\nauthor = 5\n+++\n\nBody.\n')
        )
        self.assertEqual(post.author, "")

    def test_non_string_tags_entries_are_dropped(self) -> None:
        post = parse_post(
            self.write(
                '+++\ntitle = "X"\ndate = 2024-01-01\ntags = ["a", 1, "b"]\n+++\n\nBody.\n'
            )
        )
        self.assertEqual(post.tags, ("a", "b"))

    def test_non_list_tags_become_empty(self) -> None:
        post = parse_post(
            self.write('+++\ntitle = "X"\ndate = 2024-01-01\ntags = 5\n+++\n\nBody.\n')
        )
        self.assertEqual(post.tags, ())

    def test_unparseable_updated_is_ignored(self) -> None:
        post = parse_post(
            self.write(
                '+++\ntitle = "X"\ndate = 2024-01-01\nupdated = "someday"\n+++\n\nBody.\n'
            )
        )
        self.assertIsNone(post.updated)

    def test_draft_is_read_from_toml(self) -> None:
        post = parse_post(
            self.write('+++\ntitle = "X"\ndate = 2024-01-01\ndraft = true\n+++\n\nBody.\n')
        )
        self.assertTrue(post.draft)

    def test_draft_string_false_is_not_a_draft(self) -> None:
        post = parse_post(
            self.write('---\ntitle: "X"\ndate: 2024-01-01\ndraft: false\n---\n\nBody.\n')
        )
        self.assertFalse(post.draft)

    def test_unknown_keys_stay_available_in_meta(self) -> None:
        post = parse_post(
            self.write(
                '+++\ntitle = "X"\ndate = 2024-01-01\ncover = "leaf.png"\n+++\n\nBody.\n'
            )
        )
        self.assertEqual(post.meta["cover"], "leaf.png")
        self.assertEqual(post.meta["title"], "X")

    def test_timezone_aware_dates_sort_in_utc(self) -> None:
        post = parse_post(
            self.write(
                '+++\ntitle = "TZ"\ndate = "2026-01-01T00:00:00+08:00"\n+++\n\nBody.\n'
            )
        )
        self.assertEqual(post.published_timestamp, dt.datetime(2025, 12, 31, 16, 0))

    def test_post_with_bom_is_parsed(self) -> None:
        path = self.write(POST)
        path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
        self.assertEqual(parse_post(path).title, "Hello, World")

    def test_unreadable_page_is_a_markdown_error(self) -> None:
        path = self.root / "page.md"
        path.write_bytes(b"\xff\xfe# Broken\n")
        with self.assertRaisesRegex(MarkdownError, "cannot read"):
            render_page(path, route="x")

    def test_treeprocessor_skips_non_string_tags(self) -> None:
        root = Element("div")
        root.append(Element(1))  # comment-like tag, never a real element
        processor = _BaseurlTreeprocessor("https://example.com")
        self.assertIs(processor.run(root), root)


class SummaryTests(unittest.TestCase):
    def test_summary_without_spaces_is_truncated(self) -> None:
        fragment = render_markdown("啊" * 300)
        summary = summarize_html(fragment, limit=20)
        self.assertEqual(len(summary), 21)
        self.assertTrue(summary.endswith("…"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
