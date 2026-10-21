"""基于标准库的本地预览服务器。

让 CLI 不用引入 Web 框架就能预览 ``public/``。``serve`` 会一直阻塞到被中断，
关闭 socket、捕获 Ctrl+C 交给调用方处理，``app.py`` 会把它变成平静的退出。
"""

from __future__ import annotations

import os
from collections.abc import Callable
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from typing import BinaryIO


class ServerError(RuntimeError):
    """预览目录或监听地址无效。"""


# 与 cli.DEFAULT_HOST / cli.DEFAULT_PORT 保持一致：CLI 不能导入 core，
# 两层各自携带同一个小常量，并由测试钉住。
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 6789


class _PreviewHandler(SimpleHTTPRequestHandler):
    """朴素的文件服务器，预览期间禁用缓存。

    缺失路径会回退到构建出的 ``404.html`` 并返回真实的 404 状态码，
    让预览行为和正式静态托管一致。
    """

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def send_response(self, code: int, message: str | None = None) -> None:
        if getattr(self, "_serving_custom_404", False):
            code = 404
        super().send_response(code, message)

    def send_head(self) -> BytesIO | BinaryIO | None:
        self._serving_custom_404 = False
        target = self.translate_path(self.path)
        if not os.path.exists(target):
            fallback = os.path.join(self.directory, "404.html")
            if os.path.isfile(fallback):
                self.path = "/404.html"
                self._serving_custom_404 = True
        return super().send_head()


def make_server(
    directory: Path,
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> ThreadingHTTPServer:
    """创建（但不启动）预览服务器。

    单独暴露，便于测试绑定临时端口、请求页面并确定性地关闭。
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
    """通过 HTTP 提供 ``directory``，直到进程被中断。

    默认只绑定回环地址；传 ``host="0.0.0.0"``（或命令行 ``--bind 0.0.0.0``）
    可暴露到局域网。``on_ready`` 在 socket 绑定成功后收到展示 URL，
    这样绑定失败时不会先打印误导性的 "serving..."。
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
