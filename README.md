# ByggLeaf

**无 JavaScript，无废话。你的数字花园的仁慈独裁者。**

ByggLeaf 是一个极致克制、有主见的静态网站生成器。你写 Markdown，它负责排版。
没有主题系统，没有自定义模板，没有自定义 CSS/JS，没有外部 Web 字体。只有一条
65ch 宽、居中、使用系统原生衬线体的阅读栏。

- Python 3.11+
- 仅依赖 `markdown` 与 `jinja2`
- 纯原生 CSS，构建时自动复制包内 `style.css`
- 生成的页面零 JavaScript
- 所有资源链接统一由 `baseurl` 拼接
- 页面 `<head>` 输出版本化 generator，页脚输出版本化 Built with
- 内置英语、日语、韩语、粤语、简体中文、繁体中文界面
- 自动生成 `sitemap.xml`、`rss.xml`、`robots.txt` 与本地化 `404.html`

## 项目边界

**ByggLeaf 不是通用 SSG，也从不打算成为通用 SSG。**

它只服务一个目标：把一个人的 Markdown 数字花园，以一套固定、克制、可预测的
方式排版成静态网站。它是仁慈独裁者制作的专用工具，不是平台。

以下内容不在路线图中：

- 主题市场、主题变量、主题继承
- 用户自定义模板、插件系统、钩子
- 自定义 CSS/JS、外部字体、第三方统计
- 通用内容类型、任意输出管线、增量构建缓存
- 多站点管理、后台、评论、搜索服务

如果你需要这些能力，Hugo、Eleventy、Astro 等通用工具更合适。ByggLeaf 的
克制是产品承诺，不是待补齐的功能缺口。

## 快速开始

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .

mkdir my-garden && cd my-garden
byggleaf init
# 编辑 byggleaf.toml 中的 title / baseurl / copyright
byggleaf new content
byggleaf build
byggleaf serve
```

`byggleaf clean` 只删除 `public/`，不会碰 `content/`、`assets/` 和配置：

```bash
byggleaf clean
```

`byggleaf serve` 默认在 <http://127.0.0.1:6789/> 预览已经构建好的 `public/`。
它不会隐式重新构建，也不会启动第二个构建流程。

默认只绑定回环地址。要从局域网访问，可显式绑定所有接口：

```bash
byggleaf serve --bind 0.0.0.0
# 另一台设备访问：http://<这台机器的局域网 IP>:6789/
```

`--host 0.0.0.0` 是 `--bind` 的兼容别名；端口默认为 `6789`，仍可通过
`--port` 临时覆盖。

> **本地预览与 baseurl**：生成的页面严格使用 `[site].baseurl`。如果它是
> `https://example.com`，本地打开时浏览器会去请求线上域名。纯本地预览时把
> `baseurl = ""`（生成根相对路径），或设为 `http://127.0.0.1:6789`。
> `serve` 检测到这种不一致时会给出提示。

## 示例站点

`byggleaf init` 自带一篇示例文章（`content/posts/hello-world.md`）和
`about`、`statement` 两个独立页面。用 `byggleaf new content` 再补几篇
即可体验分页：`posts_per_page = 5`（默认）时，11 篇文章会生成 3 页。

```bash
byggleaf init
byggleaf new content   # 重复执行，凑够想要的文章数
byggleaf build
byggleaf serve
```

打开 <http://127.0.0.1:6789/> 即可查看首页文章流和翻页效果。

## 工作区

```text
my-garden/
├── byggleaf.toml
├── assets/
│   ├── img/          # 图片；favicon.ico 在这里才显示图标
│   ├── video/
│   └── audio/
└── content/
    ├── posts/
    │   └── hello-world.md
    ├── about/
    │   └── index.md
    └── statement/
        └── index.md
```

`init` 只会创建缺失的文件。已有 `byggleaf.toml` 时默认拒绝执行；显式使用
`byggleaf init --force` 才会覆盖生成的文件（不会删除你的其他内容）。

## 内容约定

### 文章

`content/posts/*.md` 使用 TOML front matter：

