# Contributing

欢迎任何形式的贡献！无论是提出问题（issues）还是提交代码（pull requests），
即使是再小的毛病、再小的改动，我们都非常欢迎。

环境搭建与日常命令（测试 / lint / i18n 校验 / 发布打包）见
[docs/zh/DEVELOPMENT.md](docs/zh/DEVELOPMENT.md)，此处不再重复。
提交前请确保后端 `ruff check .` + `pytest`、前端 `npm run lint` + `npm test`
+ `npm run check:i18n` 全部通过。

> **English summary**: set up the dev environment per
> [docs/zh/DEVELOPMENT.md](docs/zh/DEVELOPMENT.md); run the backend
> (`ruff check .`, `pytest`) and frontend (`npm run lint`, `npm test`,
> `npm run check:i18n`) gates before every PR. Bug fixes require a
> root-cause analysis. Use conventional commits. Contributions of any size
> are welcome!

## 开发规则（对所有人类开发者与 AI 代理生效）

1. **修复 bug 必须落在根因上。** 禁止打补丁掩盖症状；PR 必须附根因分析。
2. **开发前必读 [docs/zh/PITFALLS.md](docs/zh/PITFALLS.md)**；解决新坑必须回填该文件。
3. **依赖政策**：只允许通用基础库——后端 `requests` / `fastapi` / `uvicorn` /
   `rich`；前端 `vue` / `vite` / `pinia` / `vue-router` / `codemirror`
   （外加 CodeMirror 官方包：语言包如 `@codemirror/lang-cpp`、语法高亮
   `@lezer/highlight`）与 `markdown-it`（题面渲染，HTML 默认转义）。
   严禁从任何现有 LeetCode 相关项目复制代码——所有业务逻辑必须原创。
4. **文档政策**：README 中英双份必须同步修改；`docs/` 下的每次改动必须在
   [ROADMAP](docs/zh/ROADMAP.md) 登记。每个事实只在一个文档里维护（安装步骤在
   USAGE、命令在 DEVELOPMENT、系统事实在 ARCHITECTURE、坑在 PITFALLS），
   其余位置用链接引用，避免多份副本各自漂移。
5. **文档语言**：深层文档（docs/zh/）以中文为权威；[docs/en/USAGE.md](docs/en/USAGE.md)
   为英文读者提供精简入口，英文 README 链接必须指向真实存在的内容。

## 提交规范

- 使用 conventional commits：`feat:` / `fix:` / `docs:` / `refactor:` / `test:` / `chore:`
- 修复 bug 必须附根因分析，禁止打补丁掩盖症状
- 用户可见的变更需在 [CHANGELOG](CHANGELOG.md) 的 `[Unreleased]` 段登记一条
