"""The version has exactly one source: pyproject.toml."""

from __future__ import annotations

import tomllib
import unittest
from pathlib import Path

from byggleaf.core.version import VERSION, get_version

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


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
