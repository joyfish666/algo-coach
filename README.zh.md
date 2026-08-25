# AlgoCoach

力扣（leetcode.cn）本地刷题 Web 工作台 + AI 学习教练。
所有数据——Cookie、配置、提交归档——全部留在本地，无任何云依赖。

> **状态**：v0.1.0 功能面已全部交付（真网回归实测通过，见 [ROADMAP](docs/zh/ROADMAP.md)），
> 正在进行发布前的全面体检与打磨。

## 功能

- `/setup` 引导向导：粘贴 Cookie 即时校验，可选配置 LLM Key
- 题库全量同步：本地缓存 + 全局进度反馈（切页/刷新不丢失）+ 状态/难度/标签/关键词筛选、
  随机一题、收藏标记与紧凑密度切换
- 答题工作台：中文题面渲染、CodeMirror 6 编辑器（语法高亮随主题切换）、Run / Submit 富判定结果
  （用时/内存击败百分比、WA 用例对比、CE/RE 详情）、每题笔记、收藏星标
- 提交历史页：本地归档的每一次提交可回看（WA 对比 / CE-RE 详情展开），按题目过滤
- 断网复习：打开过的题目落盘为本地文件，随时可复习
- 每日一题直达；分析仪表盘（标签掌握度图表、推荐练习）与 AI 薄弱点报告（自带 Key）
- 工作台 AI 教练侧边栏，自动附带当前题目与最近判定上下文，可显式附带当前代码
- 本地提交归档（JSON Lines）+ 站内近期提交导入；通过状态按题目自动推导
- 中英双语界面；浅色/暗色双主题设计系统（语义化成功/警告/危险色贯穿难度与判定反馈）；
  统一 toast 反馈（错误驻留至关闭）；前端请求统一超时保护

## 安装

要求 Python ≥ 3.10。Node.js ≥ 18 仅在从源码构建前端时需要
（发布版 wheel 将附带已构建的前端产物）。

```bash
git clone https://github.com/joyfish666/algo-coach.git
cd algo-coach
pip install -e .
cd web && npm install && npm run build && cd ..
```

## 快速开始

```bash
coach
```

服务仅绑定 `127.0.0.1`（默认端口 `8000`，被占用自动顺延），横幅打印最终 URL，
就绪后自动打开浏览器——前端页面由服务直接托管，运行期无需 Node。
首次启动进入 `/setup` 引导页。

内置单实例守卫：重复启动会被拒绝并提示已运行的地址。

参数：`--port`、`--no-browser`、`--debug`。

## 隐私模型

Cookie、配置与提交归档存放于 `~/.algocoach/`（仓库外、用户目录内），
POSIX 下写入时收紧文件权限。除 leetcode.cn 本身（以及你自行配置的 LLM 端点）外，
数据不会发往任何第三方。

## 文档

- [中文文档](docs/zh/)：USAGE · DEVELOPMENT · ARCHITECTURE · ROADMAP · PITFALLS
- 英文文档规划于 v1.x（见 [ROADMAP](docs/zh/ROADMAP.md)）

## 开发规则 / Development Rules

所有人类开发者与 AI Agent 必须遵守：

1. **修复 bug 必须定位根源**，禁止打补丁掩盖症状；PR 中需附根因分析。
2. **开发前必读 [docs/zh/PITFALLS.md](docs/zh/PITFALLS.md)**；解决新坑后必须回填。
3. **依赖政策**：仅允许通用基础库——后端 `requests` / `fastapi` / `uvicorn` / `rich`；
   前端 `vue` / `vite` / `pinia` / `vue-router` / `codemirror`，以及 CodeMirror 官方包
   （语言包如 `@codemirror/lang-cpp`、语法高亮基础 `@lezer/highlight`）与
   `markdown-it`（题面渲染，默认转义 HTML 防注入）；
   禁止搬运任何现有 LeetCode 相关项目代码，业务逻辑必须 100% 自研。
4. **文档政策**：README 必须保持中英双份同步；docs/ 改动需同步登记 ROADMAP。

欢迎任何形式的贡献！无论是提出问题（issues）还是提交代码（pull requests），即使是再小的毛病、再小的改动，我们都非常欢迎。
*Welcome in any form of contribution — issues or PRs, no matter how small!*

## 参与贡献

见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可证

[MIT](LICENSE)