```markdown
+++
title = "New Article"
date = 2026-10-18T14:30:00
updated = ""
author = ""
tags = []
+++

正文从这里开始。
```

字段说明：

- `date`：发布日期，也参与倒序排序；支持日期或日期时间。
- `updated`：编辑日期，可留空；只在文章页显示，不参与排序。
- `author`：作者名，留空则不显示；填写后显示在文章头部和 SEO meta 中。
- `tags`：仅用于 SEO，不生成标签页或标签链接；可写 `["a", "b"]`，
  也兼容 `tag = "a, b"` 字符串。

新建文章：

```bash
byggleaf new content
```

会从包内 `resources/article.example.md` 创建 `content/posts/new-article.md`，自动写入当前
日期时间、标题 `New Article`，并预留 `updated`、`author`、`tags` 字段。
如果文件已存在，会继续创建 `new-article-2.md`，不会覆盖已有文章。

按 `date` 倒序生成：

- `/` 首页文章流，第 1 页
- `/page/2/`、`/page/3/`……后续分页
- `/posts/<文件名>/` 文章详情

不生成 `/posts/` 归档页。首页的文章流就是完整归档，通过分页浏览后续文章。
每页文章数由 `[site].posts_per_page` 控制。文章详情页的 `← All posts` 会回到
该文章所属的分页：第 1 页返回 `/`，第 2 页返回 `/page/2/`，依此类推。

正文开头如果有一个与 `title` 完全相同的 H1，会被自动移除，避免标题重复。
`---` 分隔的简单 YAML front matter 也可识别，但只解析扁平的 `key: value`，
TOML 是推荐格式。

### 页面搜索引擎优化

所有页面都会输出：

- `description`：文章页使用首页同款第一段摘要；独立页面使用正文第一段；
  首页使用 `hero_subtitle`，为空时回退站点标题。
- `canonical` 与 `og:url`：使用 `baseurl` 拼接当前页面绝对地址。
- `og:type`、`og:title`、`og:description`、`og:site_name`。
- `<html lang>` 使用规范化后的 `[site].language`。
- RSS 自动发现链接与 sitemap 链接。

文章页还会额外输出：

- `author`：仅在填写 `author` 时输出。
- `keywords`：由 `tags` 拼接。
- `article:published_time`、`article:modified_time`（有 `updated` 时）。
- `article:author` 与逐条 `article:tag`。

分页页面的 canonical 是自身，例如 `/page/2/`，不会把第 2 页 canonical 到首页。
这些都是纯 HTML meta，不引入 JSON-LD 或脚本。

### 站点地图与 RSS

每次构建自动生成：

```text
public/sitemap.xml
public/rss.xml
```

- `sitemap.xml` 包含首页、所有分页页、全部文章和全部独立页面；
  文章带 `lastmod`（优先 `updated`）。
- `rss.xml` 包含全部文章，输出标题、绝对链接、guid、发布日期、摘要、
  作者和 tags。
- 所有页面 `<head>` 都会声明 RSS 与 sitemap：

```html
<link rel="alternate" type="application/rss+xml" ... href=".../rss.xml">
<link rel="sitemap" type="application/xml" href=".../sitemap.xml">
```

- RSS/sitemap 中的站点链接同样由 `baseurl` 拼接。发布 RSS 时请把
  `baseurl` 设为真实的绝对地址。

### robots.txt 与 404 页面

每次构建还会生成：

```text
public/robots.txt
public/404.html
```

- `robots.txt` 允许全部爬虫；`baseurl` 非空时指向 sitemap 的绝对地址，
  为空（纯本地预览）时省略 Sitemap 行。
- `404.html` 是本地化的「页面未找到」页面，沿用统一的头部、导航与页脚，
  不会进入 sitemap。多数静态托管（如 GitHub Pages）会自动把它用作错误页；
  本地 `byggleaf serve` 也会把缺失路径回退到它并返回真实的 404 状态码。

### 独立页面

除 `posts/` 外，任何包含 `index.md` 的文件夹都会生成
`/<文件夹路径>/index.html`。页面标题取正文开头的 H1；没有 H1 时使用文件夹名。

