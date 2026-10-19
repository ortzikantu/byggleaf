# 变更日志

本文件记录 ByggLeaf 的重要变更。版本号的唯一来源是 `pyproject.toml`。

## 未发布

### 新增

- 首页、分页页和独立页面输出 canonical、description 与 Open Graph 元数据。
- 自动生成 `sitemap.xml` 与 `rss.xml`。
- 所有页面 `<head>` 增加 RSS 与站点地图发现链接。
- 构建开始时自动恢复中断的发布，并清理遗留 staging 目录。
- 预检阶段增加输出路径冲突检测。
- 增加 HTML/无障碍结构测试和 HTTP 预览冒烟测试。
- CI 增加 Ruff、mypy、覆盖率、wheel 构建和安装冒烟。
- tag push 后由 `publish.yml` 自动校验、构建、发布 PyPI 并创建 GitHub Release。
- README 增加本地化状态表，CONTRIBUTING 增加本地化指南。
- 使用 GPL-3.0-or-later 许可证。

### 变更

- 语言文件按规范 BCP 47 标签精确匹配，不再提供地区回退。
- 缺少或为空的翻译 key 会显示 key 名，不再中断构建。
- 发布失败时恢复旧 `public/`；下一次构建修复崩溃残留。

## 0.1.0

- 初始版本：Markdown 文章与独立页面、分页、固定模板、原生 CSS、
  零 JavaScript、构建/预览/清理命令、文章 SEO 与内置界面翻译。
