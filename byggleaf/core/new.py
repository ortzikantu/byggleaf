"""Create a new article from the packaged content template.

This is the service behind ``byggleaf new content``.  It only touches the
workspace's ``content/posts`` directory and never rewrites an existing file.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
ARTICLE_TEMPLATE = PACKAGE_ROOT / "resources" / "article.example.md"
DATE_PLACEHOLDER = "{{date}}"


class NewError(RuntimeError):
    """A new content file could not be created."""


@dataclass(frozen=True, slots=True)
class NewArticleResult:
    """The file that was created and the timestamp written into it."""

    path: Path
    published: dt.datetime


def _next_available_path(posts_dir: Path) -> Path:
    """Pick new-article.md, then new-article-2.md, and so on."""

    candidate = posts_dir / "new-article.md"
    index = 2
    while candidate.exists():
        candidate = posts_dir / f"new-article-{index}.md"
        index += 1
    return candidate


def create_article(
    root: Path,
    *,
    now: dt.datetime | None = None,
) -> NewArticleResult:
    """Create an empty article with dated front matter.

    Existing files are never overwritten; repeated calls produce
    ``new-article.md``, ``new-article-2.md``, etc.
    """

    root = Path(root).resolve()
    if not (root / "byggleaf.toml").is_file():
        raise NewError(
            f"byggleaf.toml not found in {root}; run `byggleaf init` first"
        )

    try:
        template = ARTICLE_TEMPLATE.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise NewError(f"cannot read article template: {ARTICLE_TEMPLATE}") from exc

    if DATE_PLACEHOLDER not in template:
        raise NewError(
            f"article template is missing the {DATE_PLACEHOLDER} placeholder"
        )

    published = (now or dt.datetime.now()).replace(microsecond=0)
    content = template.replace(
        DATE_PLACEHOLDER,
        published.isoformat(timespec="seconds"),
    )

    posts_dir = root / "content" / "posts"
    try:
        posts_dir.mkdir(parents=True, exist_ok=True)
        path = _next_available_path(posts_dir)
        path.write_text(content, encoding="utf-8")
    except OSError as exc:
        raise NewError(f"cannot create article in {posts_dir}: {exc}") from exc

    return NewArticleResult(path=path, published=published)


__all__ = ["NewArticleResult", "NewError", "create_article"]
