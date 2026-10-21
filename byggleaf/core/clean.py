"""安全删除生成目录。

``clean`` 刻意比 ``rm -rf`` 窄，只碰 ``public/``，不碰内容、配置和资源；
符号链接只删链接本身、绝不跟随，免得误删项目之外的目录。
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path


class CleanError(RuntimeError):
    """生成目录无法删除。"""


@dataclass(frozen=True, slots=True)
class CleanResult:
    """记录 clean 实际发现了什么、做了什么。"""

    output_dir: Path
    removed: bool
    kind: str


def clean_output(root: Path) -> CleanResult:
    """删除 ``<root>/public`` 并返回事实结果。

    目标不存在视为成功（幂等）；``public`` 是符号链接时只 unlink、不进入；
    普通目录则递归删除。
    """

    root = Path(root).resolve()
    output = root / "public"

    if not output.exists() and not output.is_symlink():
        return CleanResult(output_dir=output, removed=False, kind="missing")

    try:
        if output.is_symlink():
            output.unlink()
            kind = "symlink"
        elif output.is_dir():
            if os.path.ismount(output):
                raise CleanError(
                    f"{output} is a mount point; refusing to remove it"
                )
            shutil.rmtree(output)
            kind = "directory"
        else:
            # 普通文件与特殊条目直接 unlink，绝不跟随链接
            #（符号链接已在上面的分支处理）。
            output.unlink()
            kind = "file"
    except OSError as exc:
        raise CleanError(f"cannot remove {output}: {exc}") from exc

    return CleanResult(output_dir=output, removed=True, kind=kind)
