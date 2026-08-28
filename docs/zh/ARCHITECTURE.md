# ARCHITECTURE

## 三层架构

```
web (Vue 3 SPA)  ↔  server/api.py (FastAPI 薄封装)  ↔  lc (核心业务层)  ↔  sites/cn.py (leetcode.cn 适配)
```

- **web/**：Vue 3 + Vite + Pinia + Vue Router + CodeMirror 6（语法高亮经 @lezer/highlight
  双调色板随 data-theme 切换）；构建产物 `web/dist` 由 FastAPI 静态托管；开发模式 Vite :5173
  proxy `/api` → :8000。全局通知走 toast store（成功自动消退、错误驻留至手动关闭）；
  同步轮询由应用级 sync store 持有，跨路由存活、页面刷新后自动重新接管进行中的后端同步；
  判定文案/语义色由共享 utils/verdict.js 单点映射（工作台结果面板与历史页共用）。
- **server/api.py**：REST 层。领域异常与带 i18n 键的 HTTPException（统一经 `http_domain_error()`）都翻译为携带 `message_key` 的结构化错误 JSON，前端据此按 UI 语言渲染；SPA catch-all 回退 index.html（`relative_to` 严格限制在 dist 内；资源形态路径未命中一律 404，防止旧标签页的哈希 chunk 被改写成 HTML）；Host（含 IPv6 括号格式）/ Origin 校验中间件——写方法要求白名单本地 Origin（含 Vite dev 来源 `http://localhost:5173`），GET 免 Origin 但 Host 必须本地（防 DNS rebinding），`{qid}` 入口统一做 slug 字符白名单校验；带阻塞网络 IO 的长端点一律普通 def 走线程池。config.toml 的全部写者经 `lc.config.update_lock()` 串行化。
- **lc/**：与 UI 框架解耦的核心业务层：config / auth / httpclient / exceptions / logutil / i18n / langs / problems / judge / archive / favorites / llm / atomicio（跨平台原子写：tmp + os.replace，Windows 上对并发读者造成的 sharing violation 做有界重试；config/favorites/题库缓存/工作区文件的唯一写盘通道）。
- **sites/cn.py**：所有 GraphQL 响应解析单点收口，字段缺失降级为清晰报错而非崩溃。
- **SiteAdapter 抽象**（sites/base.py）：最小接口，只为 cn 实现；leetcode.com 待需求验证。

## 本地存储布局

```
~/.algocoach/
├── config.toml            schema_version、Cookie、LLM 配置（界面偏好存浏览器 localStorage，不入配置文件）
├── problems.json          题库缓存（题号↔slug、付费标记、难度、标签、类别）
├── submissions.jsonl      提交归档（JSON Lines 追加）
├── favorites.json         收藏索引（slug 列表；列表页需对全量题目渲染收藏态，
│                          而工作区目录只为打开过的题目存在，故用独立索引文件）
└── workspace/problems/    工作区根目录（workspace_root 可配置）
    └── 0001-two-sum/
        ├── statement.md       中文题面（文件名统一 ASCII）
        ├── solution.cpp       代码模板（多语言共存 solution.py 等）
        ├── cases.json         官方示例正本（exampleTestcases 解码后每组用例一条）
        ├── testcases.txt      人工编辑工作副本
        └── notes.md           用户笔记（完全用户所有，refresh 不触碰）
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
GET  /api/status                    配置状态/版本/站点信息/LLM 可用性（llm_configured，
                                    供 AI 面板与分析页共用门控）/同步进度快照
POST /api/setup/validate-cookie     引导页即时校验
GET  /api/settings                  读取（敏感字段脱敏：<16 字符全遮，否则仅回显尾 4 字符）
PUT  /api/settings                  更新（Cookie 变更即时重建会话；任何字段显式传 null
                                    一律 422——省略该字段才表示不修改；
                                    request_interval 限定 [0.5, 60] 秒、llm_timeout 限定
                                    [5, 600] 秒、llm_thinking 限定
                                    default/off/low/medium/high，越界 422）
GET  /api/problems                  全量返回本地缓存（筛选分页由前端执行）；
                                    每行按归档索引富化 practice_status/last_practice_at，
                                    并按收藏索引附加 favorite 标记
POST /api/problems/sync             同步题库（进行中重复调用返回 409）。
                                    续传仅发生在上次失败后；成功后的再次同步
                                    永远全新全量，保证站点新增题目可见
GET  /api/problems/sync/progress    同步进度轮询
GET  /api/daily                     每日一题
GET  /api/problem/{qid}             打开题目：本地已落盘则纯读；未落盘时惰性物化
                                    （抓取一次并写入工作区/缓存），此后离线可读；
                                    statement.md 带转换器版本号（meta.statement_version），
                                    版本落后时在线重生成一次，失败降级用旧文件；
                                    language 返回最近写入的 solution.*（重开续用
                                    上次语言），无任何 solution 时回退配置默认语言
POST /api/problem/{qid}/refresh     显式重抓题目详情并刷新工作区（用户编辑过的文件先 .bak 备份）
GET  /api/problem/{qid}/template    ?lang= 按需抓取该语言模板并落盘；省略时用配置的
                                    default_language（与其他端点同一默认来源）
PUT  /api/problem/{qid}/solution    编辑器代码落盘（debounce 自动保存/保存即判定共用）
PUT  /api/problem/{qid}/testcases   自定义用例面板保存
PUT  /api/problem/{qid}/notes       笔记落盘 notes.md
PUT  /api/problem/{qid}/favorite    收藏切换 {favorite: bool}（写 favorites.json 索引）
POST /api/judge/run                 {qid, lang, code, use_local?} 先落盘再判定，不进提交历史；
                                    远程运行合并 cases.json 全部官方示例（data_input 换行拼接）；
                                    题目缺内部题号时显式 422（judge_missing_question_id），
                                    绝不回退 slug 发出必然失败的请求
POST /api/judge/submit              {qid, lang, code} 阻塞长轮询至判定完成或超时；
                                    完成后自动归档（本地归档写入失败时判定结果仍返回，
                                    archived:false 提示前端，绝不把已完成的提交包成 500）；
                                    超时走「结果未知」路径并归档
GET  /api/archive/recent            本地归档最近记录；?qid= 按题目过滤、?limit≤200，
                                    统一走 Archive.query() 加锁扫描原语（newest-first）
POST /api/archive/import-site       submissionList 导入（≤20 条边界，去重键 = submission_id，
                                    状态分类与判题共用 cn.classify_status_text 单一来源；
                                    批次按时间戳升序追加，维持文件「追加序=时间序」不变量）
POST /api/ask                       无状态问答 {question, history?, qid, code?, lang?}——
                                    题目与最近判定自动入上下文；code 为用户显式附带当前代码（截断 6000 字符）
POST /api/llm/test                  LLM 连通性探测：payload 字段（llm_api_key/base_url/
                                    model/thinking）覆盖已保存配置、缺省回退，发一条
                                    max_tokens 限幅的 ping；未配置 400，失败走
                                    NetworkError → 502 结构化错误
POST /api/analyze                   解题统计 + 标签掌握度 + 推荐 + AI 报告（use_llm 可关；
                                    ai_configured 恒由保存的配置推导，与本次是否生成解耦）
DELETE /api/local-data              清除全部本地数据（题库缓存/归档/工作区/配置），
                                    同步进行中返回 409；保留运行中的 instance.lock；
                                    与 sync 启动共用 _lifecycle_lock 互斥（无 TOCTOU），
                                    清除时重置同步引擎累加器；前端同时清除浏览器侧草稿快照

GET  /{path}                        前端托管：命中 dist 文件直出，SPA 深链回退 index.html
                                    （资源形态路径未命中返回 404）；index.html no-cache、
                                    哈希资源 immutable 长缓存；未构建 dist 时为 API-only 模式
```

## 前端托管与单实例

- **dist 解析链**：`ALGOCOACH_DIST` 环境变量 → 仓库 `web/dist`（源码/可编辑安装）→
  安装包内 `server/webdist`（wheel 发布态）；均未命中则 API-only。
- **单实例守卫**：`~/.algocoach/instance.lock`（O_CREAT|O_EXCL 记 PID+端口）+
  PID 存活探测（Windows 走 ctypes OpenProcess）+ 端口占用时 `/api/status` 兜底识别；
  顺延选中的监听 socket 先绑定并持有、再交给 uvicorn，消除「发现空闲端口→释放→
  启动前被其他进程抢占」的 TOCTOU 窗口。

## 已知能力边界

- 站内提交列表（submissionList）仅能取最近约 20 条。
- v0.1 题面公式原文展示、图片断网失效（见 ROADMAP）。
- 调试运行（interpret_solution）偶发站点侧 Internal Error，属 leetcode.cn
  调试服务不稳定；前端会显示「调试服务暂不可用」提示，稍后重试即可。
