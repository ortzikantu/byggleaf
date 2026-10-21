"""Jinja2 渲染基础设施。

模板只从安装包内加载，刻意不指向用户项目——自定义 HTML 模板不是支持的功能，
用户只写 Markdown，排版交给工具。

模板布局保持扁平、名字短而直接：

    base.html      公共骨架（head/导航/页脚）
    home.html      带分页的首页
    post.html      文章详情
    page.html      独立页面
    postlist.html  首页文章流
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from jinja2 import (
    Environment,
    FileSystemLoader,
    StrictUndefined,
    select_autoescape,
)
from jinja2 import (
    TemplateError as JinjaTemplateError,
)

from .config import Config, absolute_url
from .locales import Locale
from .version import VERSION

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


class TemplateError(RuntimeError):
    """包内模板缺失或渲染失败。"""


def format_date(value: object) -> str:
    """安静地格式化日期：只有带时间时才显示时间。"""

    if isinstance(value, dt.datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    if isinstance(value, dt.date):
        return value.strftime("%Y-%m-%d")
    return str(value)


class TemplateEngine:
    """已配置的 Jinja 环境，并注入全局 URL 辅助函数。"""

    def __init__(self, config: Config, locale: Locale) -> None:
        if not TEMPLATES_DIR.is_dir():
            raise TemplateError(f"packaged templates directory is missing: {TEMPLATES_DIR}")

        self.config = config
        self.locale = locale
        self.environment = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=select_autoescape(enabled_extensions=("html", "xml")),
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
            auto_reload=False,
        )
        # 所有模板的 URL 都走这个函数，baseurl 拼接规则只需在一处维护。
        self.environment.globals["url"] = lambda path: absolute_url(
            config.site.baseurl, path
        )
        self.environment.globals["version"] = VERSION
        self.environment.globals["ui"] = locale.text
        self.environment.filters["datefmt"] = format_date

    def render(self, template_name: str, **context: object) -> str:
        """渲染包内模板，并预先绑定站点配置。"""

        context.setdefault("site", self.config.site)
        context.setdefault("projects", self.config.projects)
        try:
            template = self.environment.get_template(template_name)
            return template.render(**context)
        except (JinjaTemplateError, OSError, UnicodeError) as exc:
            raise TemplateError(f"template {template_name!r} failed: {exc}") from exc
