"""Markdown 渲染和 front matter 解析。

本模块只导入第三方 ``markdown`` 包——ByggLeaf 不自己实现 Markdown 解析器，
也不引入 YAML。TOML front matter（``+++``）是规范格式；``---`` 只提供刻意
很小、仅标量的 YAML 兼容层，免得从别家生成器迁来的人踩坑。

渲染结果直接交给模板，ByggLeaf 不过滤、不改写用户在 Markdown 里写的原始
HTML——那属于内容作者。唯一会做的是把 baseurl 应用到渲染器产出的本地链接和
媒体上。
"""

from __future__ import annotations

import ast
import datetime as dt
import re
import tomllib
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote
from xml.etree.ElementTree import Element

import markdown as markdown_lib
from markdown.extensions import Extension
from markdown.treeprocessors import Treeprocessor

from .config import absolute_url


class MarkdownError(ValueError):
    """Markdown 文件无法读取、解析或校验。"""


# Markdown 渲染器可能产出的、带 URL 的属性。源码里的原始 HTML 不会进入
# 这棵树，因此会原样到达页面。
_URL_ATTRIBUTES = ("href", "src")
_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
# URL 里可能用控制字符/空白隐藏 scheme；判定本地路径前先做归一化。
_URL_NOISE_RE = re.compile(r"[\x00-\x20]+")


def _absolute_markdown_url(value: str, *, attribute: str, baseurl: str) -> str:
    """让本地 Markdown 资源链接遵循站点的 baseurl。

    图片等 ``src`` 是站点资源，``/assets/x`` 与 ``assets/x`` 都按站点根解析；
    ``href`` 只重写根相对链接，像 ``../other/`` 这样的相对页链接保持 Markdown
    本义。外部 scheme、协议相对 URL、锚点与仅查询串链接都不动。
    """

    stripped = value.strip()
    if not stripped or stripped.startswith(("#", "?", "//")):
        return value
    compact = _URL_NOISE_RE.sub("", stripped).lower()
    if _SCHEME_RE.match(compact):
        return value
    if attribute == "href" and not stripped.startswith("/"):
        return value
    return absolute_url(baseurl, stripped)


class _BaseurlTreeprocessor(Treeprocessor):
    """把 baseurl 应用到渲染后 Markdown 中的本地链接与媒体。

    只访问 Markdown 渲染器产出的元素；源码里的原始 HTML 块不会进入这棵树，
    因此原样到达页面。
    """

    def __init__(self, baseurl: str) -> None:
        super().__init__()
        self.baseurl = baseurl

    def run(self, root: Element) -> Element:
        for element in root.iter():
            if not isinstance(element.tag, str):
                continue
            for attribute in _URL_ATTRIBUTES:
                value = element.get(attribute)
                if value:
                    element.set(
                        attribute,
                        _absolute_markdown_url(
                            value, attribute=attribute, baseurl=self.baseurl
                        ),
                    )
        return root


class _BaseurlExtension(Extension):
    """为一次渲染注册 :class:`_BaseurlTreeprocessor`。"""

    def __init__(self, baseurl: str) -> None:
        super().__init__()
        self.baseurl = baseurl

    def extendMarkdown(self, md: markdown_lib.Markdown) -> None:
        md.treeprocessors.register(
            _BaseurlTreeprocessor(self.baseurl), "byggleaf-baseurl", 5
        )


def render_markdown(text: str, *, baseurl: str = "") -> str:
    """渲染为 HTML5 片段，并把 baseurl 应用到本地 URL。"""

    renderer = markdown_lib.Markdown(
        extensions=["extra", "sane_lists", _BaseurlExtension(baseurl)],
        output_format="html5",
    )
    return renderer.convert(text)


# ---------------------------------------------------------------------------
# Front matter（元数据头）
# ---------------------------------------------------------------------------


