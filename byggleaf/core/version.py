"""版本号只在这里解析一次。

``raw_version()`` 给 PEP 440 版本（如 ``1.2.3``），``get_version()`` 给展示
形式（``v1.2.3``）；CLI、generator meta、RSS 和页脚都读这里。

源码检出一律以本项目的 ``pyproject.toml`` 为准，改完立即生效；wheel 里没有
pyproject，就回退到 ``importlib.metadata``；两者都拿不到时用 ``0.0.0`` 兜底。
版本号只是展示信息，不值得我们为它让站点崩溃。
"""

from __future__ import annotations

import tomllib
from pathlib import Path

#: 分发名，与 ``pyproject.toml`` 的 ``[project].name`` 一致。
DISTRIBUTION = "byggleaf"
_FALLBACK = "0.0.0"

_cache: str | None = None


def _installed_version() -> str:
    """已安装分发包的版本；未安装或元数据损坏时返回空串。"""

    from importlib.metadata import PackageNotFoundError, version

    try:
        return str(version(DISTRIBUTION) or "").strip()
    except PackageNotFoundError:
        return ""
    except Exception:  # 元数据损坏也不该拖垮站点
        return ""


def _source_version(start: Path | None = None) -> str:
    """从本文件向上查找最近的 *ByggLeaf* pyproject。

    只认 ``[project].name == DISTRIBUTION`` 的文件：虚拟环境若建在别的项目
    目录里，不会误取别人的版本号。
    """

    base = (start or Path(__file__).resolve().parent).resolve()
    for candidate in (base, *base.parents):
        pyproject = candidate / "pyproject.toml"
        if not pyproject.is_file():
            continue
        try:
            with pyproject.open("rb") as handle:
                data = tomllib.load(handle)
        except Exception:
            # 祖先目录里陌生、不可读或病态的 pyproject（恶意嵌套触发
            # RecursionError、元数据损坏等），都不能因为一个展示值拖垮站点。
            continue
        project = data.get("project") or {}
        if str(project.get("name") or "").strip().lower() != DISTRIBUTION:
            continue
        value = str(project.get("version") or "").strip()
        if value:
            return value
    return ""


def raw_version() -> str:
    """返回 PEP 440 版本，进程内只解析一次。"""

    global _cache
    if _cache is None:
        _cache = _source_version() or _installed_version() or _FALLBACK
    return _cache


def get_version() -> str:
    """返回展示形式，如 ``v1.2.3``。"""

    return f"v{raw_version()}"


def reset_cache() -> None:
    """丢弃缓存；测试切换安装状态时使用。"""

    global _cache
    _cache = None


VERSION = get_version()

__all__ = ["VERSION", "get_version", "raw_version", "reset_cache"]
