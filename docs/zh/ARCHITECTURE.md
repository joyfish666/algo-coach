# ARCHITECTURE

## 分层架构

```
web (Vue 3 SPA)  ↔  server (FastAPI 传输层)  ↔  lc (核心业务层)  ↔  lc/sites/cn.py (leetcode.cn 适配)
```

- **web/**：Vue 3 + Vite + Pinia + Vue Router + CodeMirror 6（语法高亮经 @lezer/highlight
  双调色板随 data-theme 切换）；构建产物 `web/dist` 由 FastAPI 静态托管；开发模式 Vite :5173
  proxy `/api` → :8000。全局通知走 toast store（成功自动消退、错误驻留至手动关闭）；
  同步轮询由应用级 sync store 持有，跨路由存活、页面刷新后自动重新接管进行中的后端同步；
  错误文案/难度 chip/判定文案/Markdown 渲染/localStorage 键名均由共享工具单点维护
  （utils/verdict.js · difficulty.js · errors.js · markdown.js · storage.js）。
  答题工作台 ProblemDetail.vue 只保留编排逻辑（加载、程序化写入栅栏、自动保存/快照/
  恢复条、判定门控、分割线拖拽、快捷键），题面+笔记（ProblemStatement）、自定义用例
  （CasesPanel）、判定计时（JudgingIndicator）、标题元信息行（ProblemMetaRow）各为独立
  组件；切换题目时未保存内容必须以**旧题号**冲刷，该契约由 ProblemDetail.test.js 的
  持久化契约测试钉住。
- **分组（groups）**：一个共享快照 store（`stores/groups.js`）服务三处入口——
  `/groups` 管理页（GroupNode 递归渲染无限层级，上/下移与改父级均为按钮/下拉，
  组内搜索加题）、题库列表行悬浮加组按钮、工作台元信息行的已属分组 chip
  （点击深链 `/groups?group=<id>` 并滚动高亮）。store 每次变更后重取小文档，
  保证树形/顺序/成员关系与服务端一致；加组浮层（GroupPickerPopover）用
  「扁平列表 + 完整路径前缀」而非树形下拉——无限层级下树形下拉不可用，
  扁平路径在任何深度都可读。`/api/problems` 契约不携带分组信息，
  成员关系由前端 join，列表行渲染零耦合。节点可折叠（头部箭头/点组名），
  折叠态持久化在 localStorage（`algocoach-group-collapsed`），深链定位前先
  展开祖先链；组内条目可标记「重点」（`marked` slug 列表，随分享码双向携带，
  渲染为加粗标题 + 强调色序号）。
- **server/**：REST 传输层，按职责分模块——
  `app.py`（组合根：Origin/Host 守卫中间件、异常处理器、dist 托管与 SPA 回退）、
  `errors.py`（统一错误 envelope 与状态码映射）、`state.py`（进程级单例与按配置派生的
  工厂，也是测试的统一 patch 点）、`routers/`（settings 状态/设置/LLM 探测、
  problems 题库/工作台/判题、coach AI 问答与分析、archive 归档/导入/清除）。
  所有错误响应使用单一 envelope `{"error": {kind, message_key, message, detail?}}`：
  领域异常与带 i18n 键的 HTTPException（经 `http_domain_error()`）都携带 `message_key`，
  前端据此按 UI 语言渲染；SPA catch-all 回退 index.html（`relative_to` 严格限制在 dist 内；
  资源形态路径未命中一律 404，防止旧标签页的哈希 chunk 被改写成 HTML）；Host（含 IPv6
  括号格式）/ Origin 校验——写方法要求白名单本地 Origin（含 Vite dev 来源
  `http://localhost:5173`），GET 免 Origin 但 Host 必须本地（防 DNS rebinding），
  `{qid}` 入口统一经 `lc.validate.is_safe_slug` 白名单校验；带阻塞网络 IO 的长端点
  一律普通 def 走线程池。config.toml 的全部写者经 `lc.config.update_lock()` 串行化。
- **lc/**：与 UI 框架解耦的核心业务层——config（配置+锁+env 校验）/ auth / httpclient /
  exceptions / logutil / i18n / langs / problems（题库缓存+同步引擎）/ workspace
  （每题工作区物化，含 STATEMENT_VERSION 版本契约）/ htmltomd（题面 HTML→Markdown
  转换器）/ coach（AI 提示词工程，纯逻辑）/ clock / validate / cookies（同名跨域
  Cookie 的容错读取与去重）/ judge / archive / favorites / llm / atomicio（跨平台
  原子写：tmp + os.replace，Windows 上对并发读者造成的 sharing violation 做有界重试；
  config/favorites/题库缓存/工作区文件的唯一写盘通道）/ groups（自定义分组树：扁平
  parent 指针 + 有序 slugs，移动沿父链防环、嵌套防御上限 10 层、分享码
  zlib+urlsafe base64 纯标准库编码）。
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
├── groups.json            自定义分组树（扁平 parent 指针 + 有序 slugs；
│                          只记录题号不复制题目；嵌套防御上限 10 层）
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
GET  /api/heartbeat                 Web-UI 存活心跳（每个打开的标签页约 10s 一次）；
                                    cli --idle-exit 看门狗据此在最后一次页面关闭后
                                    按期限退出（同步进行中顺延），双击启动脚本依赖此机制
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
GET  /api/groups                    全量分组树（扁平 parent 指针，兄弟顺序=数组顺序）
POST /api/groups                    建组 {name, parent?}（嵌套超 10 层 400 group_depth_limit）
PUT  /api/groups/{id}/rename        改名 {name}
PUT  /api/groups/{id}/move          改父级/排序 {parent, index?}；parent=null 回到根，
                                    index 为去除自身后的兄弟下标（越界钳位）；
                                    移入自身子树 400 group_cycle，深度超限 400
DELETE /api/groups/{id}             级联删除整棵子树
POST /api/groups/{id}/items         追加题目 {slugs}（slug 白名单校验，组内去重追加）
PUT  /api/groups/{id}/items         整组重排 {slugs}（必须是现有 slugs 的排列，否则 422）
DELETE /api/groups/{id}/items/{qid} 移除一题（同时清理该题的重点标记）
PUT  /api/groups/{id}/marked        整组替换重点标记 {slugs}（自动剔除不属于本组的 slug）
POST /api/groups/import             导入分享码 {code}：总是新建顶级分组（与现有根组重名
                                    自动加后缀）；未同步的 slug 原样保留（前端渲染为
                                    「未识别」，同步后自动恢复）；非法码 400
                                    group_invalid_code，嵌套超限 400 group_depth_limit
POST /api/groups/export             导出分享码 {ids?}（缺省=全部根组；指定 id 按子树裁剪）
                                    → {code}，格式 algocoach-groups:v1:<base64url(zlib(json))>
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
POST /api/ask                       无状态问答 {question, history?, qid, code?, lang?, ui_lang?}——
                                    题目与最近判定自动入上下文；code 为用户显式附带当前代码（截断 6000 字符）；
                                    ui_lang（前端 i18n store 附带）决定系统提示词/上下文标签语言，
                                    未知值回退 zh
POST /api/llm/test                  LLM 连通性探测：payload 字段（llm_api_key/base_url/
                                    model/thinking）覆盖已保存配置、缺省回退，发一条
                                    max_tokens 限幅的 ping；未配置 400，失败走
                                    NetworkError → 502 结构化错误
POST /api/analyze                   解题统计 + 标签掌握度 + 推荐 + AI 报告（use_llm 可关；
                                    ui_lang 决定报告提示词与摘要语言；ai_configured 恒由保存的
                                    配置推导，与本次是否生成解耦）
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

见 [PITFALLS「已知限制」](PITFALLS.md)——该清单在那里单点维护（连同全部实现陷阱），
此处不再复制，避免两份各自漂移。
