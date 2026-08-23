# ROADMAP

> 所有【延】决策登记于此，防止遗忘。版本策略：semver 自 v0.1.0 起。

## v0.1.0（当前目标）

范围决策：**v0.1.0 = P0 + P1 全量交付**，与实施阶段 0–7 一一对应：

| 阶段 | 内容 | 状态 |
|---|---|---|
| 0 | 仓库骨架：LICENSE / .gitignore / pyproject / web 脚手架 / 双语 README / docs 目录 / CI 配置 | ✅ 已完成 |
| 1 | lc 核心：config / auth / i18n / logutil / exceptions / langs / httpclient / sites.cn | ⬜ 待实施 |
| 2 | problems + server API（题库同步、缓存、续传） | ⬜ 待实施 |
| 3 | 前端骨架：tokens.css 双主题 / 侧边栏布局 / router / ThemeSwitch / i18n / 路由守卫 | ◐ 骨架已就位，待完整实现 |
| 4 | 答题工作台：ProblemDetail + CodeEditor + Run/Submit + 结果面板 + 自定义用例面板 | ⬜ 待实施 |
| 5 | 题库列表页 + setup 向导 + daily | ⬜ 待实施 |
| 6 | archive + llm + analyze + AI 侧边栏 | ⬜ 待实施 |
| 7 | 文档全套 + 测试补齐 + 打磨（含安装态 dist 定位验收） | ⬜ 待实施 |

## v0.x

- **语言注册表扩充**（按行添加）。**Go 语言支持【延】**：CodeMirror 官方无
  `@codemirror/lang-go` 包，为保持依赖政策纯净不为单一语言引入 pinned 社区包；
  待官方包出现或明确批准社区包后再加入；届时仍不可行则以 plain text 降级。
- **归档导出/清理机制【延】**：submissions.jsonl 只追加会无限增长，
  analyze 约定只取最近 N 条（N 可配置）。
- **ask 流式输出【延】**：v0.1 为非流式 + 120s 超时，长回答体验一般，待评估流式方案。
- **KaTeX 公式渲染【延】**：v0.1 题面 LaTeX 公式以原文展示（markdown-it 默认不解析公式），
  KaTeX 登记待评估；图片不做本地化（断网失效为已知限制）。
- **SQL/数据库类别支持【延】**：同步保留全部题目但打「暂不支持」标记，
  打开工作台时拦截提示；SQL 类别支持待评估。

## v1.x

- docs 英文版（docs/en/ 目前仅放占位说明）
- 发布到 PyPI

## v2?

- leetcode.com SiteAdapter（需求验证后再实现，当前只为 cn 写实现）
