"""ByggLeaf：一个刻意保持小巧的静态网站生成器。

包根只做一件事：从 :mod:`byggleaf.core.version` 转出版本号，不导入任何入口
模块。真正的入口只有安装后的 ``byggleaf`` console script，包内刻意不提供
``__main__.py``。

依赖方向由 tests/test_architecture.py 守卫，任何模块都不反向指回 app.py：

    app.py  ->  cli.py, core/*
    cli.py  ->  仅标准库
    core/*  ->  core/*、标准库、markdown、jinja2
"""

from .core.version import VERSION as __version__

__all__ = ["__version__"]
