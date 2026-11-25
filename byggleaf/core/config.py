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
DEFAULT_LANGUAGE = "en"
DEFAULT_POSTS_PER_PAGE = 5

# URL 里可能夹带控制字符/空白；拼接 baseurl 前先归一化再判断是不是本地路径。
_URL_NOISE_RE = re.compile(r"[\x00-\x20]+")


def compact_url(value: str) -> str:
    """去掉 URL 里的控制字符/空白并转小写，用于 scheme 判定。"""

    return _URL_NOISE_RE.sub("", value).lower()


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
class CustomLink:
    """页脚里的一个自定义链接：站外地址或站内页面。"""

    name: str
    url: str

    @property
    def is_external(self) -> bool:
        """站外链接不拼接 baseurl。"""

        return compact_url(self.url).startswith(("http://", "https://", "mailto:", "//"))


@dataclass(frozen=True, slots=True)
class Site:
    """所有模板共享的站点级呈现值。"""

    title: str
    baseurl: str
    hero_title: str = ""
    hero_subtitle: str = ""
    hero_image: str = ""
    copyright: str = ""
    language: str = DEFAULT_LANGUAGE
    posts_per_page: int = DEFAULT_POSTS_PER_PAGE

    def url(self, path: str) -> str:
        """把站点路径转成模板使用的绝对 URL。"""

        return absolute_url(self.baseurl, path)


@dataclass(frozen=True, slots=True)
class Config:
    """完整且经过校验的配置面。"""

    site: Site
    projects: tuple[Project, ...] = ()
    customurl: tuple[CustomLink, ...] = ()


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
    # 只归一化一次，模板与调用方都不用再考虑结尾斜杠。
    if baseurl == "/":
        baseurl = ""
    else:
        baseurl = baseurl.rstrip("/")

    # hero_title 只出现在首页大标题；title 只进 head、og 与 feed。
    # 没写 hero_title 时沿用 title，老配置不用改。
    hero_title = _string(site_table, "hero_title", where="[site]") or title
    hero_subtitle = _string(site_table, "hero_subtitle", where="[site]")
    # 首屏照片：给了就换成报头式头图，没给就保持纯文字首屏。
    hero_image = _string(site_table, "hero_image", where="[site]")
    copyright_text = _string(site_table, "copyright", where="[site]")
    raw_language = _string(site_table, "language", where="[site]") or DEFAULT_LANGUAGE
    try:
        language = canonicalize_language(raw_language)
    except LocaleError as exc:
        raise ConfigError(f"[site].language: {exc}") from exc

    raw_posts_per_page = site_table.get("posts_per_page", DEFAULT_POSTS_PER_PAGE)
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
        url = _string(item, "url", where=f"projects[{index}]")
        description = _string(item, "description", where=f"projects[{index}]")
        projects.append(Project(name=name, url=url, description=description))

    raw_links = data.get("customurl", [])
    if not isinstance(raw_links, list):
        raise ConfigError(f"{path.name}: [[customurl]] must be an array of tables")

    customurl: list[CustomLink] = []
    for index, item in enumerate(raw_links, start=1):
        if not isinstance(item, dict):
            raise ConfigError(f"{path.name}: customurl[{index}] must be a table")
        customurl.append(
            CustomLink(
                name=_string(item, "name", where=f"customurl[{index}]", required=True),
                url=_string(item, "url", where=f"customurl[{index}]", required=True),
            )
        )

    site = Site(
        title=title,
        baseurl=baseurl,
        hero_title=hero_title,
        hero_subtitle=hero_subtitle,
        hero_image=hero_image,
        copyright=copyright_text,
        language=language,
        posts_per_page=posts_per_page,
    )
    return Config(
        site=site,
        projects=tuple(projects),
        customurl=tuple(customurl),
    )
