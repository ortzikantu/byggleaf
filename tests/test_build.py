"""End-to-end tests for scaffold, build routing, and generated HTML."""

from __future__ import annotations

import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from byggleaf.core import scaffold
from byggleaf.core.builder import Builder, BuildError
from byggleaf.core.config import load_config
from byggleaf.core.scaffold import ScaffoldError
from byggleaf.core.version import VERSION

ROOT = Path(__file__).resolve().parents[1]


class ScaffoldTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_init_creates_the_complete_workspace(self) -> None:
        result = scaffold.init_site(self.root)
        for relative in (
            "byggleaf.toml",
            "content/posts/hello-world.md",
            "content/about/index.md",
            "content/statement/index.md",
            "assets/img/favicon.ico",
            "assets/img",
            "assets/video",
            "assets/audio",
        ):
            with self.subTest(path=relative):
                self.assertTrue((self.root / relative).exists())
        self.assertGreater((self.root / "assets/img/favicon.ico").stat().st_size, 0)
        self.assertTrue(result.favicon_copied)
        self.assertEqual(len(result.created), 5)

    def test_second_init_refuses_to_clobber_without_force(self) -> None:
        scaffold.init_site(self.root)
        with self.assertRaisesRegex(ScaffoldError, "already exists"):
            scaffold.init_site(self.root)

    def test_force_restores_generated_files(self) -> None:
        scaffold.init_site(self.root)
        config = self.root / "byggleaf.toml"
        config.write_text("# damaged\n", encoding="utf-8")
        scaffold.init_site(self.root, force=True)
        self.assertIn("[site]", config.read_text(encoding="utf-8"))

    def test_existing_user_files_are_kept_without_force(self) -> None:
        scaffold.init_site(self.root)
        (self.root / "byggleaf.toml").unlink()
        about = self.root / "content/about/index.md"
        about.write_text("# Mine\n\nDo not touch.\n", encoding="utf-8")
        result = scaffold.init_site(self.root)
        self.assertEqual(about.read_text(encoding="utf-8"), "# Mine\n\nDo not touch.\n")
        self.assertIn(about, result.skipped)


class BuildTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        scaffold.init_site(self.root)
        self.set_language("en")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def set_language(self, language: str) -> None:
        config_path = self.root / "byggleaf.toml"
        text = config_path.read_text(encoding="utf-8")
        config_path.write_text(
            re.sub(
                r'language = "[^"]*"',
                f'language = "{language}"',
                text,
                count=1,
            ),
            encoding="utf-8",
        )

    def build(self) -> object:
        config = load_config(self.root / "byggleaf.toml")
        return Builder(self.root, config).build()

    def read(self, relative: str) -> str:
        return (self.root / "public" / relative).read_text(encoding="utf-8")

    def back_link(self, slug: str) -> str:
        post = self.read(f"posts/{slug}/index.html")
        match = re.search(
            r'<nav class="post-footer-nav"[^>]*>\s*<a href="([^"]+)"',
            post,
        )
        self.assertIsNotNone(match)
        return match.group(1)

    def write_post(self, name: str, title: str, date: str, body: str = "Body.") -> None:
        path = self.root / "content" / "posts" / name
        path.write_text(
            f'+++\ntitle = "{title}"\ndate = {date}\n+++\n\n{body}\n',
            encoding="utf-8",
        )

    def set_posts_per_page(self, count: int) -> None:
        config_path = self.root / "byggleaf.toml"
        config_path.write_text(
            config_path.read_text(encoding="utf-8").replace(
                "posts_per_page = 5", f"posts_per_page = {count}"
            ),
            encoding="utf-8",
        )

    def test_builds_home_posts_pages_and_assets(self) -> None:
        result = self.build()
        self.assertEqual(result.posts, 1)
        self.assertEqual(result.pages, 2)
        self.assertEqual(result.favicon, "/assets/img/favicon.ico")

        for relative in (
            "index.html",
            "posts/hello-world/index.html",
            "about/index.html",
            "statement/index.html",
            "assets/css/style.css",
            "assets/img/favicon.ico",
            "sitemap.xml",
            "rss.xml",
        ):
            with self.subTest(path=relative):
                self.assertTrue((self.root / "public" / relative).is_file())

        self.assertFalse((self.root / "public/posts/index.html").exists())

        home = self.read("index.html")
        self.assertIn(
            'href="https://example.com/assets/css/style.css"', home
        )
        self.assertIn(
            f'<meta name="generator" content="ByggLeaf {VERSION}">', home
        )
        self.assertIn(
            f"Built with ByggLeaf {VERSION}. No JavaScript, no tracking.", home
        )
        self.assertIn('href="https://example.com/about/"', home)
        self.assertNotIn(">Posts</a>", home)
        self.assertIn("Lemovind", home)
        self.assertIn("Hello, World", home)
        self.assertNotIn("https://example.com/statement/", home)
        self.assertNotIn("<script", home.lower())
        self.assertIn(
            '<link rel="canonical" href="https://example.com/">', home
        )
        self.assertIn('<meta property="og:type" content="website">', home)
        self.assertIn(
            '<meta property="og:url" content="https://example.com/">', home
        )
        self.assertIn('href="https://example.com/rss.xml"', home)
        self.assertIn('href="https://example.com/sitemap.xml"', home)

        post = self.read("posts/hello-world/index.html")
        self.assertEqual(post.count("<h1"), 1)
        self.assertIn('<time datetime="2025-01-01">2025-01-01</time>', post)
        self.assertEqual(self.back_link("hello-world"), "https://example.com/")

        about = self.read("about/index.html")
        self.assertIn('<h1 class="page-title">About</h1>', about)
        self.assertNotIn("<h1>About</h1>", about)
        self.assertIn(
            '<link rel="canonical" href="https://example.com/about/">', about
        )
        self.assertIn('<meta property="og:type" content="article">', about)
        self.assertIn(
            '<meta name="description" content="This is an independent page.',
            about,
        )

        sitemap = self.read("sitemap.xml")
        self.assertIn("<urlset", sitemap)
        self.assertIn(
            "<loc>https://example.com/about/</loc>", sitemap
        )
        self.assertIn(
            "<loc>https://example.com/posts/hello-world/</loc>", sitemap
        )

        rss = self.read("rss.xml")
        self.assertIn("<rss version=\"2.0\"", rss)
        self.assertIn("<language>en</language>", rss)
        self.assertIn("<title>Hello, World</title>", rss)
        self.assertIn(
            "<link>https://example.com/posts/hello-world/</link>", rss
        )

    def test_pagination_uses_configured_page_size(self) -> None:
        for title, date in (
            ("April", "2026-04-01"),
            ("March", "2026-03-01"),
            ("February", "2026-02-01"),
            ("January", "2026-01-01"),
        ):
            self.write_post(f"{title.lower()}.md", title, date)
        self.set_posts_per_page(2)
        result = self.build()

        self.assertEqual(result.posts, 5)
        self.assertTrue((self.root / "public/page/2/index.html").is_file())
        self.assertTrue((self.root / "public/page/3/index.html").is_file())
        self.assertFalse((self.root / "public/posts/index.html").exists())

        first = self.read("index.html")
        second = self.read("page/2/index.html")
        third = self.read("page/3/index.html")

        self.assertIn("April", first)
        self.assertIn("March", first)
        self.assertNotIn("February", first)
        self.assertIn('href="https://example.com/page/2/" rel="next"', first)
        self.assertNotIn('rel="prev"', first)

        self.assertIn("February", second)
        self.assertIn("January", second)
        self.assertNotIn("April", second)
        self.assertIn('href="https://example.com/" rel="prev"', second)
        self.assertIn('href="https://example.com/page/3/" rel="next"', second)
        self.assertNotIn("Lemovind", second)

        self.assertIn("Hello, World", third)
        self.assertIn('href="https://example.com/page/2/" rel="prev"', third)
        self.assertNotIn('rel="next"', third)

        self.assertEqual(self.back_link("april"), "https://example.com/")
        self.assertEqual(self.back_link("february"), "https://example.com/page/2/")
        self.assertEqual(self.back_link("hello-world"), "https://example.com/page/3/")

        sitemap = self.read("sitemap.xml")
        self.assertIn(
            "<loc>https://example.com/page/2/</loc>", sitemap
        )
        self.assertIn(
            "<loc>https://example.com/page/3/</loc>", sitemap
        )

    def test_post_seo_uses_summary_author_and_tags(self) -> None:
        seo = self.root / "content/posts/seo.md"
        seo.write_text(
            "+++\n"
            'title = "SEO Post"\n'
            "date = 2026-05-01T10:30:00\n"
            "updated = 2026-05-02T11:00:00\n"
            'author = "Ada Lovelace"\n'
            'tags = ["python", "byggleaf"]\n'
            "+++\n"
            "\n"
            "First paragraph for SEO.\n"
            "\n"
            "Second paragraph.\n",
            encoding="utf-8",
        )
        self.build()

        home = self.read("index.html")
        summary = re.search(
            r'<p class="post-summary">(.*?)</p>', home, re.DOTALL
        )
        self.assertIsNotNone(summary)
        self.assertEqual(summary.group(1), "First paragraph for SEO.")

        post = self.read("posts/seo/index.html")
        self.assertIn(
            '<meta name="description" content="First paragraph for SEO.">', post
        )
        self.assertIn('<meta name="author" content="Ada Lovelace">', post)
        self.assertIn(
            '<meta name="keywords" content="python, byggleaf">', post
        )
        self.assertIn(
            '<link rel="canonical" href="https://example.com/posts/seo/">', post
        )
        self.assertIn(
            '<meta property="og:description" content="First paragraph for SEO.">',
            post,
        )
        self.assertIn(
            '<meta property="article:published_time" content="2026-05-01T10:30:00">',
            post,
        )
        self.assertIn(
            '<meta property="article:modified_time" content="2026-05-02T11:00:00">',
            post,
        )
        self.assertIn(
            '<meta property="article:author" content="Ada Lovelace">', post
        )
        self.assertIn('<meta property="article:tag" content="python">', post)
        self.assertIn('<meta property="article:tag" content="byggleaf">', post)
        self.assertIn('<span class="post-author">Ada Lovelace</span>', post)
        self.assertIn("2026-05-01 10:30", post)
        self.assertIn("2026-05-02 11:00", post)

        rss = self.read("rss.xml")
        self.assertIn("<dc:creator>Ada Lovelace</dc:creator>", rss)
        self.assertIn("<category>python</category>", rss)
        self.assertIn("<category>byggleaf</category>", rss)
        self.assertIn(
            "<description>First paragraph for SEO.</description>", rss
        )

        sitemap = self.read("sitemap.xml")
        self.assertIn(
            "<lastmod>2026-05-02T11:00:00</lastmod>", sitemap
        )

        plain = self.read("posts/hello-world/index.html")
        self.assertNotIn('class="post-author"', plain)
        self.assertNotIn('class="post-updated"', plain)

    def test_navbar_has_home_and_about_only(self) -> None:
        self.build()
        home = self.read("index.html")
        nav = re.search(
            r'<nav class="site-nav".*?</nav>', home, re.DOTALL
        )
        self.assertIsNotNone(nav)
        labels = re.findall(r">([^<>]+)</a>", nav.group(0))
        self.assertEqual(labels, ["Home", "About"])
        self.assertNotIn("Posts", nav.group(0))

    def test_language_localizes_generated_ui(self) -> None:
        self.set_language("zh-CN")
        self.build()

        home = self.read("index.html")
        self.assertIn('<html lang="zh-CN">', home)
        self.assertIn(">首页</a>", home)
        self.assertIn(">关于</a>", home)
        self.assertIn("跳到正文", home)
        self.assertIn("写作", home)
        self.assertIn("项目", home)
        self.assertIn(f"由 ByggLeaf {VERSION} 生成", home)

        post = self.read("posts/hello-world/index.html")
        self.assertIn("← 全部文章", post)
        self.assertIn('aria-label="文章导航"', post)

    def test_traditional_chinese_language(self) -> None:
        self.set_language("zh-HK")
        self.build()

        home = self.read("index.html")
        self.assertIn('<html lang="zh-HK">', home)
        self.assertIn(">首頁</a>", home)
        self.assertIn(">關於</a>", home)
        self.assertIn("寫作", home)
        self.assertIn("產生", home)

    def test_posts_render_newest_first(self) -> None:
        self.write_post("newest.md", "Newest", "2026-03-01")
        self.write_post("oldest.md", "Oldest", "2020-01-01")
        self.build()
        home = self.read("index.html")
        self.assertLess(home.index("Newest"), home.index("Hello, World"))
        self.assertLess(home.index("Hello, World"), home.index("Oldest"))

    def test_missing_favicon_omits_the_link(self) -> None:
        (self.root / "assets/img/favicon.ico").unlink()
        result = self.build()
        self.assertIsNone(result.favicon)
        self.assertNotIn('rel="icon"', self.read("index.html"))
        self.assertFalse((self.root / "public/assets/img/favicon.ico").exists())

    def test_empty_baseurl_produces_root_relative_links(self) -> None:
        config_path = self.root / "byggleaf.toml"
        config_path.write_text(
            config_path.read_text(encoding="utf-8").replace(
                'baseurl = "https://example.com"', 'baseurl = ""'
            ),
            encoding="utf-8",
        )
        self.build()
        home = self.read("index.html")
        self.assertIn('href="/assets/css/style.css"', home)
        self.assertIn('href="/posts/hello-world/"', home)
        self.assertEqual(self.back_link("hello-world"), "/")

    def test_stale_output_is_removed(self) -> None:
        stale = self.root / "public/stale.html"
        stale.parent.mkdir(parents=True, exist_ok=True)
        stale.write_text("old", encoding="utf-8")
        self.build()
        self.assertFalse(stale.exists())

    def test_user_assets_are_copied_and_counted(self) -> None:
        photo = self.root / "assets/img/photo.jpg"
        photo.write_bytes(b"not really a jpeg")
        result = self.build()
        self.assertEqual(result.assets, 3)  # stylesheet + favicon + photo
        self.assertEqual(
            (self.root / "public/assets/img/photo.jpg").read_bytes(),
            b"not really a jpeg",
        )

    def test_stylesheet_is_copied_byte_for_byte(self) -> None:
        self.build()
        self.assertEqual(
            (self.root / "public/assets/css/style.css").read_bytes(),
            (ROOT / "byggleaf/assets/css/style.css").read_bytes(),
        )

    def test_hidden_page_is_not_added_to_navigation(self) -> None:
        self.build()
        statement = self.read("statement/index.html")
        nav = re.search(
            r'<nav class="site-nav".*?</nav>', statement, re.DOTALL
        )
        self.assertIsNotNone(nav)
        self.assertNotIn("statement", nav.group(0))
        self.assertIn("https://example.com/about/", nav.group(0))

    def test_custom_page_without_h1_gets_a_humanized_title(self) -> None:
        page = self.root / "content/notes/index.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text("No heading here, just a page.\n", encoding="utf-8")
        self.build()
        output = self.read("notes/index.html")
        self.assertIn('<h1 class="page-title">Notes</h1>', output)

    def test_script_in_markdown_is_removed_from_every_output(self) -> None:
        self.write_post(
            "unsafe.md",
            "Unsafe",
            "2026-01-01",
            '<script>alert("x")</script>\n\n'
            '[click](javascript:alert(1))\n\n'
            '<img src="x" onerror="alert(2)">\n\n'
            "Safe text.\n",
        )
        self.build()
        for path in (self.root / "public").rglob("*.html"):
            lowered = path.read_text(encoding="utf-8").lower()
            with self.subTest(path=path.name):
                self.assertNotIn("<script", lowered)
                self.assertNotIn("javascript:", lowered)
                self.assertNotIn("onerror", lowered)

    def test_markdown_asset_urls_are_built_with_baseurl(self) -> None:
        self.write_post(
            "with-image.md",
            "With Image",
            "2026-02-02",
            "![A leaf](assets/img/leaf.jpg)\n\n[About](/about/)\n",
        )
        self.build()
        post = self.read("posts/with-image/index.html")
        self.assertIn(
            'src="https://example.com/assets/img/leaf.jpg"', post
        )
        self.assertIn('href="https://example.com/about/"', post)

    def test_missing_content_directory_is_a_build_error(self) -> None:
        (self.root / "content").rename(self.root / "content-away")
        with self.assertRaisesRegex(BuildError, "content"):
            self.build()

    def test_failed_build_keeps_the_previous_public_tree(self) -> None:
        self.build()
        previous_home = self.read("index.html")
        broken = self.root / "content/posts/broken.md"
        broken.write_text(
            '+++\ntitle = "Broken"\n+++\n\nMissing a date.\n',
            encoding="utf-8",
        )

        with self.assertRaisesRegex(BuildError, "date"):
            self.build()

        self.assertEqual(self.read("index.html"), previous_home)
        self.assertFalse((self.root / "public/posts/broken/index.html").exists())
        self.assertEqual(list(self.root.glob(".byggleaf-build-*")), [])
        self.assertEqual(list(self.root.glob(".byggleaf-public-*")), [])

    def test_failed_first_build_publishes_nothing(self) -> None:
        (self.root / "content/posts/broken.md").write_text(
            "+++\ntitle = \"Broken\"\n+++\n", encoding="utf-8"
        )
        with self.assertRaises(BuildError):
            self.build()
        self.assertFalse((self.root / "public").exists())
        self.assertEqual(list(self.root.glob(".byggleaf-build-*")), [])

    def test_output_path_conflict_is_rejected_during_preflight(self) -> None:
        self.write_post("second.md", "Second", "2025-02-01")
        self.set_posts_per_page(1)
        page = self.root / "content/page/2/index.md"
        page.parent.mkdir(parents=True)
        page.write_text("# Conflict\n\nCustom page.\n", encoding="utf-8")

        with self.assertRaisesRegex(BuildError, "output path conflict"):
            self.build()
        self.assertFalse((self.root / "public").exists())

    def test_publication_recovery_restores_backup_and_clears_staging(self) -> None:
        self.build()
        previous_home = self.read("index.html")
        public = self.root / "public"
        backup = self.root / ".byggleaf-public-crashed"
        staging = self.root / ".byggleaf-build-crashed"
        public.rename(backup)
        staging.mkdir()

        builder = Builder(self.root, load_config(self.root / "byggleaf.toml"))
        builder._recover_publication()

        self.assertEqual(self.read("index.html"), previous_home)
        self.assertFalse(backup.exists())
        self.assertFalse(staging.exists())

    def test_publish_failure_restores_the_previous_public_tree(self) -> None:
        self.build()
        previous_home = self.read("index.html")
        real_replace = os.replace
        final = self.root / "public"

        def flaky_replace(source: str | Path, destination: str | Path) -> None:
            if (
                Path(source).name.startswith(".byggleaf-build-")
                and Path(destination) == final
            ):
                raise OSError("simulated publish failure")
            real_replace(source, destination)

        with mock.patch(
            "byggleaf.core.builder.os.replace", side_effect=flaky_replace
        ):
            with self.assertRaisesRegex(BuildError, "simulated publish failure"):
                self.build()

        self.assertEqual(self.read("index.html"), previous_home)
        self.assertEqual(list(self.root.glob(".byggleaf-public-*")), [])
        self.assertEqual(list(self.root.glob(".byggleaf-build-*")), [])

    def test_content_failure_is_caught_before_staging(self) -> None:
        (self.root / "content/posts/broken.md").write_text(
            "+++\ntitle = \"Broken\"\n+++\n", encoding="utf-8"
        )
        with mock.patch(
            "byggleaf.core.builder.tempfile.mkdtemp",
            side_effect=AssertionError("staging must not be created"),
        ) as mkdtemp:
            with self.assertRaisesRegex(BuildError, "date"):
                self.build()
            mkdtemp.assert_not_called()

    def test_successful_rebuild_leaves_no_backup(self) -> None:
        self.build()
        self.build()
        self.assertTrue((self.root / "public/index.html").is_file())
        self.assertEqual(list(self.root.glob(".byggleaf-public-*")), [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
