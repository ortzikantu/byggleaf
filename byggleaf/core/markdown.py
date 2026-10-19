"""Markdown rendering and front matter parsing.

The only third-party import in this module is the ``markdown`` package.  That
is intentional: ByggLeaf does not implement its own Markdown parser, and it
does not pull in YAML either.  TOML front matter (``+++``) is the canonical
format; a deliberately tiny, scalar-only YAML compatibility layer (``---``)
avoids surprising people who arrive from other generators.

Rendered HTML is sanitised before it reaches a template.  The promise is "No
JS"; that promise should survive an accidentally pasted ``<script>`` tag.
"""

from __future__ import annotations

import ast
import datetime as dt
import html
import re
import tomllib
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote

import markdown as markdown_lib

from .config import absolute_url


class MarkdownError(ValueError):
    """A Markdown file could not be read, parsed, or validated."""


# Elements that can execute or import code.  Their entire contents are dropped.
_BLOCKED_TAGS = frozenset(
    {
        "applet",
        "base",
        "button",
        "embed",
        "form",
        "frame",
        "frameset",
        "iframe",
        "input",
        "link",
        "math",
        "meta",
        "noscript",
        "object",
        "option",
        "script",
        "select",
        "style",
        "svg",
        "template",
        "textarea",
    }
)

# Attributes that can navigate to executable schemes or carry inline CSS/JS.
_DROP_ATTRIBUTES = frozenset(
    {
        "action",
        "formaction",
        "srcdoc",
        "style",
        "xlink:href",
    }
)
_URL_ATTRIBUTES = frozenset({"href", "src", "poster", "xlink:href"})
_UNSAFE_URL_PREFIXES = (
    "javascript:",
    "vbscript:",
    "data:text/html",
    "data:image/svg",
)
_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
# Control characters and whitespace are ignored by browsers when resolving a
# scheme; normalise before comparing so "java\nscript:" cannot slip through.
_URL_NOISE_RE = re.compile(r"[\x00-\x20]+")
# Void elements never emit an end tag, so a blocked one must not leave the
# sanitiser stuck in skip mode for the rest of the document.
_BLOCKED_VOID_TAGS = frozenset({"base", "embed", "input", "link", "meta"})


