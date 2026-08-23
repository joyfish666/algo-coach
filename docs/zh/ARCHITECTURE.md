# ARCHITECTURE

## 三层架构

```
web (Vue 3 SPA)  ↔  server/api.py (FastAPI 薄封装)  ↔  lc (核心业务层)  ↔  sites/cn.py (leetcode.cn 适配)
```

- **web/**：Vue 3 + Vite + Pinia + Vue Router + CodeMirror 6；构建产物 `web/dist` 由 FastAPI 静态托管；开发模式 Vite :5173 proxy `/api` → :8000。
- **server/api.py**：REST 层。领域异常翻译为结构化错误 JSON；SPA catch-all 回退 index.html；Origin / Sec-Fetch-Site / Host 校验中间件（白名单含 Vite dev 来源 `http://localhost:5173`，按方法分级）；带阻塞网络 IO 的长端点一律普通 def 走线程池。
- **lc/**：与 UI 框架解耦的核心业务层：config / auth / httpclient / exceptions / logutil / i18n / langs / problems / judge / archive / llm。
- **sites/cn.py**：所有 GraphQL 响应解析单点收口，字段缺失降级为清晰报错而非崩溃。
- **SiteAdapter 抽象**（sites/base.py）：最小接口，只为 cn 实现；leetcode.com 待需求验证。

## 本地存储布局

```
~/.algocoach/
├── config.toml            schema_version、Cookie、LLM 配置、界面偏好
├── problems.json          题库缓存（题号↔slug、付费标记、难度、标签、类别）
├── submissions.jsonl      提交归档（JSON Lines 追加）
└── workspace/problems/    工作区根目录（workspace_root 可配置）
    └── 0001-two-sum/
        ├── statement.md       中文题面（文件名统一 ASCII）
        ├── solution.cpp       代码模板（多语言共存 solution.py 等）
        ├── cases.json         官方示例正本
        └── testcases.txt      人工编辑工作副本
```

目录命名：题号全数字时 `0001-two-sum/`（zfill 补零），非数字时直接用 slug。

## 归档格式

JSON Lines 追加写。每条记录自足冗余 difficulty / tags / lang 与完整判定字段
（qid、frontendQuestionId、submission_id、lang、timestamp、status 含 "unknown"、
runtime/memory + 击败百分比、WA 对比、CE/RE 摘要），单条即可独立支撑 analyze 统计与 AI 报告。
submission_id 三条写入路径全覆盖（判题完成 / 超时 unknown 归档 / 站内导入），亦为去重键。
「已通过」状态由归档按 qid 取最近一条判定推导；进程内维护 qid→最近判定增量索引（线程安全），
避免列表页全量扫档。

## REST API 契约

`{qid}` = slug 规范键。

```
GET  /api/status                    配置状态/版本/站点信息/同步进度快照
POST /api/setup/validate-cookie     引导页即时校验
GET  /api/settings                  读取（敏感字段脱敏）
PUT  /api/settings                  更新（Cookie 变更即时重建会话）
GET  /api/problems                  全量返回本地缓存（筛选分页由前端执行）
POST /api/problems/sync             同步题库（进行中重复调用返回 409）
GET  /api/problems/sync/progress    同步进度轮询
GET  /api/daily                     每日一题
GET  /api/problem/{qid}             题目详情；?refresh=1 显式重抓（用户编辑过的文件先 .bak 备份）
GET  /api/problem/{qid}/template    ?lang=cpp 按需抓取该语言模板并落盘
PUT  /api/problem/{qid}/solution    编辑器代码落盘（debounce 自动保存/保存即判定共用）
PUT  /api/problem/{qid}/testcases   自定义用例面板保存
POST /api/judge/run                 {qid, lang, code, use_local?} 先落盘再判定，不进提交历史
POST /api/judge/submit              {qid, lang, code} 阻塞长轮询至判定完成或超时；
                                    完成后自动归档；超时走「结果未知」路径并归档
GET  /api/archive/recent            本地归档最近记录
POST /api/archive/import-site       recentSubmissionList 导入（≤20 条边界，去重键 = submission_id）
POST /api/ask                       无状态问答 {question, history?, qid}——题目与最近判定自动入上下文
POST /api/analyze                   解题统计 + 标签掌握度 + 推荐 + AI 报告（use_llm 可关）

GET  /{path}                        前端托管：命中 dist 文件直出，SPA 深链回退 index.html；
                                    未构建 dist 时为 API-only 模式
```

## 前端托管与单实例

- **dist 解析链**：`ALGOCOACH_DIST` 环境变量 → 仓库 `web/dist`（源码/可编辑安装）→
  安装包内 `server/webdist`（wheel 发布态）；均未命中则 API-only。
- **单实例守卫**：`~/.algocoach/instance.lock`（O_CREAT|O_EXCL 记 PID+端口）+
  PID 存活探测（Windows 走 ctypes OpenProcess）+ 端口占用时 `/api/status` 兜底识别。

## 已知能力边界

- recentSubmissionList 仅能取最近约 20 条。
- v0.1 题面公式原文展示、图片断网失效（见 ROADMAP）。