这些页面**不会**自动进入导航栏。导航栏只有 Home / About 两个链接。
例如 `content/statement/index.md` 会生成 `/statement/`，但它是隐藏页面。

### 站点图标

`byggleaf init` 会把包内的默认 `favicon.ico` 复制到 `assets/img/`。
构建器只在这个位置寻找它；删除后构建会安静地忽略 favicon，不报错。

## 配置

```toml
[site]
title = "My Digital Garden"
hero_subtitle = "用代码和文字记录生活。"
baseurl = "https://example.com"
copyright = "Your Name"
language = "zh-CN"
posts_per_page = 5

[[projects]]
name = "Example"
url = "https://github.com/example/example"
description = "Example."
```

`title` 和 `baseurl` 必填（`baseurl` 可以是空字符串）。`projects` 会渲染在首页
项目列表。`posts_per_page` 是正整数，默认 `5`，决定首页每页显示多少篇文章。
`language` 必须是规范的 BCP 47 语言标签，并且必须存在同名语言文件；当前内置
`en`、`ja`、`ko`、`yue`、`zh`、`zh-CN`、`zh-HK`。它同时决定 `<html lang>` 和界面文案。
没有 `[theme]`、`[extra_css]` 或其他逃生舱。

## 架构

包内只保留一个入口脚本和一个装配点，`scaffold` 归入 `core/`：

```text
byggleaf/
├── __init__.py
├── app.py
├── cli.py
├── core/
│   ├── __init__.py
│   ├── builder.py
│   ├── clean.py
│   ├── config.py
│   ├── jinja.py
│   ├── locales.py
│   ├── markdown.py
│   ├── new.py
│   ├── scaffold.py
│   ├── seo.py
│   ├── server.py
│   └── version.py
├── assets/
├── templates/
├── resources/
└── locales/
```

依赖方向严格单向，并由测试守卫：

```text
app.py  ──>  cli.py
   │           (只依赖标准库)
   └──────>  core/*  ──>  builder / clean / config / markdown / jinja /
                           locales / new / scaffold / seo / server / version
                           (只依赖标准库 + markdown + jinja2；内部可单向调用)
```

- `app.py` 是唯一同时认识 `core` 与 `cli` 的装配点。
- `app.py` 延迟导入依赖第三方包的 core 服务：`--version` 与 `--help`
  在没有 `markdown`/`jinja2` 的环境里也能运行。
- `cli.py` 只定义命令和参数，通过注入的 handlers 调用应用服务，不导入 core。
- `core/*` 绝不反向导入 `app` 或 `cli`；`scaffold` 也是 core 的普通服务模块。
- 包内没有 `__main__.py`：唯一入口是安装后的 `byggleaf` console script。
- `core/version.py` 从 `pyproject.toml` 读取版本；wheel 安装时回退到发行版 metadata。
- `assets/`、`templates/`、`resources/` 是纯数据，不含 Python 逻辑。
- 没有用户模板目录：Jinja 只从安装包内部加载模板。

### 模板布局

模板保持扁平，不为了“目录感”制造层级：

```text
templates/
├── base.html      # 页面骨架 + head + 导航 + footer
├── 404.html       # 本地化「页面未找到」
├── home.html      # 首页（文章流 + 分页）
├── post.html      # 文章详情
├── page.html      # about/statement 等独立页面
└── postlist.html  # 首页的文章流
```

- 名字保持短、直接：`home` 是首页，`post` 是文章详情，`page` 是独立页面，
  `postlist` 就是文章列表，不再加 `partial` 之类的前后缀。
- 多词命名统一用下划线；当前这组模板都是单词，不需要再制造复合词。
- `base.html` 拥有 head、导航和 footer。它们永远一起变化，拆成多个 partial
  只会增加跳转成本。
- `base.html`、`404.html`、`home.html`、`post.html`、`page.html`、`postlist.html`
  全部平铺，没有模板子目录，也没有用户可以覆盖的布局层。Jinja 只加载包内模板。

### 界面语言

语言解析集中在 `core/locales.py`，内置语言文件位于包内 `locales/`：

