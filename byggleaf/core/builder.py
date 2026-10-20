"""The build orchestrator.

This is the only core module that knows the shape of a ByggLeaf project:
``content/`` in, ``public/`` out, with packaged CSS and the user's media
copied alongside.  It composes the lower-level ``config``, ``markdown``,
``jinja`` and ``server`` bases without knowing anything about argparse or
terminal colours.

The build is deliberately three readable stages:

1. **Preflight** — validate the project, parse every post/page, and render all
   HTML in memory.  No output path is touched.
2. **Materialize** — copy assets and write the rendered files into a private
   hidden staging directory.
3. **Publish** — swap the finished staging tree into ``public/``, restoring the
   previous tree if the swap fails.

Routing contract:

* ``content/posts/name.md``                  -> ``/posts/name/``
* ``content/posts/``                         -> ``/posts/`` archive
* ``content/<any>/index.md``                 -> ``/<any>/``
* ``content/posts/**`` is never a custom page
* Home is generated at ``/`` and is not sourced from content.
* ``/404.html`` (localized error page) and ``/robots.txt`` are always emitted.

Custom pages are intentionally invisible: they never enter the navbar.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import time
import uuid
from dataclasses import dataclass, replace
from pathlib import Path

from .config import Config
from .jinja import TemplateEngine
from .locales import Locale, load_locale
from .markdown import Page, Post, parse_post, render_page
from .seo import SitemapEntry, render_robots, render_rss, render_sitemap

PACKAGE_ASSETS = Path(__file__).resolve().parent.parent / "assets"
USER_ASSET_DIRECTORIES = ("img", "video", "audio")


class BuildError(RuntimeError):
    """The project cannot be rendered safely or completely."""


@dataclass(frozen=True, slots=True)
class BuildResult:
    """A factual summary for the CLI, not a logging side effect."""

    output_dir: Path
    posts: int
    pages: int
    assets: int
    favicon: str | None
    duration_seconds: float


@dataclass(frozen=True, slots=True)
class OutputFile:
    """One fully rendered file waiting to be written."""

    relative_path: Path
    content: str


@dataclass(frozen=True, slots=True)
class PreparedSite:
    """Everything that can fail during content/template processing.

    Building this object touches no output directory.  A failed preflight must
    leave the previous public/ tree exactly as it was.
    """

    favicon: str | None
    posts: tuple[Post, ...]
    pages: tuple[Page, ...]
    files: tuple[OutputFile, ...]


@dataclass(frozen=True, slots=True)
class Pagination:
    """Template-facing pagination state for one home page slice."""

    current_page: int
    total_pages: int
    previous_url: str | None
    next_url: str | None


def _humanize_route(route: str) -> str:
    """Fallback title for an index.md that starts without an H1."""

    last = route.rsplit("/", 1)[-1] or route
    words = last.replace("_", " ").replace("-", " ").strip()
    return words.title() if words else "Page"


def _pagination_url(page_number: int) -> str:
    """Page 1 is the home page; later pages use clean /page/n/ URLs."""

    return "/" if page_number == 1 else f"/page/{page_number}/"


class Builder:
    """Render one ByggLeaf project rooted at ``root``."""

    def __init__(self, root: Path, config: Config) -> None:
        self.root = Path(root).resolve()
        self.config = config
        self.content_dir = self.root / "content"
        self.assets_dir = self.root / "assets"
        self.output_dir = self.root / "public"
        self.locale: Locale = load_locale(config.site.language)
        self.templates = TemplateEngine(config, self.locale)
        self._staging_dir: Path | None = None

    def _nav(self, active: str | None) -> list[dict[str, object]]:
        """Exactly two links, localized for the configured language."""

        return [
            {
                "label": self.locale.text("home"),
                "url": "/",
                "active": active == "home",
            },
            {
                "label": self.locale.text("about"),
                "url": "/about/",
                "active": active == "about",
            },
        ]

    @property
    def _target(self) -> Path:
        """The private directory currently being rendered into."""

        if self._staging_dir is None:
            raise BuildError("build staging directory is not initialized")
        return self._staging_dir

    # -- public entry point -------------------------------------------------

    def build(self) -> BuildResult:
        started = time.perf_counter()

        # Recover any temporary trees left by a process killed mid-publish.
        self._recover_publication()

        # Stage 1: validate and render everything in memory.  No output path is
        # touched before this succeeds.
        prepared = self._preflight()

        # Stage 2: materialise into a private staging tree.  Content and
        # template failures are already impossible by this point.
        staging = Path(
            tempfile.mkdtemp(prefix=".byggleaf-build-", dir=self.root)
        )
        self._staging_dir = staging
        assets = 0
        try:
            # mkdtemp creates 0700; published pages should stay world-readable.
            staging.chmod(0o755)
            assets = self._materialize(prepared)
            self._publish(staging)
        except BaseException as exc:
            shutil.rmtree(staging, ignore_errors=True)
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            if isinstance(exc, BuildError):
                raise
            raise BuildError(f"build failed: {exc}") from exc
        finally:
            self._staging_dir = None

        return BuildResult(
            output_dir=self.output_dir,
            posts=len(prepared.posts),
            pages=len(prepared.pages),
            assets=assets,
            favicon=prepared.favicon,
            duration_seconds=time.perf_counter() - started,
        )

    def _preflight(self) -> PreparedSite:
        """Parse all content and render all HTML without writing output.

        This is stage D of the failure policy.  Markdown errors, invalid front
        matter, template exceptions, and missing templates are caught before a
        staging directory even exists.
        """

        try:
            self._validate_project()
            favicon = self._detect_favicon()
            posts = self._load_posts()
            pages = self._load_pages()
            files = self._render_site(posts, pages, favicon)
        except BuildError:
            raise
        except Exception as exc:
            raise BuildError(f"build failed: {exc}") from exc

        return PreparedSite(
            favicon=favicon,
            posts=tuple(posts),
            pages=tuple(pages),
            files=tuple(files),
        )

    def _materialize(self, prepared: PreparedSite) -> int:
        """Copy assets and write pre-rendered HTML into the staging tree."""

        assets = self._copy_stylesheet()
        assets += self._copy_user_assets()
        for rendered in prepared.files:
            self._write_output(rendered.relative_path, rendered.content)
        return assets

    # -- validation and filesystem -----------------------------------------

    def _validate_project(self) -> None:
        if not self.content_dir.is_dir():
            raise BuildError(
                f"{self.content_dir} is missing; run `byggleaf init` first"
            )

        stylesheet = PACKAGE_ASSETS / "css" / "style.css"
        if not stylesheet.is_file():
            raise BuildError(f"packaged stylesheet is missing: {stylesheet}")

        if self.output_dir.is_symlink():
            # Refuse to recursively delete something that is not really ours.
            raise BuildError(
                f"{self.output_dir} is a symlink; run `byggleaf clean` and build again"
            )
        if self.output_dir.exists() and not self.output_dir.is_dir():
            raise BuildError(
                f"{self.output_dir} exists but is not a directory; "
                "run `byggleaf clean` and build again"
            )

    def _recover_publication(self) -> None:
        """Repair leftovers from a process killed during a previous publish.

        If public/ is missing but a backup exists, restore the newest backup.
        If public/ exists, any backups are stale.  Staging trees are always
        disposable and are removed at the start of the next build.
        """

        backups = sorted(self.root.glob(".byggleaf-public-*"))
        if (
            not self.output_dir.exists()
            and not self.output_dir.is_symlink()
            and backups
        ):
            newest = max(backups, key=lambda path: path.stat().st_mtime_ns)
            os.replace(newest, self.output_dir)
            backups.remove(newest)

        for backup in backups:
            if backup.is_dir():
                shutil.rmtree(backup, ignore_errors=True)
            else:
                backup.unlink(missing_ok=True)

        for staging in self.root.glob(".byggleaf-build-*"):
            if staging.is_dir():
                shutil.rmtree(staging, ignore_errors=True)
            else:
                staging.unlink(missing_ok=True)

    def _publish(self, staging: Path) -> None:
        """Swap the finished staging tree into place.

        The old directory is renamed aside first; if the new tree cannot be
        moved into place, the old directory is restored.  The only window in
        which ``public/`` does not exist is the two local renames.
        """

        final = self.output_dir
        backup: Path | None = None

        if final.exists() or final.is_symlink():
            if final.is_symlink() or not final.is_dir():
                raise BuildError(
                    f"{final} is not a replaceable directory; run `byggleaf clean`"
                )
            backup = self.root / f".byggleaf-public-{uuid.uuid4().hex}"
            os.replace(final, backup)

        try:
            os.replace(staging, final)
        except BaseException:
            if backup is not None:
                try:
                    os.replace(backup, final)
                except OSError as restore_exc:
                    raise BuildError(
                        "could not publish the new site, and the previous "
                        f"public/ could not be restored; it is preserved at {backup}"
                    ) from restore_exc
            raise

        if backup is not None:
            # The new site is live; failure to tidy the backup is not a build
            # failure, and the hidden directory is safe to remove later.
            shutil.rmtree(backup, ignore_errors=True)

    def _detect_favicon(self) -> str | None:
        """Look only in the user's assets.  No file means no icon, not an error."""

        candidate = self.assets_dir / "img" / "favicon.ico"
        return "/assets/img/favicon.ico" if candidate.is_file() else None

    def _copy_stylesheet(self) -> int:
        source = PACKAGE_ASSETS / "css" / "style.css"
        target = self._target / "assets" / "css" / "style.css"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return 1

    def _copy_user_assets(self) -> int:
        """Copy only media.  User CSS/JS has no supported path into a page."""

        copied = 0
        for name in USER_ASSET_DIRECTORIES:
            source = self.assets_dir / name
            if not source.is_dir():
                continue
            target = self._target / "assets" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, target, dirs_exist_ok=True)
            copied += sum(1 for item in source.rglob("*") if item.is_file())
        return copied

    # -- content discovery --------------------------------------------------

    def _load_posts(self) -> list[Post]:
        posts_dir = self.content_dir / "posts"
        if not posts_dir.is_dir():
            return []

        posts: list[Post] = []
        for path in sorted(posts_dir.glob("*.md")):
            if not path.is_file():
                continue
            if path.stem in {"", ".", ".."} or "\\" in path.stem:
                raise BuildError(f"{path}: unsafe post filename")
            posts.append(parse_post(path, baseurl=self.config.site.baseurl))

        # Newest first.  The title is a stable tie-breaker for equal dates.
        posts.sort(
            key=lambda post: (post.published_timestamp, post.title),
            reverse=True,
        )
        return posts

    def _load_pages(self) -> list[Page]:
        """Discover every index.md except files inside content/posts/."""

        pages: list[Page] = []
        for path in sorted(self.content_dir.rglob("index.md")):
            if not path.is_file():
                continue
            relative = path.parent.relative_to(self.content_dir)
            if not relative.parts:
                continue  # content/index.md would collide with Home
            if relative.parts[0] == "posts":
                continue
            route = relative.as_posix()
            page = render_page(
                path,
                route=route,
                baseurl=self.config.site.baseurl,
            )
            if not page.title:
                page = replace(page, title=_humanize_route(route))
            pages.append(page)

        pages.sort(key=lambda page: page.route)
        return pages

    # -- rendering ----------------------------------------------------------

    def _render_site(
        self,
        posts: list[Post],
        pages: list[Page],
        favicon: str | None,
    ) -> list[OutputFile]:
        """Render every page, feed, and sitemap entry into memory."""

        files: list[OutputFile] = []
        site = self.config.site
        pagination_pages = self._paginate(posts)
        post_back_urls = {
            post.slug: _pagination_url(page_number)
            for page_number, page_posts, _ in pagination_pages
            for post in page_posts
        }
        sitemap_entries: list[SitemapEntry] = [
            SitemapEntry(path=_pagination_url(page_number))
            for page_number, _, _ in pagination_pages
        ]

        for page_number, page_posts, pagination in pagination_pages:
            relative_path = (
                Path("index.html")
                if page_number == 1
                else Path("page") / str(page_number) / "index.html"
            )
            files.append(
                OutputFile(
                    relative_path=relative_path,
                    content=self.templates.render(
                        "home.html",
                        posts=page_posts,
                        pagination=pagination,
                        nav=self._nav("home"),
                        favicon=favicon,
                        meta_title=(
                            site.title
                            if page_number == 1
                            else (
                                f"{self.locale.text('page_title', page=page_number)}"
                                f" · {site.title}"
                            )
                        ),
                        meta_description=site.hero_subtitle or site.title,
                        canonical_path=_pagination_url(page_number),
                        og_type="website",
                    ),
                )
            )

        for post in posts:
            files.append(
                OutputFile(
                    relative_path=Path("posts") / post.slug / "index.html",
                    content=self.templates.render(
                        "post.html",
                        post=post,
                        back_url=post_back_urls[post.slug],
                        nav=self._nav("home"),
                        favicon=favicon,
                    ),
                )
            )
            sitemap_entries.append(
                SitemapEntry(
                    path=post.url,
                    lastmod=(post.updated or post.date).isoformat(),
                )
            )

        for page in pages:
            active = "about" if page.route == "about" else None
            files.append(
                OutputFile(
                    relative_path=Path(page.route) / "index.html",
                    content=self.templates.render(
                        "page.html",
                        page=page,
                        nav=self._nav(active),
                        favicon=favicon,
                        meta_title=f"{page.title} · {site.title}",
                        meta_description=(
                            page.summary
                            or site.hero_subtitle
                            or site.title
                        ),
                        canonical_path=page.url,
                        og_type="article",
                    ),
                )
            )
            sitemap_entries.append(SitemapEntry(path=page.url))

        # The error page is a real document (same chrome, localized copy), but
        # it is deliberately not a sitemap entry: crawlers should not list it.
        files.append(
            OutputFile(
                relative_path=Path("404.html"),
                content=self.templates.render(
                    "404.html",
                    nav=self._nav(None),
                    favicon=favicon,
                    meta_title=(
                        f"{self.locale.text('not_found')} · {site.title}"
                    ),
                    meta_description=self.locale.text("not_found_hint"),
                    canonical_path="/404.html",
                    og_type="website",
                ),
            )
        )

        files.append(
            OutputFile(
                relative_path=Path("robots.txt"),
                content=render_robots(self.config),
            )
        )

        files.append(
            OutputFile(
                relative_path=Path("sitemap.xml"),
                content=render_sitemap(self.config, sitemap_entries),
            )
        )
        files.append(
            OutputFile(
                relative_path=Path("rss.xml"),
                content=render_rss(self.config, posts),
            )
        )
        self._assert_unique_outputs(files)
        return files

    def _assert_unique_outputs(self, files: list[OutputFile]) -> None:
        """Fail preflight when two generated files would share one path."""

        seen: set[str] = set()
        for output in files:
            key = output.relative_path.as_posix()
            if key in seen:
                raise BuildError(f"output path conflict: /{key}")
            seen.add(key)

    def _paginate(self, posts: list[Post]) -> list[tuple[int, list[Post], Pagination]]:
        """Split posts into home-page slices using the configured page size."""

        per_page = self.config.site.posts_per_page
        total_pages = max(1, (len(posts) + per_page - 1) // per_page)
        result: list[tuple[int, list[Post], Pagination]] = []

        for page_number in range(1, total_pages + 1):
            start = (page_number - 1) * per_page
            page_posts = posts[start : start + per_page]
            pagination = Pagination(
                current_page=page_number,
                total_pages=total_pages,
                previous_url=(
                    _pagination_url(page_number - 1) if page_number > 1 else None
                ),
                next_url=(
                    _pagination_url(page_number + 1)
                    if page_number < total_pages
                    else None
                ),
            )
            result.append((page_number, page_posts, pagination))

        return result

    def _write_output(self, relative: Path, content: str) -> None:
        target = self._target / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content.rstrip() + "\n", encoding="utf-8")
