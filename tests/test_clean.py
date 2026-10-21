"""clean 只删 public/，不动其外的东西。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from byggleaf.core.clean import CleanError, CleanResult, clean_output


class CleanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_missing_public_is_idempotent(self) -> None:
        result = clean_output(self.root)
        self.assertIsInstance(result, CleanResult)
        self.assertFalse(result.removed)
        self.assertEqual(result.kind, "missing")

    def test_removes_public_recursively_and_keeps_siblings(self) -> None:
        public = self.root / "public"
        (public / "posts/hello").mkdir(parents=True)
        (public / "posts/hello/index.html").write_text("old", encoding="utf-8")
        config = self.root / "byggleaf.toml"
        config.write_text("[site]\n", encoding="utf-8")

        result = clean_output(self.root)

        self.assertTrue(result.removed)
        self.assertEqual(result.kind, "directory")
        self.assertFalse(public.exists())
        self.assertTrue(config.exists())

    def test_symlink_is_unlinked_not_followed(self) -> None:
        outside = self.root / "outside"
        outside.mkdir()
        marker = outside / "keep.txt"
        marker.write_text("do not delete", encoding="utf-8")
        public = self.root / "public"
        public.symlink_to(outside, target_is_directory=True)

        result = clean_output(self.root)

        self.assertTrue(result.removed)
        self.assertEqual(result.kind, "symlink")
        self.assertFalse(public.exists())
        self.assertEqual(marker.read_text(encoding="utf-8"), "do not delete")

    def test_regular_file_named_public_is_removed(self) -> None:
        public = self.root / "public"
        public.write_text("not a directory", encoding="utf-8")
        result = clean_output(self.root)
        self.assertTrue(result.removed)
        self.assertEqual(result.kind, "file")
        self.assertFalse(public.exists())

    def test_mount_point_is_refused(self) -> None:
        public = self.root / "public"
        public.mkdir()
        with mock.patch("byggleaf.core.clean.os.path.ismount", return_value=True):
            with self.assertRaisesRegex(CleanError, "mount point"):
                clean_output(self.root)
        self.assertTrue(public.is_dir())

    def test_removal_error_is_reported(self) -> None:
        (self.root / "public").mkdir()
        with mock.patch(
            "byggleaf.core.clean.shutil.rmtree", side_effect=OSError("denied")
        ):
            with self.assertRaisesRegex(CleanError, "cannot remove"):
                clean_output(self.root)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
