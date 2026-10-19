"""Generate sitemap.xml and rss.xml from the prepared site content."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from email.utils import format_datetime
from xml.sax.saxutils import escape, quoteattr

from .config import Config
from .markdown import DateValue, Post
from .version import VERSION


@dataclass(frozen=True, slots=True)
class SitemapEntry:
    """One URL in the sitemap, with an optional ISO last-modified value."""

    path: str
    lastmod: str | None = None


def _xml_escape(value: str) -> str:
    return escape(value, {'"': "&quot;"})


def _rss_datetime(value: DateValue) -> dt.datetime:
    if isinstance(value, dt.datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=dt.UTC)
        return value.astimezone(dt.UTC)
    return dt.datetime.combine(value, dt.time.min, tzinfo=dt.UTC)


def _rfc822(value: DateValue) -> str:
    return format_datetime(_rss_datetime(value), usegmt=True)


def render_sitemap(config: Config, entries: list[SitemapEntry]) -> str:
    """Render a deterministic sitemap in sitemaps.org XML format."""

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for entry in entries:
        lines.append("  <url>")
        lines.append(f"    <loc>{_xml_escape(config.site.url(entry.path))}</loc>")
        if entry.lastmod is not None:
            lines.append(f"    <lastmod>{_xml_escape(entry.lastmod)}</lastmod>")
        lines.append("  </url>")
    lines.append("</urlset>")
    return "\n".join(lines) + "\n"


def render_rss(
    config: Config,
    posts: list[Post],
    *,
    build_time: dt.datetime | None = None,
) -> str:
    """Render an RSS 2.0 feed with summaries and article tags."""

    site = config.site
    channel_link = site.url("/")
    self_link = site.url("/rss.xml")
    description = site.hero_subtitle or site.title
    generated_at = build_time or dt.datetime.now(dt.UTC)
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=dt.UTC)
    generated_at = generated_at.astimezone(dt.UTC)

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" '
        'xmlns:atom="http://www.w3.org/2005/Atom" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/">',
        "  <channel>",
        f"    <title>{_xml_escape(site.title)}</title>",
        f"    <link>{_xml_escape(channel_link)}</link>",
        f"    <description>{_xml_escape(description)}</description>",
        f"    <language>{_xml_escape(site.language)}</language>",
        f"    <generator>ByggLeaf {VERSION}</generator>",
        f"    <lastBuildDate>{format_datetime(generated_at, usegmt=True)}</lastBuildDate>",
        f"    <atom:link href={quoteattr(self_link)} rel=\"self\" "
        'type="application/rss+xml"/>',
    ]
    if site.copyright:
        lines.append(f"    <copyright>{_xml_escape(site.copyright)}</copyright>")

    for post in posts:
        link = site.url(post.url)
        lines.extend(
            [
                "    <item>",
                f"      <title>{_xml_escape(post.title)}</title>",
                f"      <link>{_xml_escape(link)}</link>",
                f'      <guid isPermaLink="true">{_xml_escape(link)}</guid>',
                f"      <pubDate>{_rfc822(post.date)}</pubDate>",
                f"      <description>{_xml_escape(post.summary or post.title)}</description>",
            ]
        )
        if post.author:
            lines.append(f"      <dc:creator>{_xml_escape(post.author)}</dc:creator>")
        for tag in post.tags:
            lines.append(f"      <category>{_xml_escape(tag)}</category>")
        lines.append("    </item>")

    lines.extend(["  </channel>", "</rss>"])
    return "\n".join(lines) + "\n"


__all__ = ["SitemapEntry", "render_rss", "render_sitemap"]