```text
locales/
├── en.toml     # English
├── ja.toml     # 日本語
├── ko.toml     # 한국어
├── yue.toml    # 粵語
├── zh.toml     # 中文
├── zh-CN.toml  # 简体中文
└── zh-HK.toml  # 繁體中文
```

语言 ID 不是任意字符串，而是经过校验和规范化的 BCP 47 标签：

- 语言小写、地区大写。
  `zh-hk` → `zh-HK`。
- 标签规范化后写入 `<html lang>`，供浏览器和搜索引擎识别。
- **没有回退机制**：`load_locale()` 只查找与规范化标签完全同名的文件。
- 不符合 BCP 47 形状的写法，例如 `zh_CN`、`chinese`、`zh-CN-`，
  在配置解析阶段就会报错。
- 缺少对应文件时列出全部已有语言文件，并提示贡献翻译：

```text
no translation file for 'zh-SG'; available: en, ja, ko, yue, zh, zh-CN, zh-HK.
Add locales/zh-SG.toml or contribute a translation.
```

- **缺少某个 `[ui]` key，或该 key 的值为空时，页面直接显示 key 名。**
  例如缺少 `home` 会显示 `home`，不会中断构建。
- 内置语言文件仍应保持完整；部分翻译可以加载，但会暴露未翻译的 key。

| 语言 | 代码 | 支持 |
| --- | --- | :---: |
| 英语 | `en` | ✅ |
| 日本語 | `ja` | ✅ |
| 한국어 | `ko` | ✅ |
| 粵語 | `yue` | ✅ |
| 中文 | `zh` | ✅ |
| 简体中文（中国大陆） | `zh-CN` | ✅ |
| 繁體中文（香港） | `zh-HK` | ✅ |
| 简体中文（新加坡） | `zh-SG` | ❌ |
| 繁體中文（台灣） | `zh-TW` | ❌ |
| 繁體中文（澳門） | `zh-MO` | ❌ |
| 粵語（香港） | `yue-HK` | ❌ |
| 英语（美国） | `en-US` | ❌ |
| 简体中文（脚本标签） | `zh-Hans` | ❌ |
| 繁體中文（脚本标签） | `zh-Hant` | ❌ |

