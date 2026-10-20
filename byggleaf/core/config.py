"""TOML configuration: parse once, validate once, then pass immutable values.

ByggLeaf uses :mod:`tomllib` from the standard library, so configuration does
not add a dependency.  The rest of the application only ever sees frozen
dataclasses; templates cannot mutate site settings by accident.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .locales import LocaleError, canonicalize_language

CONFIG_FILENAME = "byggleaf.toml"

# URL schemes that can execute or smuggle code.  The Markdown sanitizer keeps
# the same list for content; config-owned URLs (baseurl, project links) must
# not become a back door into the zero-JavaScript promise.
_UNSAFE_URL_PREFIXES = (
    "javascript:",
    "vbscript:",
    "data:text/html",
    "data:image/svg",
)
_URL_NOISE_RE = re.compile(r"[\x00-\x20]+")


def _unsafe_url(value: str) -> bool:
    """True when a URL would execute code once a browser resolves it."""

    compact = _URL_NOISE_RE.sub("", value).lower()
    return compact.startswith(_UNSAFE_URL_PREFIXES)


class ConfigError(ValueError):
    """A configuration file is absent, unreadable, or semantically invalid."""


def absolute_url(baseurl: str, path: str) -> str:
    """Join a site-relative path onto ``baseurl``.

    ``baseurl`` may be a full origin (``https://example.com``), a subdirectory
    (``https://example.com/garden``), or an empty string for local root-relative
    previews.  The returned value is always an absolute *path* from the web
    server's point of view, or a fully qualified URL when a base URL is set.
    """

    if not path:
        path = "/"
    if not path.startswith("/"):
        path = "/" + path
    return baseurl.rstrip("/") + path


@dataclass(frozen=True, slots=True)
class Project:
    """One entry in the home page's project list."""

    name: str
    url: str
    description: str = ""


@dataclass(frozen=True, slots=True)
class Site:
    """Site-wide presentation values shared by every template."""

    title: str
    baseurl: str
    hero_subtitle: str = ""
    copyright: str = ""
    language: str = "en"
    posts_per_page: int = 5

    def url(self, path: str) -> str:
        """Turn a site path into the absolute URL used by templates."""

        return absolute_url(self.baseurl, path)


@dataclass(frozen=True, slots=True)
class Config:
    """The complete, validated configuration surface."""

    site: Site
    projects: tuple[Project, ...] = ()


def _string(
    table: dict[str, Any],
    key: str,
    *,
    where: str,
    required: bool = False,
    allow_empty: bool = False,
) -> str:
    value = table.get(key)
    if value is None:
        if required:
            raise ConfigError(f"{where}.{key} is required")
        return ""
    if not isinstance(value, str):
        raise ConfigError(f"{where}.{key} must be a string")
    if required and not allow_empty and not value.strip():
        raise ConfigError(f"{where}.{key} must not be empty")
    return value.strip()


def load_config(path: Path) -> Config:
    """Read and validate ``byggleaf.toml``.

    The error messages name both the file and the offending key.  A static site
    generator should not make its user guess which line of TOML was wrong.
    """

    path = Path(path)

    try:
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError as exc:
        raise ConfigError(
            f"{path.name} not found; run `byggleaf init` to create a workspace"
        ) from exc
    except (OSError, UnicodeError) as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc

    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path.name}: invalid TOML: {exc}") from exc

    site_table = data.get("site")
    if not isinstance(site_table, dict):
        raise ConfigError(f"{path.name}: [site] table is required")

    title = _string(site_table, "title", where="[site]", required=True)
    # An empty baseurl is valid and useful: it produces root-relative links for
    # local previews.  Missing baseurl is still a configuration mistake.
    if "baseurl" not in site_table:
        raise ConfigError("[site].baseurl is required (it may be an empty string)")
    baseurl = _string(
        site_table, "baseurl", where="[site]", required=True, allow_empty=True
    )
    if any(character.isspace() for character in baseurl):
        raise ConfigError("[site].baseurl must not contain whitespace")
    if _unsafe_url(baseurl):
        raise ConfigError("[site].baseurl must not be an executable URL scheme")
    # Normalise once.  No template or caller has to think about trailing slashes.
    if baseurl == "/":
        baseurl = ""
    else:
        baseurl = baseurl.rstrip("/")

    hero_subtitle = _string(site_table, "hero_subtitle", where="[site]")
    copyright_text = _string(site_table, "copyright", where="[site]")
    raw_language = _string(site_table, "language", where="[site]") or "en"
    try:
        language = canonicalize_language(raw_language)
    except LocaleError as exc:
        raise ConfigError(f"[site].language: {exc}") from exc

    raw_posts_per_page = site_table.get("posts_per_page", 5)
    if (
        isinstance(raw_posts_per_page, bool)
        or not isinstance(raw_posts_per_page, int)
        or raw_posts_per_page < 1
    ):
        raise ConfigError("[site].posts_per_page must be a positive integer")
    posts_per_page = raw_posts_per_page

    raw_projects = data.get("projects", [])
    if not isinstance(raw_projects, list):
        raise ConfigError(f"{path.name}: [[projects]] must be an array of tables")

    projects: list[Project] = []
    for index, item in enumerate(raw_projects, start=1):
        if not isinstance(item, dict):
            raise ConfigError(f"{path.name}: projects[{index}] must be a table")
        name = _string(
            item, "name", where=f"projects[{index}]", required=True
        )
        url = _string(item, "url", where=f"projects[{index}]", required=True)
        if _unsafe_url(url):
            raise ConfigError(
                f"{path.name}: projects[{index}].url must not be an "
                "executable URL scheme"
            )
        description = _string(item, "description", where=f"projects[{index}]")
        projects.append(Project(name=name, url=url, description=description))

    site = Site(
        title=title,
        baseurl=baseurl,
        hero_subtitle=hero_subtitle,
        copyright=copyright_text,
        language=language,
        posts_per_page=posts_per_page,
    )
    return Config(site=site, projects=tuple(projects))
