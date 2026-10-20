"""The version has exactly one source: pyproject.toml."""

from __future__ import annotations

import tempfile
import tomllib
import unittest
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from unittest import mock

from byggleaf.core.version import VERSION, _read_pyproject_version, get_version

ROOT = Path(__file__).resolve().parents[1]


class VersionTests(unittest.TestCase):
    def test_version_matches_pyproject(self) -> None:
        project = tomllib.loads(
            (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )
        expected = project["project"]["version"]
        self.assertEqual(VERSION, expected)
        self.assertEqual(get_version(), expected)

    def test_version_is_a_non_empty_string(self) -> None:
        self.assertIsInstance(VERSION, str)
        self.assertTrue(VERSION.strip())

    def test_pyproject_without_project_table_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pyproject.toml"
            path.write_text("[tool.ruff]\nline-length = 100\n", encoding="utf-8")
            self.assertIsNone(_read_pyproject_version(path))

    def test_pyproject_with_a_foreign_name_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pyproject.toml"
            path.write_text(
                '[project]\nname = "other-package"\nversion = "9.9.9"\n',
                encoding="utf-8",
            )
            self.assertIsNone(_read_pyproject_version(path))

    def test_pyproject_without_a_version_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pyproject.toml"
            path.write_text('[project]\nname = "byggleaf"\n', encoding="utf-8")
            self.assertIsNone(_read_pyproject_version(path))

    def test_pyproject_with_an_empty_version_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pyproject.toml"
            path.write_text(
                '[project]\nname = "byggleaf"\nversion = ""\n',
                encoding="utf-8",
            )
            self.assertIsNone(_read_pyproject_version(path))

    def test_unreadable_pyproject_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            # A directory cannot be read as a text file.
            self.assertIsNone(_read_pyproject_version(Path(directory)))

    def test_distribution_metadata_is_the_wheel_fallback(self) -> None:
        get_version.cache_clear()
        try:
            with mock.patch(
                "byggleaf.core.version._SOURCE_PYPROJECT",
                Path("/nonexistent/byggleaf/pyproject.toml"),
            ):
                with mock.patch(
                    "byggleaf.core.version.distribution_version",
                    return_value="1.2.3",
                ):
                    self.assertEqual(get_version(), "1.2.3")
        finally:
            get_version.cache_clear()

    def test_missing_distribution_falls_back_to_a_placeholder(self) -> None:
        get_version.cache_clear()
        try:
            with mock.patch(
                "byggleaf.core.version._SOURCE_PYPROJECT",
                Path("/nonexistent/byggleaf/pyproject.toml"),
            ):
                with mock.patch(
                    "byggleaf.core.version.distribution_version",
                    side_effect=PackageNotFoundError,
                ):
                    self.assertEqual(get_version(), "0.0.0")
        finally:
            get_version.cache_clear()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
