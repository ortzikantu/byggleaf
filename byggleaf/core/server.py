"""Local preview server built on the standard library.

This module exists so the CLI never needs a web framework.  ``serve`` blocks
until interrupted; closing the socket and catching Ctrl+C is the caller's
concern (``app.py`` turns it into a calm exit).
"""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class ServerError(RuntimeError):
    """The preview directory or server address is invalid."""


# Keep in sync with cli.DEFAULT_HOST / cli.DEFAULT_PORT.  The CLI may not
# import core, so the two layers intentionally carry the same tiny constants.
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 6789


class _PreviewHandler(SimpleHTTPRequestHandler):
    """A plain file server that politely refuses to cache during preview."""

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def make_server(
    directory: Path,
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> ThreadingHTTPServer:
    """Create (but do not start) a preview server.

    Exposed separately so tests can bind an ephemeral port, request pages, and
    shut the server down deterministically.
    """

    directory = Path(directory).resolve()
    if not directory.is_dir():
        raise ServerError(
            f"{directory} does not exist; run `byggleaf build` before `byggleaf serve`"
        )

    handler = partial(_PreviewHandler, directory=str(directory))
    try:
        return ThreadingHTTPServer((host, port), handler)  # type: ignore[arg-type]
    except OSError as exc:
        raise ServerError(f"cannot serve {directory} on {host}:{port}: {exc}") from exc


def serve(
    directory: Path,
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    on_ready: Callable[[str], None] | None = None,
) -> None:
    """Serve ``directory`` over HTTP until the process is interrupted.

    The default is deliberately loopback-only.  Pass ``host="0.0.0.0"`` (or
    ``--bind 0.0.0.0`` on the command line) to expose the preview on a LAN.
    ``on_ready`` receives the display URL *after* the socket has been bound, so
    a bind error is reported without a misleading "serving..." message.
    """

    httpd = make_server(directory, host=host, port=port)
    actual_port = httpd.server_address[1]

    display_host = host
    if host in {"0.0.0.0", "::"}:
        display_host = "127.0.0.1"
    if ":" in display_host and not display_host.startswith("["):
        display_host = f"[{display_host}]"

    with httpd:
        if on_ready is not None:
            on_ready(f"http://{display_host}:{actual_port}/")
        httpd.serve_forever()
