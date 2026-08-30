# AlgoCoach

本地优先的 leetcode.cn 刷题工作台，内置 AI 学习教练。所有数据——Cookie、配置、
提交归档——全部留在本机，无云依赖。

> **状态**：v0.1.0 已交付并通过真网回归验证（见 [ROADMAP](docs/zh/ROADMAP.md)）。

## 功能

- `/setup` 引导向导（Cookie + 偏好）；LLM 配置独立放在设置页，带一键连通性
  探测与思考模式控制
- 全量题库同步（约 4400 题），进度跨页面切换存活；状态（已通过/尝试过/未做/收藏）、
  难度、标签、关键词筛选，随机一题，紧凑密度模式
- 答题工作台：题面渲染、CodeMirror 6 编辑器、Run/Submit 富判定结果（WA 用例对比、
  CE/RE 详情、击败百分比）、每题笔记与自定义用例；重开题目自动续用上次语言与代码
- 本地归档的提交历史与一键站内导入；打开过的题目落盘为本地文件，可离线复习
- 自定义分组（刷题计划）：可无限嵌套、按顺序排列的题目清单，只记录题号不复制
  题目；分享码导入/导出；题库列表、工作台、分组页三处入口
- 每日一题直达；分析仪表盘（标签掌握度、推荐练习、AI 薄弱点报告）；每题一个
  无状态 AI 教练侧边栏（回复跟随界面语言，可显式附带当前代码）
- 中英双语界面；浅色/暗色设计系统；统一 toast 与请求超时

## 快速开始

要求 Python ≥ 3.10（仅从源码构建前端时需要 Node.js ≥ 18）：

```bash
git clone https://github.com/joyfish666/algo-coach.git
cd algo-coach && pip install -e .
cd web && npm install && npm run build && cd ..
coach
```

`coach` 仅绑定 `127.0.0.1`（默认端口 8000，被占用自动顺延），就绪后自动打开浏览器，
重复启动会被单实例守卫拒绝。首次启动进入 `/setup` 引导页。
参数：`--port`、`--no-browser`、`--debug`。

## 隐私模型

Cookie、配置与提交归档存放在 `~/.algocoach/`——仓库目录之外，POSIX 下权限收紧。
除访问 leetcode.cn 本站（以及你自己配置的 LLM 端点）外，没有任何数据离开本机。

## 文档

中文文档为权威：

- [使用手册 USAGE](docs/zh/USAGE.md)（安装/启动/页面/报错对照）·
  [English quick guide](docs/en/USAGE.md)
- [开发环境 DEVELOPMENT](docs/zh/DEVELOPMENT.md) ·
  [系统架构 ARCHITECTURE](docs/zh/ARCHITECTURE.md)（含 REST 契约）
- [实现陷阱 PITFALLS](docs/zh/PITFALLS.md) · [ROADMAP](docs/zh/ROADMAP.md) ·
  [CHANGELOG](CHANGELOG.md)
- 贡献规则：[CONTRIBUTING.md](CONTRIBUTING.md)

## 参与贡献

见 [CONTRIBUTING.md](CONTRIBUTING.md)——根因优先的 bug 修复、最小依赖政策、
双语文档同步等规则都在其中。任何形式的贡献都欢迎，再小的改动也是。

## 许可证

[MIT](LICENSE)
