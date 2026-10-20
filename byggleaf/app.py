"""Application assembly point.

``app.py`` is the only module that imports both ``cli`` and ``core``.  The CLI
defines the command surface and receives handlers from this file; core modules
never learn that a command line exists.  This is the seam that keeps the
dependency graph pointing in one direction.

The installed ``byggleaf`` console script lands here.  There is deliberately
no package-level ``__main__.py``: one entry point is enough.

Core services that pull in third-party packages are imported inside the
command handlers rather than at module top.  ``core/version.py`` is
standard-library only, so ``byggleaf --version`` and ``--help`` still work in
an environment without ``markdown``/``jinja2`` (for example a wheel installed
with ``--no-deps`` during the CI smoke test).
"""

from __future__ import annotations

import sys
from pathlib import Path

from . import cli
from .core.version import VERSION


def _display(path: Path, root: Path) -> str:
    """Prefer a short workspace-relative path in terminal summaries."""

    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _cmd_init(options: cli.InitOptions) -> int:
    from .core.scaffold import ScaffoldError, init_site

    console = cli.Console()
    errors = cli.Console(stream=sys.stderr)
    root = options.root.resolve()

    console.heading("init")
    console.item("root", str(root))

    try:
        result = init_site(root, force=options.force)
    except (ScaffoldError, OSError) as exc:
        errors.error(str(exc))
        return 1

    for path in result.created:
        console.item("create", _display(path, root))
    for path in result.skipped:
        console.item("keep", _display(path, root))

    console.success("The garden is ready.")
    console.muted(
        "Next: edit byggleaf.toml, then run `byggleaf build` and `byggleaf serve`."
    )
    return 0


def _cmd_clean(options: cli.CleanOptions) -> int:
    from .core.clean import CleanError, clean_output

    console = cli.Console()
    errors = cli.Console(stream=sys.stderr)
    root = options.root.resolve()

    console.heading("clean")

    try:
        result = clean_output(root)
    except (CleanError, OSError) as exc:
        errors.error(str(exc))
        return 1

    if not result.removed:
        console.muted("public/ is already absent; nothing to do.")
        return 0

    console.item("removed", f"{_display(result.output_dir, root)}/")
    console.success(f"Removed public/ ({result.kind}).")
    return 0


def _cmd_new(options: cli.NewOptions) -> int:
    from .core.new import NewError, create_article

    console = cli.Console()
    errors = cli.Console(stream=sys.stderr)
    root = options.root.resolve()

    console.heading("new")

    try:
        result = create_article(root)
    except (NewError, OSError) as exc:
        errors.error(str(exc))
        return 1

    console.item("create", _display(result.path, root))
    console.item("date", result.published.isoformat(sep=" ", timespec="minutes"))
    console.success("Created a new article.")
    console.muted(
        "Edit the title, author, tags, and body; set updated when you revise it."
    )
    return 0


def _cmd_build(options: cli.BuildOptions) -> int:
    from .core.builder import Builder, BuildError
    from .core.config import CONFIG_FILENAME, ConfigError, load_config
    from .core.jinja import TemplateError
    from .core.locales import LocaleError
    from .core.markdown import MarkdownError

    console = cli.Console()
    errors = cli.Console(stream=sys.stderr)
    root = options.root.resolve()
    public_dir = root / "public"

    console.heading("build")

    try:
        config = load_config(root / CONFIG_FILENAME)
        console.item("site", config.site.title)
        console.item("baseurl", config.site.baseurl or "(root-relative)")
        result = Builder(root, config).build()
    except (
        ConfigError,
        BuildError,
        LocaleError,
        MarkdownError,
        TemplateError,
        OSError,
    ) as exc:
        errors.error(str(exc))
        if public_dir.exists() or public_dir.is_symlink():
            errors.muted(
                "Previous public/ was preserved; no partial output was published."
            )
        else:
            errors.muted("No public/ output was published.")
        errors.muted("Fix the issue above and run `byggleaf build` again.")
        return 1

    console.item("output", f"{_display(result.output_dir, root)}/")
    console.item("posts", str(result.posts))
    console.item("pages", str(result.pages))
    console.item("assets", str(result.assets))
    if result.favicon:
        console.item("favicon", result.favicon)
    console.success(f"Built in {result.duration_seconds * 1000:.0f} ms.")
    return 0


def _cmd_serve(options: cli.ServeOptions) -> int:
    from .core.config import CONFIG_FILENAME, ConfigError, load_config
    from .core.server import ServerError, serve

    console = cli.Console()
    errors = cli.Console(stream=sys.stderr)
    root = options.root.resolve()
    public_dir = root / "public"

    console.heading("serve")

    if not public_dir.is_dir():
        errors.error("public/ does not exist; run `byggleaf build` first")
        return 1

    configured_baseurl = ""
    try:
        configured_baseurl = load_config(root / CONFIG_FILENAME).site.baseurl
    except ConfigError:
        # A preview of already-built files should still work without a config.
        pass

    def ready(url: str) -> None:
        console.item("bind", f"{options.host}:{options.port}")
        console.item("local", url)
        console.item("root", f"{_display(public_dir, root)}/")
        if options.host in {"0.0.0.0", "::"}:
            console.muted(
                "Bound to all interfaces; use this machine's LAN IP "
                "from another device."
            )
        if configured_baseurl:
            local_prefixes = (
                f"http://127.0.0.1:{options.port}",
                f"http://localhost:{options.port}",
                f"http://{options.host}:{options.port}",
            )
            if not any(
                configured_baseurl == prefix
                or configured_baseurl.startswith(prefix + "/")
                for prefix in local_prefixes
            ):
                console.muted(
                    f"note: pages use baseurl {configured_baseurl!r}; "
                    'set [site] baseurl = "" for a purely local preview.'
                )
        console.muted("Press Ctrl+C to stop.")

    try:
        serve(
            public_dir,
            host=options.host,
            port=options.port,
            on_ready=ready,
        )
    except ServerError as exc:
        errors.error(str(exc))
        return 1
    except OSError as exc:
        errors.error(str(exc))
        return 1
    return 0


def handlers() -> cli.Handlers:
    """Wire command names to the application services they are allowed to use."""

    return cli.Handlers(
        init=_cmd_init,
        build=_cmd_build,
        clean=_cmd_clean,
        new=_cmd_new,
        serve=_cmd_serve,
    )


def main(argv: list[str] | None = None) -> int:
    """Console-script entry point."""

    return cli.main(argv, handlers=handlers(), version=VERSION)