def _split_front_matter(text: str, *, source: Path) -> tuple[dict[str, object], str]:
    """返回 (metadata, body)，支持 TOML 或极简 YAML front matter。

    TOML 是受支持的格式；``---`` 块只接受扁平的 ``key: scalar`` 行——
    引入 YAML 解析器会破坏“两个依赖”的规则，也不符合项目口味。
    """

    if text.startswith("\ufeff"):
        text = text[1:]
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    if not text.startswith(("+++\n", "---\n")):
        return {}, text

    delimiter = text[:3]
    lines = text.split("\n")
    try:
        end = next(
            index for index, line in enumerate(lines[1:], start=1)
            if line.strip() == delimiter
        )
    except StopIteration as exc:
        raise MarkdownError(f"{source}: unterminated {delimiter} front matter") from exc

    raw = "\n".join(lines[1:end])
    body = "\n".join(lines[end + 1 :]).lstrip("\n")

    if delimiter == "+++":
        try:
            toml_metadata = tomllib.loads(raw)
        except tomllib.TOMLDecodeError as exc:
            raise MarkdownError(f"{source}: invalid TOML front matter: {exc}") from exc
        return toml_metadata, body

    metadata: dict[str, object] = {}
    for line_number, line in enumerate(raw.splitlines(), start=2):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in line:
            raise MarkdownError(
                f"{source}: front matter line {line_number} is not `key: value`"
            )
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            raise MarkdownError(f"{source}: empty front matter key on line {line_number}")
        if len(value) >= 2 and value[0] in {"'", '"'}:
            if value[-1] != value[0]:
                raise MarkdownError(
                    f"{source}: unterminated quoted value on line {line_number}"
                )
            try:
                parsed = ast.literal_eval(value)
            except (ValueError, SyntaxError) as exc:
                raise MarkdownError(
                    f"{source}: invalid quoted value on line {line_number}"
                ) from exc
            value = parsed
        metadata[key] = value
    return metadata, body


DateValue = dt.date | dt.datetime


def _parse_date(value: object, *, source: Path, key: str = "date") -> DateValue:
    if isinstance(value, dt.datetime):
        return value
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            raise MarkdownError(f"{source}: front matter {key} must not be empty")
        try:
            if "T" in candidate or " " in candidate:
                return dt.datetime.fromisoformat(candidate)
            return dt.date.fromisoformat(candidate)
        except ValueError:
            try:
                return dt.datetime.fromisoformat(candidate)
            except ValueError as exc:
                raise MarkdownError(
                    f"{source}: invalid {key} {value!r}; "
                    "use YYYY-MM-DD or an ISO date-time"
                ) from exc
    raise MarkdownError(
        f"{source}: front matter {key} must be a date or date-time"
    )


def _parse_optional_date(
    value: object,
    *,
    source: Path,
    key: str,
) -> DateValue | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return _parse_date(value, source=source, key=key)


def _parse_author(value: object, *, source: Path) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise MarkdownError(f"{source}: front matter author must be a string")
    return value.strip()


def _parse_tags(metadata: dict[str, object], *, source: Path) -> tuple[str, ...]:
    value = metadata.get("tags", metadata.get("tag"))
    if value is None:
        return ()
    if isinstance(value, str):
        items = [item.strip() for item in value.split(",")]
    elif isinstance(value, list):
        if not all(isinstance(item, str) for item in value):
            raise MarkdownError(
                f"{source}: front matter tags must be a list of strings"
            )
        items = [item.strip() for item in value]
    else:
        raise MarkdownError(
            f"{source}: front matter tags must be a list or comma-separated string"
        )
    return tuple(item for item in items if item)


def _sortable_datetime(value: DateValue) -> dt.datetime:
    """把日期/日期时间统一成可比较的时间，混合文章也能安全排序。"""

    if isinstance(value, dt.datetime):
        if value.tzinfo is not None:
            return value.astimezone(dt.UTC).replace(tzinfo=None)
        return value
    return dt.datetime.combine(value, dt.time.min)


def _required_title(value: object, *, source: Path) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MarkdownError(f"{source}: front matter title is required")
    return value.strip()


# ---------------------------------------------------------------------------
# 文本提取
# ---------------------------------------------------------------------------


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _text_from_html(fragment: str) -> str:
    parser = _TextExtractor()
    parser.feed(fragment)
    parser.close()
    return re.sub(r"\s+", " ", "".join(parser.parts)).strip()


