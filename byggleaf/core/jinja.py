"""The Jinja2 rendering base.

ByggLeaf has exactly one template set, and it lives inside the installed
package.  There is deliberately no FileSystemLoader pointed at the user's
project: custom HTML templates are not a supported feature.  The user writes
Markdown; the dictator handles typography.

The internal layout is intentionally flat and uses short, direct names:

    base.html      shared page chrome
    home.html      paginated home page
    post.html      one post detail
    page.html      standalone/custom page
    postlist.html  article stream used by the home page
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from jinja2 import (
    Environment,
    FileSystemLoader,
    StrictUndefined,
    select_autoescape,
)
from jinja2 import (
    TemplateError as JinjaTemplateError,
)

from .config import Config, absolute_url
from .locales import Locale
from .version import VERSION

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


class TemplateError(RuntimeError):
    """A packaged template is missing or failed to render."""


def format_date(value: object) -> str:
    """Display dates quietly; include time only when one was provided."""

    if isinstance(value, dt.datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    if isinstance(value, dt.date):
        return value.strftime("%Y-%m-%d")
    return str(value)


class TemplateEngine:
    """Configured Jinja environment plus the URL helper used everywhere."""

    def __init__(self, config: Config, locale: Locale) -> None:
        if not TEMPLATES_DIR.is_dir():
            raise TemplateError(f"packaged templates directory is missing: {TEMPLATES_DIR}")

        self.config = config
        self.locale = locale
        self.environment = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=select_autoescape(enabled_extensions=("html", "xml")),
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
            auto_reload=False,
        )
        # Every URL in every template goes through this function.  That is how
        # the absolute-baseurl rule is kept honest in one place.
        self.environment.globals["url"] = lambda path: absolute_url(
            config.site.baseurl, path
        )
        self.environment.globals["version"] = VERSION
        self.environment.globals["ui"] = locale.text
        self.environment.filters["datefmt"] = format_date

    def render(self, template_name: str, **context: object) -> str:
        """Render a packaged template with the site config pre-bound."""

        context.setdefault("site", self.config.site)
        context.setdefault("projects", self.config.projects)
        try:
            template = self.environment.get_template(template_name)
            return template.render(**context)
        except (JinjaTemplateError, OSError, UnicodeError) as exc:
            raise TemplateError(f"template {template_name!r} failed: {exc}") from exc
