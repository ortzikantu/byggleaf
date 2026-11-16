# 变更日志

本文件记录 ByggLeaf 的重要变更。版本号的唯一来源是 `pyproject.toml`。

## 0.1.4

### 变更

- 包元数据的作者改为 `Hao Wu <hao.wu@ortzikantu.com>`。
- 贡献政策明确：不接受 Pull Request，只接受经过 GPG 签名的补丁；不接受未经
  制作者或提交者过目、审阅的 AI 翻译与 AI 代码。

- 文章底部的上下篇改为「左新右旧」：左边通往更新的文章、右边通往更旧的文章，
  文案复用分页已有的较新/更早；只有一侧时各守自己那一端。
- 文章列表的摘要取消 58ch 宽度上限，铺满正文栏；首页分区标题加了一道陶土短杠
  并略微放大。
- 移除「有主见」「仁慈独裁者」等表述，README、包描述与示例 statement 页同步。

### 新增

- `byggleaf init` 现在会写出 `.gitignore`，忽略 `public/`、`.byggleaf-*`、
  `.venv/`、`venv/`、`build/`、`dist/`、`__pycache__/` 等构建产物与本地环境。
- `byggleaf new content` 生成的文章 front matter 预置全部受支持字段
  （`title`、`date`、`updated`、`author`、`tags`、`draft`、`license`、`license_url`）。
- `byggleaf build` 的摘要新增 `version` 行，直接打印当前版本号：换过安装、
  改过版本号或打开旧 `public/` 时，不会再分不清构建用的是哪一版。

## 0.1.3

### 新增

- 文章底部新增两段：上一篇/下一篇（只有标签与箭头，左右分布，取代原来的
  「全部文章」按钮）与许可声明。
- `[site].license` / `license_url` 与文章 front matter 同名键：许可文字原样显示，
  前面只加一个本地化前缀；有链接时同时输出 `<head rel="license">`；都没写则
  整块不显示。
- 文章 front matter 支持 `draft = true`：草稿默认不进入首页、RSS 与 sitemap，
  `byggleaf build --drafts` 时才构建。默认构建不会碰草稿，所以草稿可以先只写半分；
  用 `--drafts` 预览时草稿必须是完整文章（要有 title 与 date）。
- 独立页面（`content/<目录>/index.md`）也接受 front matter：`title` 覆盖正文 H1，
  `draft` 让页面不发布。

### 变更

- front matter 不再做类型审判：`author` 不是字符串就当没写，`tags` 里非字符串的条目
  被丢弃，`updated` 解析失败就当没写。未知键原样保留在 `post.meta` / `page.meta`
  中，是否使用由模板决定。
- 移除配置层的 URL scheme 审查：`[site].baseurl` 与 `[[projects]].url` 按原样采用，
  不再因为 `javascript:` 之类的值中断构建；站点配置和 Markdown 内容一样由作者负责。
- `baseurl` 含空白字符不再报错；`[[projects]].url` 变为可选。
- `---` front matter 只做机械切分：缺少冒号、空键、引号未闭合或引号内不是合法
  字面量，都原样保留为字符串，不再抛错。
- 没有 `content/` 目录不再报错：项目会构建出一个只有首页骨架的空花园。
- `[site].language` 没有对应翻译文件时回退英语并在构建摘要里说明，不再中断构建。
- `404.html` 不再输出 description、canonical 与 Open Graph 元数据：错误页不应被
  索引或分享，保留 `<title>`、`lang`、导航与页脚即可。
- 文章页的 `og:title` 现在与 `<title>` 及其他页面一致，带上 ` · 站点标题` 后缀；
  标题与 SEO 元数据统一由构建器计算，模板不再各自拼接。

## 0.1.2

### 变更

- 移除 Markdown 渲染流程中的自定义 HTML 安全过滤器：用户写入 Markdown 的原始
  HTML 按底层 `markdown` 渲染器的输出原样保留，由内容作者自行负责；ByggLeaf 只
  保证自身模板、样式与静态资源不含 JavaScript。`baseurl` 对本地链接与资源 URL
  的重写保持不变。
- 移除 CLI 的 ANSI 颜色输出：`NO_COLOR` / `FORCE_COLOR` 逻辑、颜色常量与未使用的
  `Console.accent` 一并删除，终端输出改为纯文本。
- 收敛死代码：简化 CLI 命令分发与 `init` 的配置写入分支，删除 Markdown front
  matter 中不可达的类型检查与未使用的 URL 重写属性。

## 0.1.1

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
- 配置层拒绝可执行 URL 方案：`baseurl` 与 `projects[].url` 出现
  `javascript:` 等方案时在解析阶段报错，守住「生成页面零 JavaScript」的承诺。
- 版本解析对祖先目录里的陌生/损坏 pyproject 容错，不再因展示信息崩溃站点。
- 带 UTF-8 BOM 的页面文件不再丢失标题（此前只有文章路径剥 BOM）。
- `serve` 对路径穿越请求一律 404，并锁定为回归测试。
- 补充 server / app / version 低覆盖模块的测试与 HTML 消毒器边界测试。
- CI 与发布流程的 wheel 冒烟改在无第三方依赖的全新 venv 中执行。

### 变更

- 版本展示统一带 `v` 前缀（`ByggLeaf v0.1.1`）：页脚、generator meta、RSS
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