✅ 表示包内已有同名 TOML；❌ 表示当前没有文件，配置后会明确报错。
增加语言不需要改代码：复制现有 TOML，按 BCP 47 规范化标签命名，
补齐全部 `[ui]` key，再更新本表和测试即可。详见
[CONTRIBUTING.md](CONTRIBUTING.md#localization)。

翻译覆盖导航、跳到正文链接、段落标题、分页按钮、更新时间、页脚、404 文案、ARIA 标签等
页面 UI，不翻译文章正文和站点配置。

生成页面会包含：

```html
<meta name="generator" content="ByggLeaf v0.1.1">
```

以及 footer：

```html
<p class="colophon">Built with ByggLeaf v0.1.1. No JavaScript, no tracking.</p>
```

版本号直接来自当前的 `pyproject.toml`，不维护第二份字面量。

Markdown 渲染结果还会经过一个小型 HTML 过滤器，移除 `<script>`、事件处理器
和 `javascript:` URL。即使误粘贴了原始 HTML，输出也保持零 JavaScript。

## 构建失败与发布恢复

当前默认采用 **A + D**：先预检，再原子发布。

- **D. 预检**：先校验项目，解析全部文章/页面，并在内存中渲染全部 HTML、
  sitemap 和 RSS；这一步失败时连 staging 目录都不会创建，`public/` 完全不被触碰。
- **输出路径冲突检测**：预检阶段检查所有生成路径。分页页与自定义页面
  争用同一个 `/page/N/` 时直接报错，不会写出其中一个覆盖另一个。
- **A. 原子发布**：预检通过后才写入项目根目录下的 `.byggleaf-build-*` 临时目录。
  全部写入成功后，旧 `public/` 被移到 `.byggleaf-public-*`，新目录再切换为 `public/`。
- **发布失败恢复**：切换失败时立即把旧 `public/` 恢复；写入过程失败时删除临时目录，
  旧站点保持原样。
- **崩溃恢复**：每次构建开始时检查残留：
  - `public/` 缺失但存在 `.byggleaf-public-*` 时，恢复最新的备份；
  - `public/` 已存在时，清理过期备份；
  - 始终清理 `.byggleaf-build-*` staging 残留。
- CLI 会明确提示：旧 `public/` 是否保留、是否发布了任何部分结果、下一步该做什么。

可选方案与取舍：

| 方案 | 做法 | 优点 | 代价 |
| --- | --- | --- | --- |
| A. 原子发布（当前） | staging 构建，成功后目录切换 | 失败不破坏旧站；无半成品 | 需要临时目录，发布时两次本地 rename |
| B. 备份回滚 | 先备份 `public/`，原地构建，失败恢复 | 目录切换更少 | 构建期间旧站可能已被改写，恢复逻辑更重 |
| C. 原地覆盖 + fail-fast | 清空 `public/` 后直接写 | 最简单、最快 | 失败会留下半成品站点，不推荐 |
| D. 先预检再写入（当前） | 先解析全部内容并渲染模板，再写输出 | 内容/模板错误不触碰输出 | 无法防止磁盘/权限等写入阶段失败，因此与 A 组合 |
| E. 保留失败现场 | 失败时保留 staging 供排查 | 调试方便 | 需要显式 `--keep-failed`，否则临时目录会堆积 |

当前组合 **A + D** 覆盖内容错误、模板错误、路径冲突、写入错误、发布切换错误，
并由下一次构建自动处理被强杀后留下的临时目录。不建议退回 C。

## 开发与测试

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

ruff check .
mypy byggleaf
coverage run -m unittest discover -s tests -v
coverage report
python -m build
python -m twine check dist/*
```

CI 在 Python 3.11 与 3.13 上运行同一套门禁，见
[`.github/workflows/ci.yml`](.github/workflows/ci.yml)。

测试使用标准库 `unittest`，并额外包含：

- **HTML/无障碍结构检查**：`lang`、title、唯一 H1、`main#main`、唯一 id、
  meta/canonical/OG、RSS/sitemap 发现链接、图片 alt、无 `<script>`。
- **HTTP 冒烟**：启动真实预览服务器，抓取首页、跟随分页链接到 `/page/2/`，
  并请求 `rss.xml` 与 `sitemap.xml`。
- **本地化数据驱动测试**：扫描 `locales/*.toml`，不维护硬编码语言列表；
  每个文件都必须能加载；缺失或空的 key 会回退显示 key 名。

`tests/test_architecture.py` 还会检查：

- 只有 app 装配 cli 与 core
- core 不导入入口层；scaffold 位于 core 内且不反向依赖
- 包内没有 `__main__.py`，入口收敛为 console script
- 导入图无环
- 第三方依赖只有 `markdown` 和 `jinja2`
- 模板/CSS 中没有 JavaScript、外部字体或 `@import`
- 设计 token 精确匹配，关键静态资源已声明为 package-data
- 版本来自 `pyproject.toml`，并渲染到 generator meta 与页脚
- 模板保持扁平，文件名短而直接；多词命名使用下划线
- 语言文件名本身必须是规范化 BCP 47 标签
- 严格按 BCP 47 规范化标签查找同名文件，不做地区或语言回退
- 首页分页由 `[site].posts_per_page` 控制，不再生成 `/posts/` 归档页
- 详情页 `All posts` 返回文章所属分页
- `new content` 从包内模板生成文章并自动写入日期时间
- 文章 SEO 使用首页同款摘要、可选作者和 tags
- 所有页面都有 canonical、OG、description 和 feed 发现链接
- 构建生成 sitemap.xml、rss.xml、robots.txt 与本地化 404 页面
- 构建先预检全部内容和模板，再进入 staging；失败时旧 `public/` 保留
- 输出路径冲突在预检阶段报错
- 发布失败恢复旧 `public/`；下一次构建恢复崩溃残留
- `byggleaf clean` 删除 `public/`，且不会跟随符号链接
- 构建路由、文章排序、隐藏页面、favicon 行为等端到端结果

## 部署到 GitHub Pages

下面这份工作流是给**你的站点仓库**用的，不放在 ByggLeaf 源码仓库里。把它保存为
站点仓库的 `.github/workflows/pages.yml`。

在站点仓库的 GitHub 设置中启用：

```text
Settings -> Pages -> Build and deployment -> Source: GitHub Actions
```

```yaml
name: pages

on:
  push:
    branches: [main, master]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: true

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install ByggLeaf
        run: python -m pip install byggleaf

      - name: Build with Pages baseurl
        run: |
          set -euo pipefail

          REPO_NAME="${GITHUB_REPOSITORY#*/}"
          if [ "$REPO_NAME" = "${GITHUB_REPOSITORY_OWNER}.github.io" ]; then
            BASEURL="https://${GITHUB_REPOSITORY_OWNER}.github.io"
          else
            BASEURL="https://${GITHUB_REPOSITORY_OWNER}.github.io/${REPO_NAME}"
          fi

          python - "$BASEURL" <<'PY'
          import re
          import sys
          from pathlib import Path

          path = Path("byggleaf.toml")
          text = path.read_text(encoding="utf-8")
          text, count = re.subn(
              r'(?m)^baseurl\s*=\s*.*$',
              f'baseurl = "{sys.argv[1]}"',
              text,
              count=1,
          )
          if count != 1:
              raise SystemExit("byggleaf.toml: baseurl not found")
          path.write_text(text, encoding="utf-8")
          PY

          byggleaf build

      - uses: actions/configure-pages@v5

      - uses: actions/upload-pages-artifact@v3
        with:
          path: public

      - id: deployment
        uses: actions/deploy-pages@v4
