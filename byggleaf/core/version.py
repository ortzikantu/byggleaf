"""The single source of truth for ByggLeaf's version.

``raw_version()`` is the PEP 440 version (``0.1.0``); ``get_version()`` is the
display form (``v0.1.0``) used by the CLI, the generator meta, the RSS feed
and the footer.

Resolution order: a source checkout (including ``pip install -e .``) reads the
project's own ``pyproject.toml``, so a bumped version applies immediately; a
wheel has no readable pyproject and falls back to ``importlib.metadata``; if
both fail the placeholder ``0.0.0`` keeps rendering alive — a cosmetic value
must never break the site.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

#: Distribution name, matching ``[project].name`` in ``pyproject.toml``.
DISTRIBUTION = "byggleaf"
_FALLBACK = "0.0.0"

_cache: str | None = None


def _installed_version() -> str:
    """The installed distribution's version, or "" when unavailable or broken."""

    from importlib.metadata import PackageNotFoundError, version

    try:
        return str(version(DISTRIBUTION) or "").strip()
    except PackageNotFoundError:
        return ""
    except Exception:  # corrupt metadata must not break the site
        return ""


def _source_version(start: Path | None = None) -> str:
    """Walk up from this file to the nearest *ByggLeaf* pyproject.

    Only a pyproject whose ``[project].name`` equals ``DISTRIBUTION`` counts:
    a venv created inside some other project's tree must not donate its
    version number.
    """

    base = (start or Path(__file__).resolve().parent).resolve()
    for candidate in (base, *base.parents):
        pyproject = candidate / "pyproject.toml"
        if not pyproject.is_file():
            continue
        try:
            with pyproject.open("rb") as handle:
                data = tomllib.load(handle)
        except Exception:
            # Foreign, unreadable, or pathological pyproject files in ancestor
            # directories (RecursionError on hostile nesting, broken metadata,
            # ...) must never break the site over a cosmetic value.
            continue
        project = data.get("project") or {}
        if str(project.get("name") or "").strip().lower() != DISTRIBUTION:
            continue
        value = str(project.get("version") or "").strip()
        if value:
            return value
    return ""


def raw_version() -> str:
    """The PEP 440 version, resolved once per process."""

    global _cache
    if _cache is None:
        _cache = _source_version() or _installed_version() or _FALLBACK
    return _cache


def get_version() -> str:
    """The display version (``v0.1.0``)."""

    return f"v{raw_version()}"


def reset_cache() -> None:
    """Drop the cached version (tests use it when switching install state)."""

    global _cache
    _cache = None


VERSION = get_version()

__all__ = ["VERSION", "get_version", "raw_version", "reset_cache"]
