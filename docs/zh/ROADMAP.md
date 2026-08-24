# ROADMAP

> 所有【延】决策登记于此，防止遗忘。版本策略：semver 自 v0.1.0 起。

## v0.1.0（当前目标）

范围决策：**v0.1.0 = P0 + P1 全量交付**，与实施阶段 0–7 一一对应：

| 阶段 | 内容 | 状态 |
|---|---|---|
| 0 | 仓库骨架：LICENSE / .gitignore / pyproject / web 脚手架 / 双语 README / docs 目录 / CI 配置 | ✅ 已完成 |
| 1 | lc 核心：config / auth / i18n / logutil / exceptions / langs / httpclient / sites.cn | ✅ 已完成 |
| 2 | problems + server API（题库同步、缓存、续传） | ✅ 已完成 |
| 3 | 前端骨架：tokens.css 双主题 / 侧边栏布局 / router / ThemeSwitch / i18n / 路由守卫 | ✅ 已完成 |
| 4 | 答题工作台：ProblemDetail + CodeEditor + Run/Submit + 结果面板 + 自定义用例面板 | ◐ 已实现，待真网实测（two-sum 全流程 + 剑指 Offer slug 路由） |
| 5 | 题库列表页 + setup 向导 + daily | ✅ 已实现，待真网联调回归 |
| 6 | archive + llm + analyze + AI 侧边栏 | ✅ 已实现（AI 报告/ask 需真实 LLM Key 联调回归） |
| 7 | 文档全套 + 测试补齐 + 打磨（含安装态 dist 定位验收） | ✅ 已完成（安装态验收通过：非可编辑 pip 安装下 coach 直接打开前端） |

**v0.1.0 功能面全部交付。** 真网回归实测（2026-08-23，真实会话）：

| 项 | 结果 |
|---|---|
| 题库全量同步 | ✅ 4421 题 / 45 页 / 零错误 |
| two-sum 详情/模板/用例落盘 | ✅ |
| Run 调试（data_input 修正后） | ✅ 用户确认可用 |
| Submit + 富结果 + 归档 | ✅ 65/65 通过 |
| 每日一题 | ✅ |
| 站内导入 + 分析统计/SVG 图表 | ✅ 导入 17 条、去重 3 条 |
| Cookie 向导（简易两字段模式） | ✅ |
| AI ask / 报告 | ⬜ 待用户填入 DeepSeek Key 后自测 |

遗留已知项：调试服务偶发站点侧 Internal Error（已做友好提示）；会话轮换与动态 IP
强相关（自动持久化已缓解，换网后需重新复制）。

## v0.1.x（当前进行：全面体检修复）

对功能设计 / UI / 实现逻辑 / 测试流程 / 文档五个维度做了一轮审查，按根因修复：

| 类别 | 修复 | 根因 |
|---|---|---|
| 功能 | 二次同步静默空操作 | 续传语义未区分「失败后续传」与「成功后重新全量」 |
| 功能 | slug `sum` 劫持 `0001-two-sum` 目录 | 目录定位用 endswith 而非解析命名约定 |
| 功能 | Run 只发第一组官方示例；exampleTestcases 抓回未用 | 用例建模只认 sampleTestCase 单值 |
| 功能 | `ui_language`/`theme` 死配置键 | 界面偏好双份真相，后端份无人消费 |
| UI/逻辑 | 错误文案中英混杂；auth 横幅显示裸 i18n 键 | 各视图自取服务端 message；前端 catalog 缺键静默 |
| 逻辑 | 导入与判题两套状态分类规则已漂移 | 同一领域概念重复实现 |
| 逻辑 | `Archive.recent()` 无锁读、判题路径重复读盘、端口 TOCTOU | 并发契约不完整 |
| 测试 | `integration` 标记零用例；CI 仅 py3.12；无 lint | 真网回归只有手工记录；工具链缺失 |
| 文档 | ARCHITECTURE 称 GET「纯读」与实现相悖等 | 文档落后于实现语义 |

## v0.x

- **浏览器扩展一键同步 Cookie【延】**：LEETCODE_SESSION 为 HttpOnly，网页脚本读不到，
  纯 Web 向导无法全自动获取登录态；评估做 leetcode.cn 浏览器扩展把 Cookie 推送到
  本地服务，实现「登录即配置」。
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
