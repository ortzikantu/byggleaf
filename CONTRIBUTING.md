# 为 ByggLeaf 贡献

ByggLeaf 是一个刻意保持狭窄、有主见的个人数字花园静态网站生成器。它**不是**
通用 SSG，也没有主题、插件、自定义模板、自定义 CSS/JS 或任意输出管线的路线图。
把它推向通用平台的方向会被拒绝。

欢迎的贡献包括：

- 正确性和安全性修复；
- 无障碍和 HTML 质量修复；
- 构建与发布可靠性改进；
- 翻译；
- 让固定模型更容易理解的文档。

## 开发

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

ruff check .
mypy byggleaf
coverage run -m unittest discover -s tests -v
coverage report
python -m build
```

测试使用标准库 `unittest`。不要增加运行时依赖：安装后的包只能依赖 `markdown`
和 `jinja2`。开发工具放在 `dev` 可选依赖组中。

## 本地化

语言标签必须是规范的 BCP 47 标签，文件名必须正好是该标签加 `.toml`，例如：

```text
locales/zh-CN.toml
locales/zh-HK.toml
locales/yue.toml
```

没有回退机制。`zh-SG` 不会使用 `zh-CN`，必须有自己的 `zh-SG.toml`。缺少文件时
会报错并列出所有可用语言文件。

### 新增语言

1. 复制最接近的现有语言文件，例如：

   ```bash
   cp byggleaf/locales/zh-CN.toml byggleaf/locales/zh-SG.toml
   ```

2. 翻译 `[ui]` 下的每个值。缺失或为空的 key 会在运行时显示 key 名，因此部分翻译
   的文件可以安全加载；但合并进包的内置语言文件仍应保持完整。

3. 保持标签规范：

   - 语言小写；
   - 文字系统首字母大写，例如 `Hans`、`Hant`；
   - 地区大写，例如 `CN`、`HK`、`TW`。

4. 在 README 状态表中用准确代码和 ✅/❌ 标出支持情况。

5. 运行数据驱动的本地化测试：

   ```bash
   python -m unittest tests.test_locales tests.test_architecture -v
   ```

测试会扫描 `locales/*.toml`，故意不维护硬编码的支持语言列表。新增语言文件不应
需要修改测试预期列表。

6. 如果语言文件仍不完整，README 中保持 ❌。不要把半成品文件作为内置语言合并。

## 提交请求

- 保持架构单向：`app` 负责装配，`cli` 不导入 `core`，`core` 不导入入口层。
- 不要向模板、样式或 ByggLeaf 自身生成的输出加入 JavaScript（用户 Markdown 中的原始 HTML 由用户负责）。
- 不要增加用户可覆盖的模板或主题钩子。
- 每个行为变更都要有测试。
- 用户可见输出保持克制、明确；错误要说明失败原因和下一步。

## 许可证

提交贡献即表示你同意该贡献按 GPL-3.0-or-later 授权，与本项目许可证一致。
