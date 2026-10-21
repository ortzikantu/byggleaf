"""Template engine guards."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from byggleaf.core.config import Config, Site
from byggleaf.core.jinja import TemplateEngine, TemplateError, format_date
from byggleaf.core.locales import load_locale


def _engine() -> TemplateEngine:
    return TemplateEngine(
        Config(site=Site(title="Garden", baseurl="")), load_locale("en")
    )


class JinjaTests(unittest.TestCase):
    def test_format_date_falls_back_to_str(self) -> None:
        self.assertEqual(format_date("not a date"), "not a date")

    def test_missing_templates_directory_is_reported(self) -> None:
        with mock.patch(
            "byggleaf.core.jinja.TEMPLATES_DIR", Path("/nonexistent/templates")
        ):
            with self.assertRaisesRegex(TemplateError, "templates directory"):
                _engine()

    def test_unknown_template_is_reported(self) -> None:
        with self.assertRaisesRegex(TemplateError, "failed"):
            _engine().render("missing.html")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
