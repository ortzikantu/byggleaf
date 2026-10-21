"""Language tag canonicalisation and exact translation lookup."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from byggleaf.core.locales import (
    LOCALES_DIR,
    LocaleError,
    canonicalize_language,
    load_locale,
)


class LocaleTests(unittest.TestCase):
    def test_canonicalizes_bcp47_casing(self) -> None:
        self.assertEqual(canonicalize_language("zh-cn"), "zh-CN")
        self.assertEqual(canonicalize_language("zh-hk"), "zh-HK")
        self.assertEqual(canonicalize_language("en-us"), "en-US")
        self.assertEqual(canonicalize_language("ja-jp"), "ja-JP")
        self.assertEqual(canonicalize_language("ko-kr"), "ko-KR")

    def test_rejects_non_bcp47_tags(self) -> None:
        for tag in ("", "zh_CN", "chinese", "zh-CN-", "zh--CN", "zh-CN-x"):
            with self.subTest(tag=tag):
                with self.assertRaises(LocaleError):
                    canonicalize_language(tag)

    def test_all_builtin_catalogs_load(self) -> None:
        locale_files = sorted(LOCALES_DIR.glob("*.toml"))
        self.assertTrue(locale_files)
        for path in locale_files:
            with self.subTest(language=path.stem):
                locale = load_locale(path.stem)
                self.assertEqual(locale.language, path.stem)
                self.assertIsInstance(locale.strings, dict)

    def test_builtin_catalogs_share_the_same_key_set(self) -> None:
        catalogs = {
            path.stem: set(load_locale(path.stem).strings)
            for path in sorted(LOCALES_DIR.glob("*.toml"))
        }
        reference = catalogs["en"]
        for language, keys in catalogs.items():
            with self.subTest(language=language):
                self.assertEqual(keys, reference)

    def test_missing_catalog_reports_available_files_and_contribution_hint(self) -> None:
        existing = {path.stem for path in LOCALES_DIR.glob("*.toml")}
        tag = next(
            candidate
            for candidate in ("zz", "zz-ZZ", "en-US", "zh-SG")
            if candidate not in existing
        )
        with self.assertRaises(LocaleError) as raised:
            load_locale(tag)
        message = str(raised.exception)
        self.assertIn("no translation file", message)
        self.assertIn("available:", message)
        self.assertIn("contribute a translation", message)

    def test_formatting(self) -> None:
        locale = load_locale("en")
        self.assertEqual(
            locale.text("page_of", current=2, total=3),
            "Page 2 of 3",
        )
        self.assertEqual(
            locale.text("colophon", version="v0.1.0"),
            "Built with ByggLeaf v0.1.0. No JavaScript or tracking added by ByggLeaf.",
        )

    def test_missing_key_displays_the_key_name(self) -> None:
        locale = load_locale("en")
        self.assertEqual(locale.text("not_a_real_key"), "not_a_real_key")

    def test_partial_catalog_is_allowed_and_falls_back_to_key_names(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            locales_dir = Path(directory)
            (locales_dir / "xx.toml").write_text(
                '[ui]\nhome = "Home"\nempty = ""\n', encoding="utf-8"
            )
            with mock.patch("byggleaf.core.locales.LOCALES_DIR", locales_dir):
                locale = load_locale("xx")
                self.assertEqual(locale.text("home"), "Home")
                self.assertEqual(locale.text("about"), "about")
                self.assertEqual(locale.text("empty"), "empty")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
