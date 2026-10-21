"""生成 ``byggleaf init`` 使用的克制工作区。

这是一个只写惰性文件的单向操作，不导入 builder、渲染器或命令行代码，
初始工作区的契约因此独立于渲染实现。

生成的布局就是一个花园的完整公开 API：一个 TOML、媒体目录和 Markdown；
没有主题目录、没有模板覆盖目录，也没有放 JavaScript 的地方。
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


class ScaffoldError(RuntimeError):
    """工作区无法安全创建。"""


# 包内数据位于包根（比本模块高两层）。这些文件只在 init 时读取，
# 之后归用户所有；ByggLeaf 不会背着用户改动它们。
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
    """记录 init 实际做了什么，供终端摘要如实输出。"""

    root: Path
    created: tuple[Path, ...]
    skipped: tuple[Path, ...]
    favicon_copied: bool


def _write_file(path: Path, content: str, *, force: bool) -> bool:
    """写一个脚手架文件；文件已存在且未 force 时保留并返回 False。"""

    if path.exists() and not force:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def init_site(root: Path, *, force: bool = False) -> ScaffoldResult:
    """在 ``root`` 下创建 ByggLeaf 工作区。

    用户已有的文件只在显式 ``force`` 时覆盖；唯一的硬性拦截是已存在
    ``byggleaf.toml`` 却没加 ``--force``——在别人的花园上悄悄再盖一层
    并不友善。
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

    # 先写配置：init 失败时留下的是明显可修的信号，而不是只填了一半的
    # 内容目录。已存在配置且未加 --force 的情况在上方已经报错。
    _write_file(config_path, config_text, force=force)
    created.append(config_path)

    for relative_path, text in CONTENT_FILES.items():
        target = root / relative_path
        if _write_file(target, text, force=force):
            created.append(target)
        else:
            skipped.append(target)

    # 包内 favicon 让每个新花园都有可辨识的标签页图标；只复制一次到用户
    # 资源目录，之后由用户替换或删除。删除后构建器只是不再输出 icon 链接。
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