```

工作流会自动把 `baseurl` 设为项目页地址：

```text
https://<owner>.github.io/<repo>
```

如果仓库名是 `<owner>.github.io`，则自动使用：

```text
https://<owner>.github.io
```

使用自定义域名时，把脚本中的 `BASEURL` 改成你的域名即可。

## 发布流程

发布是 **tag 驱动** 的持续交付，不提供本地发布脚本。仓库收到 tag push 后自行完成
校验、构建和 PyPI 发布。

1. 更新 `[project].version`（唯一事实来源）和 `CHANGELOG.md`，提交并推送。
2. 手动创建并推送 tag：

```bash
git tag -a v0.1.1 -m "ByggLeaf v0.1.1"
git push origin v0.1.1
```

3. tag push 自动触发 [`.github/workflows/publish.yml`](.github/workflows/publish.yml)：
   - `verify`：校验 tag 与版本、Ruff、mypy、测试与覆盖率、构建、`twine check`、
     产物检查和 wheel 安装冒烟；
   - `publish`：通过 PyPI Trusted Publishing 发布；
   - `release`：创建 GitHub Release 并附带构建产物。

tag 必须是 `v<version>`，例如 `v0.1.0`；版本不一致时工作流会在第一步失败。

### 首次发布配置

在 PyPI 登记 Trusted Publisher：

```text
Owner:       <GitHub 用户或组织>
Repository:  <仓库名>
Workflow:    publish.yml
Environment: pypi
```

在 GitHub 仓库创建名为 `pypi` 的 environment。工作流使用 OIDC，不需要保存
PyPI token。

手动质量门禁仍可单独运行：

```bash
ruff check .
mypy byggleaf
coverage run -m unittest discover -s tests -v
coverage report
python -m build
python -m twine check dist/*
```

版本号只在 `pyproject.toml` 维护；生成页面、CLI、tag 校验和发布产物都读取同一份值。

## 许可证

ByggLeaf 是自由软件，采用 **GNU General Public License v3.0 or later**
（GPL-3.0-or-later）。完整文本见 [LICENSE](LICENSE)。

你可以按 GPLv3 或任何更新版本使用、修改和分发它。ByggLeaf 不提供任何担保。

## 终端颜色

CLI 使用森林绿与陶土橙的 ANSI 颜色。遵循 `NO_COLOR` 约定；在非 TTY 环境中
自动关闭颜色，设置 `FORCE_COLOR=1` 可强制开启。
