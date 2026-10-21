"""构建编排器。

它是唯一知道 ByggLeaf 项目形状的 core 模块：``content/`` 进、``public/`` 出，
顺带复制包内 CSS 和用户媒体；它组合 config、markdown、jinja、server 这些下层
模块，但不认识 argparse。

构建刻意分成三个可读阶段：

1. **预检**：校验项目、解析全部文章/页面、在内存渲染全部 HTML，不碰输出路径。
2. **落地**：复制资源，把渲染结果写进私有 staging 目录。
3. **发布**：把完成的 staging 目录切换成 ``public/``，失败就恢复旧树。

路由约定：

* ``content/posts/name.md``                  -> ``/posts/name/``
* ``content/posts/``                         -> ``/posts/`` 归档
* ``content/<any>/index.md``                 -> ``/<any>/``
* ``content/posts/**`` 永远不是自定义页面
* 首页由 ``/`` 生成，不来自 content
* 每次构建都输出 ``/404.html``（本地化错误页）和 ``/robots.txt``

自定义页面故意不可见，不会进入导航。
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
    """项目无法安全或完整地渲染。"""


@dataclass(frozen=True, slots=True)
class BuildResult:
    """给 CLI 的事实摘要，而不是日志副作用。"""

    output_dir: Path
    posts: int
    pages: int
    assets: int
    favicon: str | None
    duration_seconds: float


@dataclass(frozen=True, slots=True)
class OutputFile:
    """一个已渲染完成、等待写入的文件。"""

    relative_path: Path
    content: str


@dataclass(frozen=True, slots=True)
class PreparedSite:
    """内容/模板处理阶段可能失败的全部产物。

    构建这个对象不碰任何输出目录；预检失败必须让旧 public/ 原样保留。
    """

    favicon: str | None
    posts: tuple[Post, ...]
    pages: tuple[Page, ...]
    files: tuple[OutputFile, ...]


@dataclass(frozen=True, slots=True)
class Pagination:
    """首页某一页的模板分页状态。"""

    current_page: int
    total_pages: int
    previous_url: str | None
    next_url: str | None


def _humanize_route(route: str) -> str:
    """index.md 开头没有 H1 时的回退标题。"""

    last = route.rsplit("/", 1)[-1] or route
    words = last.replace("_", " ").replace("-", " ").strip()
    return words.title() if words else "Page"


def _pagination_url(page_number: int) -> str:
    """第 1 页是首页；后续页使用干净的 /page/n/ URL。"""

    return "/" if page_number == 1 else f"/page/{page_number}/"


class Builder:
    """渲染位于 ``root`` 的一个 ByggLeaf 项目。"""

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
        """恰好两个链接，按配置语言本地化。"""

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
        """当前正在渲染的私有目录。"""

        if self._staging_dir is None:
            raise BuildError("build staging directory is not initialized")
        return self._staging_dir

    # -- 公共入口 -----------------------------------------------------------

    def build(self) -> BuildResult:
        started = time.perf_counter()

        # 先恢复上一次发布中途被强杀留下的临时目录。
        self._recover_publication()

        # 阶段 1：校验并在内存中渲染全部内容；成功之前不触碰任何输出路径。
        prepared = self._preflight()

        # 阶段 2：落地到私有 staging 目录；此时内容与模板错误已不可能发生。
        staging = Path(
            tempfile.mkdtemp(prefix=".byggleaf-build-", dir=self.root)
        )
        self._staging_dir = staging
        assets = 0
        try:
            # mkdtemp 默认 0700；发布出去的页面应保持可读。
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
        """解析全部内容、在内存渲染全部 HTML，不写任何输出。

        这是失败策略的 D 阶段：Markdown 错误、非法 front matter、模板异常、
        缺失模板，都会在 staging 目录创建之前被捕获。
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
        """复制资源，把预渲染的 HTML 写入 staging 目录。"""

        assets = self._copy_stylesheet()
        assets += self._copy_user_assets()
        for rendered in prepared.files:
            self._write_output(rendered.relative_path, rendered.content)
        return assets

    # -- 校验与文件系统 -----------------------------------------------------

    def _validate_project(self) -> None:
        if not self.content_dir.is_dir():
            raise BuildError(
                f"{self.content_dir} is missing; run `byggleaf init` first"
            )

        stylesheet = PACKAGE_ASSETS / "css" / "style.css"
        if not stylesheet.is_file():
            raise BuildError(f"packaged stylesheet is missing: {stylesheet}")

        if self.output_dir.is_symlink():
            # 拒绝递归删除不属于我们的东西。
            raise BuildError(
                f"{self.output_dir} is a symlink; run `byggleaf clean` and build again"
            )
        if self.output_dir.exists() and not self.output_dir.is_dir():
            raise BuildError(
                f"{self.output_dir} exists but is not a directory; "
                "run `byggleaf clean` and build again"
            )

    def _recover_publication(self) -> None:
        """修复上一次发布途中被强杀留下的残留。

        public/ 缺失但存在备份时，恢复最新的备份；public/ 存在则备份都是
        过期物；staging 目录永远可丢弃，在下一次构建开始时清理。
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
        """把完成的 staging 目录切换到位。

        先把旧目录改名挪开；新树无法就位就恢复旧目录。``public/`` 不存在的
        窗口只有两次本地 rename 之间。
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
            # 新站已上线；清理备份失败不算构建失败，
            # 这个隐藏目录之后删除也是安全的。
            shutil.rmtree(backup, ignore_errors=True)

    def _detect_favicon(self) -> str | None:
        """只在用户资源目录里找；没有文件就是没有图标，不是错误。"""

        candidate = self.assets_dir / "img" / "favicon.ico"
        return "/assets/img/favicon.ico" if candidate.is_file() else None

    def _copy_stylesheet(self) -> int:
        source = PACKAGE_ASSETS / "css" / "style.css"
        target = self._target / "assets" / "css" / "style.css"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return 1

    def _copy_user_assets(self) -> int:
        """只复制媒体；用户 CSS/JS 没有进入页面的支持路径。"""

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

    # -- 内容发现 -----------------------------------------------------------

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

        # 最新在前；日期相同时用标题做稳定排序。
        posts.sort(
            key=lambda post: (post.published_timestamp, post.title),
            reverse=True,
        )
        return posts

    def _load_pages(self) -> list[Page]:
        """发现除 content/posts/ 里的文件之外的每个 index.md。"""

        pages: list[Page] = []
        for path in sorted(self.content_dir.rglob("index.md")):
            if not path.is_file():
                continue
            relative = path.parent.relative_to(self.content_dir)
            if not relative.parts:
                continue  # content/index.md 会与首页冲突
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

    # -- 渲染 ----------------------------------------------------------------

    def _render_site(
        self,
        posts: list[Post],
        pages: list[Page],
        favicon: str | None,
    ) -> list[OutputFile]:
        """把每个页面、feed 与 sitemap 条目渲染到内存。"""

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

        # 错误页也是真实文档（同一套骨架、本地化文案），但刻意不进入
        # sitemap、也不输出 SEO 元数据：爬虫既不应列出也不应索引它。
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
        """两个生成文件占用同一路径时让预检失败。"""

        seen: set[str] = set()
        for output in files:
            key = output.relative_path.as_posix()
            if key in seen:
                raise BuildError(f"output path conflict: /{key}")
            seen.add(key)

    def _paginate(self, posts: list[Post]) -> list[tuple[int, list[Post], Pagination]]:
        """按配置的每页数量，把文章切成首页分页。"""

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