def summarize_html(fragment: str, *, limit: int = 180) -> str:
    """从首个渲染段落中提取一段无标签的短摘要。"""

    paragraph = re.search(r"<p(?:\s[^>]*)?>(.*?)</p>", fragment, re.IGNORECASE | re.DOTALL)
    text = _text_from_html(paragraph.group(1) if paragraph else fragment)
    if len(text) <= limit:
        return text
    shortened = text[:limit].rstrip()
    # 若限额附近存在词边界，优先在词边界截断。
    if " " in shortened[limit // 2 :]:
        shortened = shortened[: shortened.rfind(" ")].rstrip()
    return shortened.rstrip(" ,.;:") + "…"


# ---------------------------------------------------------------------------
# 文档对象
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Post:
    """一篇带日期的文章，可直接交给模板。"""

    title: str
    date: DateValue
    slug: str
    html: str
    summary: str
    source: Path
    updated: DateValue | None = None
    author: str = ""
    tags: tuple[str, ...] = ()

    @property
    def url(self) -> str:
        return f"/posts/{quote(self.slug, safe='')}/"

    @property
    def published_timestamp(self) -> dt.datetime:
        """排序键；不会丢失 ``date`` 的展示值。"""

        return _sortable_datetime(self.date)


@dataclass(frozen=True, slots=True)
class Page:
    """从 ``<目录>/index.md`` 发现的独立页面。"""

    title: str
    route: str
    html: str
    summary: str
    source: Path

    @property
    def url(self) -> str:
        return f"/{quote(self.route, safe='/')}/"


def parse_post(path: Path, *, baseurl: str = "") -> Post:
    """读取一篇文章，校验 front matter 并渲染正文。"""

    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise MarkdownError(f"cannot read {path}: {exc}") from exc

    metadata, body = _split_front_matter(text, source=path)
    title = _required_title(metadata.get("title"), source=path)
    if "date" not in metadata:
        raise MarkdownError(f"{path}: front matter date is required")
    date = _parse_date(metadata["date"], source=path, key="date")
    updated = _parse_optional_date(
        metadata.get("updated"), source=path, key="updated"
    )
    author = _parse_author(metadata.get("author"), source=path)
    tags = _parse_tags(metadata, source=path)

    # 正文开头常会重复一遍标题作为 H1；模板已负责可见标题，
    # 因此只删除与 title 完全相同的重复项，故意不同的 H1 保持原样。
    leading_title, without_heading = extract_leading_heading(body)
    if leading_title and leading_title.casefold() == title.casefold():
        body = without_heading

    rendered = render_markdown(body, baseurl=baseurl)
    return Post(
        title=title,
        date=date,
        slug=path.stem,
        html=rendered,
        summary=summarize_html(rendered),
        source=path,
        updated=updated,
        author=author,
        tags=tags,
    )


_HEADING_RE = re.compile(r"^#\s+(.+?)\s*#*\s*$")


def extract_leading_heading(text: str) -> tuple[str | None, str]:
    """从无 front matter 的页面正文中取出开头的 H1。

    把标题单独返回，模板就能拥有页面标题，而不必重复渲染同一个标题。
    """

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    index = 0
    while index < len(lines) and not lines[index].strip():
        index += 1
    if index >= len(lines):
        return None, normalized

    match = _HEADING_RE.match(lines[index])
    if not match:
        return None, normalized
    title = match.group(1).strip()
    remainder = "\n".join(lines[index + 1 :]).lstrip("\n")
    return title or None, remainder


def render_page(
    path: Path, *, route: str | None = None, baseurl: str = ""
) -> Page:
    """读取独立页面，并从开头的 H1 推导标题。"""

    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
        if text.startswith("\ufeff"):
            # 与 _split_front_matter 一致：UTF-8 BOM 不能干扰
            # 标题检测，也不能泄漏进渲染正文。
            text = text[1:]
    except (OSError, UnicodeError) as exc:
        raise MarkdownError(f"cannot read {path}: {exc}") from exc

    title, body = extract_leading_heading(text)
    rendered = render_markdown(body, baseurl=baseurl)
    return Page(
        title=title or "",
        route=route if route is not None else path.parent.name,
        html=rendered,
        summary=summarize_html(rendered),
        source=path,
    )
