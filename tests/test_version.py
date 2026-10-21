"""版本从项目自己的 pyproject 解析，或按回退链解析。"""

from __future__ import annotations

import tempfile
import tomllib
import unittest
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from unittest import mock

from byggleaf.core.version import (
    VERSION,
    _installed_version,
    _source_version,
    get_version,
    raw_version,
    reset_cache,
)

ROOT = Path(__file__).resolve().parents[1]


class VersionTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_cache()

    def tearDown(self) -> None:
        reset_cache()

    def test_raw_version_matches_pyproject_and_get_version_prefixes_v(self) -> None:
        expected = tomllib.loads(
            (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )["project"]["version"]
        self.assertEqual(raw_version(), expected)
        self.assertEqual(get_version(), f"v{expected}")
        self.assertEqual(VERSION, f"v{expected}")

    def test_source_version_walks_up_and_ignores_foreign_pyprojects(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "nested" / "garden"
            project.mkdir(parents=True)
            (root / "pyproject.toml").write_text(
                '[project]\nname = "someone-else"\nversion = "9.9.9"\n',
                encoding="utf-8",
            )
            (project / "pyproject.toml").write_text(
                '[project]\nname = "byggleaf"\nversion = "1.2.3"\n',
                encoding="utf-8",
            )
            self.assertEqual(_source_version(start=project), "1.2.3")
            self.assertEqual(_source_version(start=root), "")

    def test_installed_version_is_used_when_there_is_no_source(self) -> None:
        with mock.patch(
            "byggleaf.core.version._source_version", return_value=""
        ), mock.patch(
            "byggleaf.core.version._installed_version", return_value="1.2.3"
        ):
            self.assertEqual(raw_version(), "1.2.3")

    def test_fallback_is_the_placeholder_when_everything_is_missing(self) -> None:
        with mock.patch(
            "byggleaf.core.version._source_version", return_value=""
        ), mock.patch(
            "byggleaf.core.version._installed_version", return_value=""
        ):
            self.assertEqual(raw_version(), "0.0.0")

    def test_source_version_survives_a_hostile_ancestor_pyproject(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "garden"
            project.mkdir()
            (project / "pyproject.toml").write_text(
                '[project]\nname = "byggleaf"\nversion = "1.2.3"\n',
                encoding="utf-8",
            )
            with mock.patch(
                "byggleaf.core.version.tomllib.load",
                side_effect=RuntimeError("pathological pyproject"),
            ):
                self.assertEqual(_source_version(start=project), "")

    def test_installed_version_reads_real_metadata(self) -> None:
        # 可编辑安装在当前环境里暴露了分发元数据。
        self.assertRegex(_installed_version(), r"^\d")

    def test_installed_version_falls_back_when_missing(self) -> None:
        with mock.patch(
            "importlib.metadata.version", side_effect=PackageNotFoundError
        ):
            self.assertEqual(_installed_version(), "")

    def test_installed_version_survives_corrupt_metadata(self) -> None:
        with mock.patch(
            "importlib.metadata.version", side_effect=RuntimeError("broken")
        ):
            self.assertEqual(_installed_version(), "")

    def test_source_version_skips_empty_versions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pyproject.toml").write_text(
                '[project]\nname = "byggleaf"\nversion = ""\n',
                encoding="utf-8",
            )
            self.assertEqual(_source_version(start=root), "")

    def test_reset_cache_forces_a_fresh_resolution(self) -> None:
        with mock.patch(
            "byggleaf.core.version._source_version", return_value="first"
        ):
            self.assertEqual(raw_version(), "first")
        with mock.patch(
            "byggleaf.core.version._source_version", return_value="second"
        ):
            self.assertEqual(raw_version(), "first")  # still cached
            reset_cache()
            self.assertEqual(raw_version(), "second")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
