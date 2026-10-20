"""Configuration parsing and validation."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from byggleaf.core.config import (
    ConfigError,
    absolute_url,
    load_config,
)

CONFIG = """\
[site]
title = "A Garden"
hero_subtitle = "Notes and leaves."
baseurl = "https://example.com/garden/"
copyright = "A. Person"
language = "zh-CN"
posts_per_page = 3

[[projects]]
name = "Lemovind"
url = "https://github.com/example/lemovind"
description = "Dynamic blog in Rust."

[[projects]]
name = "ByggLeaf"
url = "https://example.com/byggleaf"
"""


class ConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def write(self, text: str, name: str = "byggleaf.toml") -> Path:
        path = self.root / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_loads_and_normalises_values(self) -> None:
        config = load_config(self.write(CONFIG))
        self.assertEqual(config.site.title, "A Garden")
        self.assertEqual(config.site.hero_subtitle, "Notes and leaves.")
        self.assertEqual(config.site.baseurl, "https://example.com/garden")
        self.assertEqual(config.site.copyright, "A. Person")
        self.assertEqual(config.site.language, "zh-CN")
        self.assertEqual(config.site.posts_per_page, 3)
        self.assertEqual([project.name for project in config.projects], ["Lemovind", "ByggLeaf"])
        self.assertEqual(config.projects[1].description, "")

    def test_default_posts_per_page_is_five(self) -> None:
        config = load_config(
            self.write(CONFIG.replace("posts_per_page = 3\n", ""))
        )
        self.assertEqual(config.site.posts_per_page, 5)

    def test_posts_per_page_must_be_a_positive_integer(self) -> None:
        for value in ("0", "-1", '"5"', "true"):
            with self.subTest(value=value):
                config = CONFIG.replace(
                    "posts_per_page = 3", f"posts_per_page = {value}"
                )
                with self.assertRaisesRegex(ConfigError, "posts_per_page"):
                    load_config(self.write(config))

    def test_url_joining(self) -> None:
        config = load_config(self.write(CONFIG))
        self.assertEqual(
            config.site.url("/assets/css/style.css"),
            "https://example.com/garden/assets/css/style.css",
        )
        self.assertEqual(config.site.url("posts/"), "https://example.com/garden/posts/")

    def test_empty_baseurl_is_root_relative(self) -> None:
        config = load_config(self.write(CONFIG.replace("https://example.com/garden/", "")))
        self.assertEqual(config.site.baseurl, "")
        self.assertEqual(config.site.url("/assets/x.css"), "/assets/x.css")

    def test_absolute_url_accepts_relative_paths(self) -> None:
        self.assertEqual(absolute_url("https://example.com", "x"), "https://example.com/x")
        self.assertEqual(absolute_url("", "/x"), "/x")
        self.assertEqual(absolute_url("https://example.com/", ""), "https://example.com/")

    def test_missing_file_is_a_config_error(self) -> None:
        with self.assertRaisesRegex(ConfigError, "not found"):
            load_config(self.root / "missing.toml")

    def test_site_table_is_required(self) -> None:
        with self.assertRaisesRegex(ConfigError, r"\[site\]"):
            load_config(self.write('title = "Wrong place"\n'))

    def test_baseurl_is_required_even_when_empty(self) -> None:
        with self.assertRaisesRegex(ConfigError, "baseurl"):
            load_config(self.write('[site]\ntitle = "Garden"\n'))

    def test_title_must_be_a_string(self) -> None:
        with self.assertRaisesRegex(ConfigError, "title must be a string"):
            load_config(
                self.write('[site]\ntitle = 42\nbaseurl = ""\n')
            )

    def test_baseurl_rejects_whitespace(self) -> None:
        with self.assertRaisesRegex(ConfigError, "whitespace"):
            load_config(
                self.write('[site]\ntitle = "Garden"\nbaseurl = "https://example.com/a b"\n')
            )

    def test_baseurl_rejects_executable_schemes(self) -> None:
        for baseurl in (
            "javascript:alert(1)",
            "VBScript:x",
            "data:text/html,<svg>",
            "data:image/svg+xml,<svg>",
        ):
            with self.subTest(baseurl=baseurl):
                with self.assertRaisesRegex(ConfigError, "executable"):
                    load_config(
                        self.write(
                            '[site]\ntitle = "Garden"\n'
                            f'baseurl = "{baseurl}"\n'
                        )
                    )

    def test_project_url_rejects_executable_schemes(self) -> None:
        config = CONFIG.replace(
            "https://github.com/example/lemovind", "javascript:alert(1)"
        )
        with self.assertRaisesRegex(ConfigError, "executable"):
            load_config(self.write(config))

    def test_ordinary_project_url_schemes_are_accepted(self) -> None:
        config = load_config(
            self.write(CONFIG.replace("https://example.com/byggleaf", "mailto:a@example.com"))
        )
        self.assertEqual(config.projects[1].url, "mailto:a@example.com")

    def test_language_is_canonicalized(self) -> None:
        config = load_config(
            self.write(CONFIG.replace('language = "zh-CN"', 'language = "zh-hk"'))
        )
        self.assertEqual(config.site.language, "zh-HK")

    def test_invalid_language_tag_is_a_config_error(self) -> None:
        for language in ("zh_CN", "chinese", "zh-CN-"):
            with self.subTest(language=language):
                config = CONFIG.replace(
                    'language = "zh-CN"', f'language = "{language}"'
                )
                with self.assertRaisesRegex(ConfigError, "language"):
                    load_config(self.write(config))

    def test_project_requires_name(self) -> None:
        with self.assertRaisesRegex(ConfigError, "name"):
            load_config(
                self.write(
                    '[site]\ntitle = "Garden"\nbaseurl = ""\n'
                    '[[projects]]\nurl = "https://example.com"\n'
                )
            )

    def test_invalid_toml_is_reported(self) -> None:
        with self.assertRaisesRegex(ConfigError, "invalid TOML"):
            load_config(self.write("[site\n"))

    def test_invalid_utf8_is_a_config_error(self) -> None:
        path = self.root / "byggleaf.toml"
        path.write_bytes(b"\xff\xfe[site]\n")
        with self.assertRaisesRegex(ConfigError, "cannot read"):
            load_config(path)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
