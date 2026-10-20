"""Markdown, front matter, sanitisation, and page title behaviour."""

from __future__ import annotations

import datetime as dt
import tempfile
import unittest
from pathlib import Path

from byggleaf.core.markdown import (
    MarkdownError,
    extract_leading_heading,
    parse_post,
    render_markdown,
    render_page,
    sanitize_html,
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

    def test_raw_html_cannot_smuggle_javascript_into_output(self) -> None:
        fragment = render_markdown(
            "Before <link rel=\"stylesheet\" href=\"evil.css\"> after.\n\n"
            "<script>alert(1)</script>\n\n"
            '<img src="x" onerror="alert(2)">\n\n'
            "[bad](javascript:alert(3))\n\n"
            "<style>body { display: none }</style>\n\n"
            "Still visible.\n"
        )
        lowered = fragment.lower()
        self.assertIn("after.", lowered)
        self.assertIn("still visible.", lowered)
        self.assertNotIn("<script", lowered)
        self.assertNotIn("<style", lowered)
        self.assertNotIn("<link", lowered)
        self.assertNotIn("onerror", lowered)
        self.assertNotIn("javascript:", lowered)

    def test_blocked_void_tag_does_not_swallow_rest_of_document(self) -> None:
        fragment = render_markdown('One <meta name="x" content="y"> two.')
        self.assertIn("One", fragment)
        self.assertIn("two.", fragment)
        self.assertNotIn("<meta", fragment)

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


class SanitizerEdgeCaseTests(unittest.TestCase):
    """Boundary behaviour of the HTML guard rail that keeps output JS-free."""

    def test_nested_blocked_tags_do_not_leak_interior_text(self) -> None:
        # form is not a CDATA (raw text) element, so the nested start tag
        # reaches the sanitizer on every supported Python version.
        fragment = sanitize_html(
            "<form><form>x</form>LEAK</form> after."
        )
        lowered = fragment.lower()
        self.assertNotIn("<form", lowered)
        self.assertNotIn("leak", lowered)
        self.assertIn("after.", lowered)

    def test_nested_script_is_consumed_as_raw_text_like_browsers(self) -> None:
        # HTMLParser treats <script> as raw text, so the nested tag is part of
        # the data and everything up to the first </script> is dropped.  The
        # trailing "LEAK" is plain escaped text, exactly as a browser renders
        # it; no <script> element survives.
        fragment = sanitize_html("<script><script>alert(1)</script>LEAK</script>")
        lowered = fragment.lower()
        self.assertNotIn("<script", lowered)
        self.assertNotIn("alert(1)", lowered)
        self.assertIn("leak", lowered)

    def test_mixed_nested_blocked_tags_are_dropped_entirely(self) -> None:
        fragment = sanitize_html(
            "<style><script>x</script>body { display: none }</style>\n\nAfter.\n"
        )
        lowered = fragment.lower()
        self.assertNotIn("<style", lowered)
        self.assertNotIn("<script", lowered)
        self.assertNotIn("display: none", lowered)
        self.assertIn("after.", lowered)

    def test_mismatched_end_tags_do_not_end_skip_mode_early(self) -> None:
        fragment = sanitize_html("<form>x</button>LEAK</form> tail.")
        lowered = fragment.lower()
        self.assertNotIn("leak", lowered)
        self.assertIn("tail.", lowered)

    def test_obfuscated_javascript_urls_are_dropped(self) -> None:
        for payload in (
            "java\nscript:alert(1)",
            "java\tscript:alert(1)",
            "JaVaScRiPt:alert(1)",
            "vbscript:msgbox(1)",
            "data:text/html,<script>",
            "data:image/svg+xml,<svg>",
        ):
            with self.subTest(payload=payload):
                fragment = sanitize_html(f'<a href="{payload}">x</a>')
                self.assertNotIn("href", fragment.lower())
                self.assertIn(">x</a>", fragment)

    def test_character_reference_javascript_urls_are_dropped(self) -> None:
        fragment = sanitize_html('<a href="java&#10;script:alert(1)">x</a>')
        self.assertNotIn("href", fragment.lower())

    def test_spaced_javascript_urls_are_dropped(self) -> None:
        fragment = sanitize_html('<a href="ja va  script:alert(1)">x</a>')
        self.assertNotIn("href", fragment.lower())

    def test_event_handler_attributes_are_dropped_in_any_case(self) -> None:
        fragment = sanitize_html(
            '<img src="/x.png" onerror="alert(1)" ONCLICK="alert(2)">'
        )
        lowered = fragment.lower()
        self.assertIn('src="/x.png"', lowered)
        self.assertNotIn("onerror", lowered)
        self.assertNotIn("onclick", lowered)

    def test_inline_style_attribute_is_dropped_but_tag_survives(self) -> None:
        fragment = sanitize_html('<p style="color:red">text</p>')
        self.assertIn("<p>text</p>", fragment)
        self.assertNotIn("style=", fragment)

    def test_iframe_with_fallback_content_is_dropped(self) -> None:
        fragment = sanitize_html(
            '<iframe src="https://x">fallback text</iframe> after.'
        )
        lowered = fragment.lower()
        self.assertNotIn("<iframe", lowered)
        self.assertNotIn("fallback text", lowered)
        self.assertIn("after.", lowered)

    def test_attribute_ampersands_are_escaped(self) -> None:
        fragment = sanitize_html('<a href="https://x/?a=1&b=2">x</a>')
        self.assertIn('href="https://x/?a=1&amp;b=2"', fragment)

    def test_integration_through_markdown_keeps_promise(self) -> None:
        fragment = render_markdown(
            "<form><form>x</form>LEAK</form>\n\n"
            '<a href="java\tscript:alert(2)">x</a>\n\n'
            "Plain paragraph.\n"
        )
        lowered = fragment.lower()
        self.assertNotIn("<form", lowered)
        self.assertNotIn("leak", lowered)
        self.assertNotIn("href", lowered)
        self.assertIn("plain paragraph.", lowered)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
