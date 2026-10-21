"""从包内模板创建新文章。

``byggleaf new content`` 的服务实现，只写 ``content/posts``。已有文件绝不
覆盖，重复执行会自动递增文件名。
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
ARTICLE_TEMPLATE = PACKAGE_ROOT / "resources" / "article.example.md"
DATE_PLACEHOLDER = "{{date}}"


class NewError(RuntimeError):
    """新内容文件无法创建。"""


@dataclass(frozen=True, slots=True)
class NewArticleResult:
    """记录创建的文件与写入的时间戳。"""

    path: Path
    published: dt.datetime


def _next_available_path(posts_dir: Path) -> Path:
    """依次选择 new-article.md、new-article-2.md……不会覆盖已有文件。"""

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
    """创建带日期 front matter 的空文章。

    已存在的文件绝不覆盖；重复调用会得到 ``new-article.md``、
    ``new-article-2.md``……
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