def _absolute_markdown_url(value: str, *, attribute: str, baseurl: str) -> str:
    """Make local Markdown resource links obey the site's baseurl.

    Images and other ``src`` values are site assets, so both ``/assets/x`` and
    ``assets/x`` resolve from the site root.  For ``href`` only root-relative
    links are rewritten; a relative page link such as ``../other/`` keeps its
    ordinary Markdown meaning.  External schemes, protocol-relative URLs,
    fragments and query-only links are left untouched.
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


class _Sanitizer(HTMLParser):
    """Small HTML filter tailored to generated Markdown.

    This is not a general-purpose security sanitiser.  It is a guard rail that
    removes executable elements, event handlers, and script-bearing URLs from
    the one input channel ByggLeaf has: Markdown authored by the site owner.
    It also makes local image/media sources absolute using ``baseurl``.
    """

    def __init__(self, baseurl: str = "") -> None:
        super().__init__(convert_charrefs=True)
        self.baseurl = baseurl
        self._chunks: list[str] = []
        self._skip_tag: str | None = None

    def _attributes(self, attrs: list[tuple[str, str | None]]) -> str:
        rendered: list[str] = []
        for name, value in attrs:
            lowered = name.lower()
            if lowered in _DROP_ATTRIBUTES or lowered.startswith("on"):
                continue
            if value is None:
                rendered.append(f" {html.escape(name, quote=True)}")
                continue
            if lowered in _URL_ATTRIBUTES:
                compact = _URL_NOISE_RE.sub("", value).lower()
                if compact.startswith(_UNSAFE_URL_PREFIXES):
                    continue
                value = _absolute_markdown_url(
                    value, attribute=lowered, baseurl=self.baseurl
                )
            rendered.append(
                f' {html.escape(name, quote=True)}="'
                f'{html.escape(value, quote=True)}"'
            )
        return "".join(rendered)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        if self._skip_tag is not None:
            return
        if lowered in _BLOCKED_TAGS:
            if lowered not in _BLOCKED_VOID_TAGS:
                self._skip_tag = lowered
            return
        self._chunks.append(f"<{lowered}{self._attributes(attrs)}>")

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        lowered = tag.lower()
        if self._skip_tag is not None or lowered in _BLOCKED_TAGS:
            return
        self._chunks.append(f"<{lowered}{self._attributes(attrs)}>")

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if self._skip_tag is not None:
            if lowered == self._skip_tag:
                self._skip_tag = None
            return
        if lowered in _BLOCKED_TAGS:
            return
        self._chunks.append(f"</{lowered}>")

    def handle_data(self, data: str) -> None:
        if self._skip_tag is None:
            self._chunks.append(html.escape(data, quote=False))

    def result(self) -> str:
        return "".join(self._chunks)


def sanitize_html(fragment: str, *, baseurl: str = "") -> str:
    """Strip executable HTML and absolutise local Markdown asset URLs."""

    parser = _Sanitizer(baseurl=baseurl)
    parser.feed(fragment)
    parser.close()
    return parser.result()


def render_markdown(text: str, *, baseurl: str = "") -> str:
    """Render Markdown to a sanitised HTML5 fragment."""

    renderer = markdown_lib.Markdown(
        extensions=["extra", "sane_lists"],
        output_format="html5",
    )
    return sanitize_html(renderer.convert(text), baseurl=baseurl)


# ---------------------------------------------------------------------------
# Front matter
# ---------------------------------------------------------------------------


def _split_front_matter(text: str, *, source: Path) -> tuple[dict[str, object], str]:
    """Return (metadata, body) for TOML or minimal YAML front matter.

    TOML is the supported format.  ``---`` blocks accept only flat
    ``key: scalar`` lines because adding a YAML parser would violate the
    two-dependency rule and, more importantly, the project's taste.
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
            if not isinstance(parsed, str):
                raise MarkdownError(
                    f"{source}: front matter values must be strings on line {line_number}"
                )
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
    """Normalise date/date-time values so mixed posts can be sorted safely."""

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
# Text extraction
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
    """Extract a short, tag-free summary from the first rendered paragraph."""

    paragraph = re.search(r"<p(?:\s[^>]*)?>(.*?)</p>", fragment, re.IGNORECASE | re.DOTALL)
    text = _text_from_html(paragraph.group(1) if paragraph else fragment)
    if len(text) <= limit:
        return text
    shortened = text[:limit].rstrip()
    # Prefer a word boundary when one exists reasonably close to the limit.
    if " " in shortened[limit // 2 :]:
        shortened = shortened[: shortened.rfind(" ")].rstrip()
    return shortened.rstrip(" ,.;:") + "…"


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Post:
    """A dated post, ready to hand to a template."""

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
        """Sort key; does not lose the display value of ``date``."""

        return _sortable_datetime(self.date)


@dataclass(frozen=True, slots=True)
class Page:
    """An independent page discovered from ``<directory>/index.md``."""

    title: str
    route: str
    html: str
    summary: str
    source: Path

    @property
    def url(self) -> str:
        return f"/{quote(self.route, safe='/')}/"


def parse_post(path: Path, *, baseurl: str = "") -> Post:
    """Read one post, validate its front matter, and render its body."""

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

    # It is common to repeat the title as an H1 at the top of the body.  The
    # template already owns the visible title, so remove only an exact
    # duplicate; a deliberately different H1 is left alone.
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
    """Lift a leading H1 out of a front-matter-less page body.

    Returning the heading separately lets the template own the page title
    without rendering the same heading twice.
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
    """Read a standalone page and derive its title from its leading H1."""

    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
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
