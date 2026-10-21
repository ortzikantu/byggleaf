"""TOML 配置：解析一次、校验一次，之后只传不可变值。

配置用标准库 :mod:`tomllib` 读取，不引入额外依赖；应用其余部分只见冻结的
dataclass，模板也没法意外改站点设置。
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .locales import LocaleError, canonicalize_language

CONFIG_FILENAME = "byggleaf.toml"

# 可执行/可夹带代码的 URL scheme。这是配置层面的约束，与 Markdown 内容
# 怎么渲染无关：``baseurl`` 与项目链接属于站点配置，不合理或可执行的值
# 应在解析阶段就拒绝，而不是生成一个坏掉的站点。
_UNSAFE_URL_PREFIXES = (
    "javascript:",
    "vbscript:",
    "data:text/html",
    "data:image/svg",
)
_URL_NOISE_RE = re.compile(r"[\x00-\x20]+")


def _unsafe_url(value: str) -> bool:
    """配置中的 URL 若被浏览器解析后可能执行代码，返回 True。"""

    compact = _URL_NOISE_RE.sub("", value).lower()
    return compact.startswith(_UNSAFE_URL_PREFIXES)


class ConfigError(ValueError):
    """配置文件缺失、不可读或语义无效。"""


def absolute_url(baseurl: str, path: str) -> str:
    """把站点相对路径拼到 ``baseurl`` 上。

    ``baseurl`` 可以是完整域名（``https://example.com``）、子目录
    （``https://example.com/garden``），或用于本地根相对预览的空串。
    返回值对 Web 服务器而言总是绝对 *路径*；设置了 baseurl 时则是完整 URL。
    """

    if not path:
        path = "/"
    if not path.startswith("/"):
        path = "/" + path
    return baseurl.rstrip("/") + path


@dataclass(frozen=True, slots=True)
class Project:
    """首页项目列表中的一项。"""

    name: str
    url: str
    description: str = ""


@dataclass(frozen=True, slots=True)
class Site:
    """所有模板共享的站点级呈现值。"""

    title: str
    baseurl: str
    hero_subtitle: str = ""
    copyright: str = ""
    language: str = "en"
    posts_per_page: int = 5

    def url(self, path: str) -> str:
        """把站点路径转成模板使用的绝对 URL。"""

        return absolute_url(self.baseurl, path)


@dataclass(frozen=True, slots=True)
class Config:
    """完整且经过校验的配置面。"""

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
    """读取并校验 ``byggleaf.toml``。

    错误信息同时给出文件名与出错的键，不让用户去猜哪一行 TOML 写错了。
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
    # 空 baseurl 合法且有用：生成本地预览所需的根相对链接；
    # 但缺少 baseurl 仍是配置错误。
    if "baseurl" not in site_table:
        raise ConfigError("[site].baseurl is required (it may be an empty string)")
    baseurl = _string(
        site_table, "baseurl", where="[site]", required=True, allow_empty=True
    )
    if any(character.isspace() for character in baseurl):
        raise ConfigError("[site].baseurl must not contain whitespace")
    if _unsafe_url(baseurl):
        raise ConfigError("[site].baseurl must not be an executable URL scheme")
    # 只归一化一次，模板与调用方都不用再考虑结尾斜杠。
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
