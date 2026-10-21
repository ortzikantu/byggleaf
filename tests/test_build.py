"""End-to-end tests for scaffold, build routing, and generated HTML."""

from __future__ import annotations

import datetime as dt
import os
import re
import shutil
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

from byggleaf.core import scaffold
from byggleaf.core.builder import Builder, BuildError
from byggleaf.core.config import Config, Site, load_config
from byggleaf.core.scaffold import ScaffoldError
from byggleaf.core.seo import render_rss
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

    def test_root_that_is_a_file_is_rejected(self) -> None:
        target = self.root / "file"
        target.write_text("x", encoding="utf-8")
        with self.assertRaisesRegex(ScaffoldError, "not a directory"):
            scaffold.init_site(target)

    def test_missing_example_config_is_reported(self) -> None:
        with mock.patch(
            "byggleaf.core.scaffold.EXAMPLE_CONFIG", self.root / "missing.toml"
        ):
            with self.assertRaisesRegex(ScaffoldError, "example config"):
                scaffold.init_site(self.root)

    def test_workspace_directory_errors_are_reported(self) -> None:
        with mock.patch("pathlib.Path.mkdir", side_effect=OSError("denied")):
            with self.assertRaisesRegex(ScaffoldError, "workspace directories"):
                scaffold.init_site(self.root)

    def test_favicon_copy_error_is_reported(self) -> None:
        with mock.patch(
            "byggleaf.core.scaffold.shutil.copyfile",
            side_effect=OSError("denied"),
        ):
            with self.assertRaisesRegex(ScaffoldError, "favicon"):
                scaffold.init_site(self.root)

    def test_missing_packaged_favicon_is_tolerated(self) -> None:
        with mock.patch(
            "byggleaf.core.scaffold.DEFAULT_FAVICON", self.root / "none.ico"
        ):
            result = scaffold.init_site(self.root)
        self.assertFalse(result.favicon_copied)
        self.assertFalse((self.root / "assets/img/favicon.ico").exists())


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

    def example_project_name(self) -> str:
        """The first project name shipped in the packaged example config."""

        data = tomllib.loads(
            (ROOT / "byggleaf/resources/config.example.toml").read_text(
                encoding="utf-8"
            )
        )
        return str(data["projects"][0]["name"])

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
            "404.html",
            "posts/hello-world/index.html",
            "about/index.html",
            "statement/index.html",
            "assets/css/style.css",
            "assets/img/favicon.ico",
            "robots.txt",
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
            f"Built with ByggLeaf {VERSION}. No JavaScript or tracking added by ByggLeaf.", home
        )
        self.assertIn('href="https://example.com/about/"', home)
        self.assertNotIn(">Posts</a>", home)
        self.assertIn(self.example_project_name(), home)
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
        self.assertNotIn(self.example_project_name(), second)

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

    def test_robots_txt_points_to_the_sitemap(self) -> None:
        self.build()
        robots = self.read("robots.txt")
        self.assertIn("User-agent: *", robots)
        self.assertIn("Allow: /", robots)
        self.assertIn("Sitemap: https://example.com/sitemap.xml", robots)

    def test_robots_txt_omits_the_sitemap_line_without_baseurl(self) -> None:
        config_path = self.root / "byggleaf.toml"
        config_path.write_text(
            config_path.read_text(encoding="utf-8").replace(
                'baseurl = "https://example.com"', 'baseurl = ""'
            ),
            encoding="utf-8",
        )
        self.build()
        robots = self.read("robots.txt")
        self.assertIn("User-agent: *", robots)
        self.assertNotIn("Sitemap:", robots)

    def test_404_page_is_localized_and_kept_out_of_the_sitemap(self) -> None:
        self.build()
        page = self.read("404.html")
        self.assertIn("Page not found", page)
        self.assertIn("The page you are looking for does not exist.", page)
        self.assertIn('href="https://example.com/"', page)
        self.assertNotIn("404.html", self.read("sitemap.xml"))
        # Error pages are not indexed or shared: no SEO/social metadata.
        self.assertNotIn('rel="canonical"', page)
        self.assertNotIn('<meta name="description"', page)
        self.assertNotIn('property="og:', page)

    def test_404_page_follows_the_site_language(self) -> None:
        self.set_language("zh-CN")
        self.build()
        self.assertIn("页面未找到", self.read("404.html"))

    def test_rss_escapes_special_characters(self) -> None:
        post = self.root / "content/posts/weird.md"
        post.write_text(
            '+++\n'
            'title = "A & B <C> \\"D\\""\n'
            "date = 2026-01-01\n"
            'author = "O\'Reilly & Sons"\n'
            "+++\n\nBody.\n",
            encoding="utf-8",
        )
        self.build()
        rss = self.read("rss.xml")
        self.assertIn(
            "<title>A &amp; B &lt;C&gt; &quot;D&quot;</title>", rss
        )
        self.assertIn(
            "<dc:creator>O'Reilly &amp; Sons</dc:creator>", rss
        )

    def test_non_ascii_slug_is_percent_encoded_in_urls_but_built_on_disk(
        self,
    ) -> None:
        post = self.root / "content/posts/你好.md"
        post.write_text(
            '+++\ntitle = "你好"\ndate = 2026-01-01\n+++\n\nBody.\n',
            encoding="utf-8",
        )
        self.build()
        self.assertTrue(
            (self.root / "public/posts/你好/index.html").is_file()
        )
        home = self.read("index.html")
        self.assertIn(
            'href="https://example.com/posts/%E4%BD%A0%E5%A5%BD/"', home
        )

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

    def test_raw_html_in_markdown_is_preserved_in_generated_pages(self) -> None:
        # Raw HTML written by the author is not filtered by ByggLeaf.
        self.write_post(
            "raw-html.md",
            "Raw HTML",
            "2026-01-01",
            "<script>alert('x')</script>\n\n"
            '[click](javascript:alert(1))\n\n'
            '<img src="x" onerror="alert(2)">\n\n'
            "Visible text.\n",
        )
        self.build()
        post = self.read("posts/raw-html/index.html")
        self.assertIn("<script>alert('x')</script>", post)
        self.assertIn('href="javascript:alert(1)"', post)
        self.assertIn('onerror="alert(2)"', post)
        self.assertIn("Visible text.", post)

    def test_raw_html_local_urls_are_not_rewritten(self) -> None:
        self.write_post(
            "raw-local.md",
            "Raw Local",
            "2026-01-01",
            '<img src="assets/img/raw.jpg">\n\n'
            '<a href="/about/">root</a>\n',
        )
        self.build()
        post = self.read("posts/raw-local/index.html")
        self.assertIn('src="assets/img/raw.jpg"', post)
        self.assertIn('href="/about/"', post)

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

    def test_missing_packaged_stylesheet_is_a_build_error(self) -> None:
        with mock.patch(
            "byggleaf.core.builder.PACKAGE_ASSETS", self.root / "missing"
        ):
            with self.assertRaisesRegex(BuildError, "stylesheet"):
                self.build()

    def test_public_symlink_is_refused(self) -> None:
        outside = self.root / "outside"
        outside.mkdir()
        (self.root / "public").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(BuildError, "symlink"):
            self.build()
        self.assertTrue(outside.is_dir())

    def test_public_path_that_is_not_a_directory_is_refused(self) -> None:
        (self.root / "public").write_text("x", encoding="utf-8")
        with self.assertRaisesRegex(BuildError, "not a directory"):
            self.build()

    def test_recovery_cleans_backup_and_staging_leftovers(self) -> None:
        self.build()
        backup_dir = self.root / ".byggleaf-public-dir"
        backup_file = self.root / ".byggleaf-public-file"
        staging_file = self.root / ".byggleaf-build-file"
        backup_dir.mkdir()
        backup_file.write_text("x", encoding="utf-8")
        staging_file.write_text("x", encoding="utf-8")

        self.build()

        self.assertFalse(backup_dir.exists())
        self.assertFalse(backup_file.exists())
        self.assertFalse(staging_file.exists())

    def test_publish_failure_without_a_previous_site_publishes_nothing(self) -> None:
        final = self.root / "public"
        real_replace = os.replace

        def replace(source: str | Path, destination: str | Path) -> None:
            if (
                Path(source).name.startswith(".byggleaf-build-")
                and Path(destination) == final
            ):
                raise OSError("simulated publish failure")
            real_replace(source, destination)

        with mock.patch("byggleaf.core.builder.os.replace", side_effect=replace):
            with self.assertRaisesRegex(BuildError, "simulated publish failure"):
                self.build()

        self.assertFalse(final.exists())
        self.assertEqual(list(self.root.glob(".byggleaf-build-*")), [])

    def test_publish_restore_failure_is_reported(self) -> None:
        self.build()
        final = self.root / "public"
        real_replace = os.replace

        def replace(source: str | Path, destination: str | Path) -> None:
            source_name = Path(source).name
            if (
                source_name.startswith(".byggleaf-build-")
                and Path(destination) == final
            ):
                raise OSError("publish failed")
            if (
                source_name.startswith(".byggleaf-public-")
                and Path(destination) == final
            ):
                raise OSError("restore failed")
            real_replace(source, destination)

        with mock.patch("byggleaf.core.builder.os.replace", side_effect=replace):
            with self.assertRaisesRegex(BuildError, "could not be restored"):
                self.build()

    def test_publish_refuses_a_non_directory_public(self) -> None:
        builder = Builder(self.root, load_config(self.root / "byggleaf.toml"))
        staging = self.root / ".byggleaf-build-manual"
        staging.mkdir()
        (self.root / "public").write_text("x", encoding="utf-8")

        with self.assertRaisesRegex(BuildError, "not a replaceable directory"):
            builder._publish(staging)

    def test_absent_posts_directory_builds_an_empty_stream(self) -> None:
        shutil.rmtree(self.root / "content/posts")
        result = self.build()
        self.assertEqual(result.posts, 0)
        self.assertIn("Nothing has been planted", self.read("index.html"))

    def test_directory_named_like_a_post_is_skipped(self) -> None:
        (self.root / "content/posts/fake.md").mkdir()
        result = self.build()
        self.assertEqual(result.posts, 1)

    def test_post_filename_with_backslash_is_rejected(self) -> None:
        (self.root / "content/posts/weird\\name.md").write_text(
            '+++\ntitle = "X"\ndate = 2024-01-01\n+++\n\nBody.\n',
            encoding="utf-8",
        )
        with self.assertRaisesRegex(BuildError, "unsafe post filename"):
            self.build()

    def test_content_index_md_does_not_replace_the_home_page(self) -> None:
        (self.root / "content/index.md").write_text("# Home?\n", encoding="utf-8")
        self.build()
        self.assertIn("Hello, World", self.read("index.html"))

    def test_index_md_inside_posts_is_not_a_custom_page(self) -> None:
        page = self.root / "content/posts/notes/index.md"
        page.parent.mkdir()
        page.write_text("# Notes\n", encoding="utf-8")
        self.build()
        self.assertFalse((self.root / "public/posts/notes/index.html").exists())

    def test_missing_user_asset_directory_is_skipped(self) -> None:
        shutil.rmtree(self.root / "assets/video")
        result = self.build()
        self.assertEqual(result.assets, 2)

    def test_directory_named_index_md_is_ignored(self) -> None:
        (self.root / "content/notes/index.md").mkdir(parents=True)
        self.build()
        self.assertFalse((self.root / "public/notes/index.html").exists())

    def test_target_requires_an_active_staging_directory(self) -> None:
        builder = Builder(self.root, load_config(self.root / "byggleaf.toml"))
        with self.assertRaisesRegex(BuildError, "staging"):
            _ = builder._target

    def test_keyboard_interrupt_cleans_staging_and_propagates(self) -> None:
        with mock.patch.object(
            Builder, "_materialize", side_effect=KeyboardInterrupt
        ):
            with self.assertRaises(KeyboardInterrupt):
                self.build()
        self.assertEqual(list(self.root.glob(".byggleaf-build-*")), [])

    def test_rss_handles_timezone_aware_dates(self) -> None:
        self.write_post("tz.md", "TZ", '"2026-01-01T00:00:00+08:00"')
        self.build()
        rss = self.read("rss.xml")
        self.assertIn("<pubDate>Wed, 31 Dec 2025 16:00:00 GMT</pubDate>", rss)

    def test_rss_without_copyright_accepts_a_naive_build_time(self) -> None:
        config = Config(site=Site(title="Garden", baseurl=""))
        rss = render_rss(config, [], build_time=dt.datetime(2026, 1, 1))
        self.assertNotIn("<copyright>", rss)
        self.assertIn(
            "<lastBuildDate>Thu, 01 Jan 2026 00:00:00 GMT</lastBuildDate>",
            rss,
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
