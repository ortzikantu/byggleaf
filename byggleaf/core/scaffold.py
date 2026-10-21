"""Generate the small, opinionated workspace used by ``byggleaf init``.

Scaffolding is a core operation: a one-way writer of inert files.  It imports
no builder, renderer, or command-line code, so the initial workspace contract
stays independent from the rendering implementation.

The generated layout is the complete public API of a garden: a TOML file,
media directories, and Markdown.  There is no theme directory, no template
override directory, and no place to put JavaScript.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


class ScaffoldError(RuntimeError):
    """Raised when a workspace cannot be created safely."""


# Package data lives at the package root, two levels above this core module.
# These files are read at init time and then belong to the user; ByggLeaf never
# edits them behind their back.
PACKAGE_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_CONFIG = PACKAGE_ROOT / "resources" / "config.example.toml"
DEFAULT_FAVICON = PACKAGE_ROOT / "assets" / "img" / "favicon.ico"


HELLO_WORLD = """\
+++
title = "Hello, World"
date = 2025-01-01
+++

This garden is a folder of Markdown, a config file, and nothing else. No
JavaScript, no theme marketplace, no build cache to debug at midnight.

## A small beginning

Write a post, give it a title and a date, and ByggLeaf will place it in the
article stream in reverse chronological order. Links, assets, and pages all
use the `baseurl` from `byggleaf.toml`.

> A digital garden should feel like paper, not like a dashboard.

A few things worth knowing:

- `content/posts/` is for dated writing.
- `content/about/index.md` is a hidden page linked only from the navbar.
- `content/statement/index.md` is a hidden page not linked from anywhere.
- `assets/img/` is copied to `public/assets/img/` untouched.

When you are ready, edit `byggleaf.toml`, run `byggleaf build`, and serve the
result with `byggleaf serve`.
"""


ABOUT_PAGE = """\
# About

This is an independent page. ByggLeaf found `content/about/index.md`, lifted
the leading heading as the page title, and rendered the rest at
`/about/index.html`.

It is one of only two links in the navbar. Replace this text with your own.
"""


STATEMENT_PAGE = """\
# Statement

ByggLeaf is a benevolent dictator for your digital garden.

It has no theme system, no custom HTML, no custom CSS, no JavaScript, and no
web fonts. What it does have is a measured column, a native serif voice, and a
small set of decisions made on your behalf.

This page is not in the navbar. It exists because a folder contained an
`index.md`, and that is enough.
"""


CONTENT_FILES: dict[Path, str] = {
    Path("content/posts/hello-world.md"): HELLO_WORLD,
    Path("content/about/index.md"): ABOUT_PAGE,
    Path("content/statement/index.md"): STATEMENT_PAGE,
}

CONTENT_DIRECTORIES: tuple[Path, ...] = (
    Path("assets/img"),
    Path("assets/video"),
    Path("assets/audio"),
    Path("content/posts"),
    Path("content/about"),
    Path("content/statement"),
)


@dataclass(frozen=True)
class ScaffoldResult:
    """What ``init`` actually did, for a truthful terminal summary."""

    root: Path
    created: tuple[Path, ...]
    skipped: tuple[Path, ...]
    favicon_copied: bool


def _write_file(path: Path, content: str, *, force: bool) -> bool:
    """Write one scaffold file, returning False when an existing file is kept."""

    if path.exists() and not force:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def init_site(root: Path, *, force: bool = False) -> ScaffoldResult:
    """Create the ByggLeaf workspace under ``root``.

    Existing user files are never overwritten unless ``force`` is explicit.
    The one hard stop is an existing ``byggleaf.toml`` without ``--force``:
    quietly layering a second garden on top of the first is not kind.
    """

    root = Path(root).resolve()

    if root.exists() and not root.is_dir():
        raise ScaffoldError(f"{root} is not a directory")

    config_path = root / "byggleaf.toml"
    if config_path.exists() and not force:
        raise ScaffoldError(
            "byggleaf.toml already exists in this directory; "
            "use `byggleaf init --force` to overwrite generated files"
        )

    try:
        config_text = EXAMPLE_CONFIG.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ScaffoldError(
            f"packaged example config is missing or unreadable: {EXAMPLE_CONFIG}"
        ) from exc

    try:
        for directory in CONTENT_DIRECTORIES:
            (root / directory).mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ScaffoldError(f"cannot create workspace directories: {exc}") from exc

    created: list[Path] = []
    skipped: list[Path] = []

    # The config is written first so a failed init leaves an obvious, fixable
    # signal rather than a half-populated content directory.  An existing
    # config without --force has already raised above.
    _write_file(config_path, config_text, force=force)
    created.append(config_path)

    for relative_path, text in CONTENT_FILES.items():
        target = root / relative_path
        if _write_file(target, text, force=force):
            created.append(target)
        else:
            skipped.append(target)

    # A packaged favicon gives every new garden a recognisable tab icon.  It
    # is copied once into the user's assets and is thereafter theirs to replace
    # or delete.  If it is deleted, the builder simply omits the icon link.
    favicon_copied = False
    favicon_target = root / "assets" / "img" / "favicon.ico"
    if DEFAULT_FAVICON.is_file() and (force or not favicon_target.exists()):
        try:
            favicon_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(DEFAULT_FAVICON, favicon_target)
        except OSError as exc:
            raise ScaffoldError(f"cannot copy default favicon: {exc}") from exc
        created.append(favicon_target)
        favicon_copied = True
    elif favicon_target.exists():
        skipped.append(favicon_target)

    return ScaffoldResult(
        root=root,
        created=tuple(created),
        skipped=tuple(skipped),
        favicon_copied=favicon_copied,
    )
