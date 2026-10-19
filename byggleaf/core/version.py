"""The single source of truth for ByggLeaf's version.

In a source checkout (and in an editable install) the version is read directly
from ``pyproject.toml`` with :mod:`tomllib`.  A wheel does not ship the
project's pyproject file, so the generated distribution metadata is used as a
fallback; that metadata is itself produced from the same pyproject version.

Keeping this in ``core`` means the CLI, templates and package root can all
consume one value without duplicating a literal version string.
"""

from __future__ import annotations

import tomllib
from functools import lru_cache
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as distribution_version
from pathlib import Path

PACKAGE_NAME = "byggleaf"
_FALLBACK_VERSION = "0.0.0"

# A source checkout is exactly two levels above core/version.py.
_SOURCE_PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def _read_pyproject_version(path: Path) -> str | None:
    """Return ``[project].version`` for ByggLeaf, or None if not applicable."""

    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError):
        return None

    project = data.get("project")
    if not isinstance(project, dict) or project.get("name") != PACKAGE_NAME:
        return None
    value = project.get("version")
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


@lru_cache(maxsize=1)
def get_version() -> str:
    """Resolve the version once, preferring the source pyproject file."""

    if _SOURCE_PYPROJECT.is_file():
        source_version = _read_pyproject_version(_SOURCE_PYPROJECT)
        if source_version is not None:
            return source_version

    try:
        return distribution_version(PACKAGE_NAME)
    except PackageNotFoundError:
        # A source tree without installation metadata is still usable; an
        # explicit fallback keeps rendering from failing over a cosmetic value.
        return _FALLBACK_VERSION


VERSION = get_version()

__all__ = ["VERSION", "get_version"]
