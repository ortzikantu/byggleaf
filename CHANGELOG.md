# 变更日志

本文件记录 ByggLeaf 的重要变更。版本号的唯一来源是 `pyproject.toml`。

## 未发布

### 新增

- 每次构建生成 `robots.txt`（允许全部爬虫；`baseurl` 非空时指向 sitemap 绝对地址）。
- 每次构建生成本地化 `404.html`（沿用统一头部/导航/页脚，不进 sitemap）；
  `byggleaf serve` 对缺失路径回退到它并返回真实 404 状态码。

### 修复

- `byggleaf --version` 与 `--help` 不再依赖已安装的第三方包：
  `app.py` 延迟导入 core 服务，没有 `markdown`/`jinja2` 的环境也能查看版本。
- 修正 README 中关于 `exampleSite/` 的描述（该目录从未随仓库分发）。
- HTML 消毒器按标签栈深度丢弃嵌套的可执行标签，内部文本不再从
  内层闭合标签处泄漏。
- 补充 server / app / version 低覆盖模块的测试与 HTML 消毒器边界测试。
- CI 与发布流程的 wheel 冒烟改在无第三方依赖的全新 venv 中执行。

### 变更

- 版本展示统一带 `v` 前缀（`ByggLeaf v0.1.0`）：页脚、generator meta、RSS
  与 `--version` 输出一致；`core/version.py` 收敛为
  「源码 pyproject → 发行 metadata → `0.0.0`」三级回退。

## 0.1.0

初始发布：Markdown 文章与独立页面、分页、固定模板、原生 CSS、零 JavaScript、
构建/预览/清理命令、文章 SEO 与内置界面翻译。

- 首页、分页页和独立页面输出 canonical、description 与 Open Graph 元数据。
- 自动生成 `sitemap.xml` 与 `rss.xml`，所有页面 `<head>` 增加发现链接。
- 构建开始时自动恢复中断的发布，并清理遗留 staging 目录。
- 预检阶段增加输出路径冲突检测；发布失败时恢复旧 `public/`。
- 语言文件按规范 BCP 47 标签精确匹配，不再提供地区回退；
  缺少或为空的翻译 key 显示 key 名，不中断构建。
- 增加 HTML/无障碍结构测试、HTTP 预览冒烟测试与本地化数据驱动测试。
- CI 增加 Ruff、mypy、覆盖率、wheel 构建和安装冒烟；
  tag push 后由 `publish.yml` 自动校验、构建、发布 PyPI 并创建 GitHub Release。
- README 增加本地化状态表与发布恢复方案说明，CONTRIBUTING 增加本地化指南。
- 使用 GPL-3.0-or-later 许可证。
