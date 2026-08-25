# PITFALLS

> **开发前必读。** 解决新坑后必须回填本文件。

## 站点与请求

- **Referer 缺失导致 403**：对 leetcode.cn 的 GraphQL 请求需注入浏览器 UA + Referer + csrfToken。
- **内部 question_id ≠ 前端题号**：frontendQuestionId 可能非纯数字（如「剑指 Offer 03」「面试题 17.16」「LCP 07」，含空格与中文）。规范键一律用 slug；题号全数字时目录命名 `0001-two-sum/`，否则直接用 slug。
- **UA 风控**：使用真实浏览器 UA。
- **每日一题时区**：以 00:00 UTC+8 为界。
- **自定义用例输入序列化格式【已真网回填】**：cn 站调试运行接口的自定义用例字段是
  `data_input`，多组用例直接换行拼接（浏览器同款）；官方示例应从详情的
  `exampleTestcases`（JSON 编码字符串数组，每个元素是一组完整输入）解码为多条 case，
  仅在缺失时回退单个 `sampleTestCase`，否则同一用例会被存两遍。曾因误用 `input` 字段名
  触发站点 Internal Error。
- **同步引擎的续传语义只属于失败态**：`SyncEngine` 的页游标与已拉取行若在任何启动时都保留，
  「上次成功同步后再点同步」会从末页续传、立即空页退出——站点新增题目直到重启进程都不可见。
  正确语义：仅当上一次运行失败且存在半程数据时才续传；成功后（或从未运行）必须全新全量。
  （2026-08-23 已修复并附回归测试）
- **题目目录定位禁止字符串后缀匹配**：目录命名约定是 `<digits>-<slug>` 或裸 `<slug>`；
  用 `endswith("-{slug}")` 扫描会让短 slug（如 `sum`）劫持长目录（如 `0001-two-sum`），
  把读写判题落到别的题目工作区。必须按约定正则解析后精确比对。（2026-08-23 已修复）
- **GraphQL 字段名【已真网回填 2026-08-23】**：cn 站实测确认——
  - 题库列表：顶层 `problemsetQuestionList(categorySlug, limit, skip, filters)` 直接调用（**不存在**底层 `questionList` 字段）；行节点是 `QuestionLightNode`，字段为 `acRate / difficulty / title / titleCn / titleSlug / paidOnly / frontendQuestionId / topicTags { slug name nameTranslated }`（CommonTagNode）；**没有** `isPaidOnly`、`categoryTitle`、`translatedTitle`、`questionFrontendId`
  - 题目详情：`question(titleSlug:)` 节点用 `translatedTitle`（**无 `titleCn`**），标签节点是 `TopicTagNode` 用 `translatedName`，含 `exampleTestcases` 与内部 `questionId`（判定接口必需）
  - 每日一题：`todayRecord { date question { … } }`，question 无 topicTags
  - 站内提交列表：**不存在 `recentSubmissionList`**；用 `submissionList(limit, offset) { hasNext lastKey submissions { id statusDisplay lang runtime timestamp url title } }`（节点 `SubmissionDumpNode` 无 titleSlug，slug 从 url `/problems/<slug>/` 正则提取）；未登录返回**空列表而非报错**
  - REST `/api/submissions/` 存在但需有效会话（401 JSON）
  - 判定接口【已真网回填】：submit 走 REST `POST /problems/{slug}/submit/` → 轮询
    `/submissions/detail/{id}/check/`；run 走 REST `POST /problems/{slug}/interpret_solution/`，
    **自定义用例字段名是 `data_input`**（多组用例直接换行拼接，浏览器同款）——曾因误用
    `input` 触发站点 Internal Error；轮询响应可能缺少 state/status_msg，完成判定需回退到
    code_answer/compile_error 等强标志字段
- **会话轮换陷阱**：重新登录 leetcode.cn 会使旧的 LEETCODE_SESSION 在服务端立即失效——本地 Cookie 文件再完好也无法通过校验；用户报「明明复制对了却提示失效」时优先怀疑此因，请以最新一次登录后复制的为准。后端已实现轮换自动持久化（响应下发新 Cookie 时写回 config.toml），但**出口 IP 变化仍会触发轮换**——JWT 内含 IP 字段，动态 IP/热点/代理切换用户需重新复制。
- **Windows 上 os.kill(pid, 0) 会杀进程**：CPython 在 Windows 把非 CTRL 信号一律走 TerminateProcess，信号 0 也不例外。进程存活探测必须用 ctypes `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)` + `GetExitCodeProcess == STILL_ACTIVE(259)`（见 cli.py `_pid_alive`）。
- **打包后 dist 定位链**：`ALGOCOACH_DIST` → 向上搜索仓库 `web/dist`（可编辑安装/源码态）→ 安装目录内 `server/webdist`（wheel 态，发布前需 npm build 后拷贝，package-data 打包）。三处都未命中则 API-only 模式，根路径返回 JSON 提示。
- **console_script 监听者是 python.exe**：Windows 下 pip 生成的 coach.exe 只是启动器，真正监听端口的进程名是 python——按端口清理进程时勿只匹配 coach.exe。
- **TestClient 需本地 base_url**：Origin/Host 守卫会拒绝非本机 Host，pytest 必须用 `TestClient(app, base_url="http://127.0.0.1:8000")`，curl POST 需带 `-H "Origin: http://localhost:5173"`。

## Cookie 失效识别（三形态）

- 403
- 302 重定向到登录页
- **200 + errors 载荷**：cn 站 GraphQL 会话过期常返回 200 + errors（认证失败信号），只看状态码会漏检。
- 三形态已由 `tests/test_integration_live.py` 覆盖真网回归（需 `ALGOCOACH_TEST_COOKIE`，
  手动 `pytest -m integration` 运行）。

## 重试纪律

- 自动重试**仅限幂等读请求**（题库拉取 / 模板查询 / 结果轮询）。
- **非幂等请求禁止自动重试**：run / submit / interpret 失败直接返回结构化错误由用户决定，
  否则会在站内造出重复提交（in-flight guard 只防前端防不住后端）。

## 429 限速处理

- 优先读取 `Retry-After`：**兼容整数秒与 HTTP-date 两种格式**，两种都要解析。
- 无头时指数退避 1s → 2s → 4s 封顶 30s。

## 前端与服务

- **SPA history 路由刷新 404**：FastAPI 需 catch-all 回退 index.html。
- **打包后 dist 定位**：pip 安装态下 `coach` 必须能定位 web/dist（package data /
  importlib.resources / 可配置路径），阶段 7 验收包含「安装态正常打开前端页面」。
- **本机 API 防护**：校验 Origin / Sec-Fetch-Site + Host 头。DNS rebinding 场景下缺失
  Origin 会穿透；dev 模式 Vite proxy 透传原始 Origin `http://localhost:5173` 必须在白名单；
  按方法分级——POST/PUT 等 state-changing 方法强制白名单 Origin（同源 fetch POST 也带
  Origin，不影响正常使用），仅 GET 允许缺失 Origin + Host 校验兜底。
- **多标签页同题双编辑**：接受 last-write-wins（localStorage 快照恢复仅覆盖「下次打开」场景）。
- **前端 i18n 缺键是静默的**：`t()` 找不到键时原样返回 key 字符串，界面会出现「cookie_invalid」
  这类裸键且无报错。新增服务端 `message_key` 或界面文案时，必须确认 zh/en 两份 catalog 都有
  对应条目（auth 横幅曾因此长期显示裸键）。
- **错误文案语言以 UI 语言为准**：服务端错误 payload 只保证 `message_key` 稳定，`message`
  文本跟随后端进程 locale；前端必须在 api 层集中按 message_key 翻译后再展示，
  各视图自行取 `error.message` 会导致中英混杂。
- **信息性行不得遮蔽错误通道**：Problems 页头曾把显示优先级排成
  `syncing > 成功提示 > 上次同步时间 > 错误文本`——只要成功同步过一次，后续任何同步
  失败的错误都永远渲染不出来（被「上次同步」分支短路）。教训：错误必须走独立通知
  通道（现为 toast store，错误驻留至手动关闭），页面内只保留信息性状态行；
  同一插槽内做优先级级联时，错误分支必须排在任何历史状态之前。
- **空 progress 快照 ≠ 同步完成**：`SyncEngine.progress()` 在「从未运行」与「刚完成」
  两种状态下都返回 `running:false`，区别仅在 started_at/finished_at 是否有值。
  前端轮询若把一切非 running 一律当完成，后端在同步中途重启（引擎归零）时会向用户
  假报「同步完成」。判定真实完成必须同时检查 `started_at || finished_at`。
- **致命错误与瞬态错误禁止共用一个状态**：工作台曾用同一个 errorText 承载「题目加载失败」
  与「保存/判定瞬时失败」，后者会把整个编辑器界面替换成错误卡，用户代码直接从视野消失。
  根因修复：加载失败才允许整页替换（loadError），操作失败一律走 toast 并保持界面存活。
- **测试客户端会归一化 URL 点段**：`client.put("/api/problem/../etc/...")` 在到达路由前就被
  httpx 折叠成合法路径（得到 404/405 而非守卫的 400），slug 白名单守卫要用「路径合法但
  字符集非法」的载荷测（如 `two.sum`）。（2026-08-24 已验证）
- **AbortSignal.timeout 需降级路径**：前端 fetch 统一加截止时间防「后端挂起永不返回」，
  但旧浏览器无该 API——封装处检测其存在性，缺失时退化为无超时而不是整个请求报错。
- **uvicorn 预绑定 socket 走 `Server.run(sockets=[...])` 而非 `Config(sock=)`**（2026-08-26 已修复）：
  `uvicorn.Config` 从不接受 `sock` 参数（只有 `fd`），传了会在启动瞬间
  `TypeError: unexpected keyword argument`——且只在真实启动路径暴露，单测若不真跑
  `server.run()` 根本抓不到。正确姿势：`uvicorn.Server(config)` 后
  `server.run(sockets=[sock])`，Config 里的 host/port 此时仅是兜底描述。
- **思考（thinking）参数没有跨厂商标准**（2026-08-26 落地时的设计约束）：DeepSeek 用
  独立模型名（deepseek-reasoner）、Qwen/DashScope 用 `enable_thinking`、GLM 用
  `thinking.type`、OpenAI 系用 `reasoning_effort`——同一语义四套参数，且严格校验的
  服务商对未知字段直接 400。因此 `llm_thinking` 的非默认档只映射最通用的 OpenAI 兼容
  约定（`enable_thinking` + `reasoning_effort`），`default` 档**一个额外字段都不发**；
  新增档位/字段前先想清楚这个兼容性矩阵，并让「测试连接」承担验证职责。
- **双 coach 实例并存**：由单实例守卫杜绝（绑定失败探测拒启 + instance.lock 锁文件封堵
  「端口顺延后新实例直接绑成功」盲区）；锁仅用于实例互斥而非数据文件加锁。若守卫被绕过仍按
  jsonl 单次小写入（O_APPEND 级别）接受 last-wins。

## 并发模型

- **async def 内调阻塞 requests 会卡死整个事件循环**：judge 长轮询、题库同步等长端点必须声明为普通 `def`（FastAPI 自动放入线程池）。
- **线程池并发下共享状态必须加锁**：限速间隔记账（2s+jitter）、同步进度计数、qid→最近判定增量索引——漏锁则并发穿透限速闸门、进度轮询读到半更新状态。
- **读-改-写必须整个落在同一临界区**（2026-08-24 已修复）：favorites 曾把 load 放在锁外、save 在锁内，
  两个并发切换不同收藏时「后写整份覆盖」会丢掉先写的那次变更；只锁写不锁读的 RMW 等于没锁。
- **破坏性端点必须与后台任务生命周期互斥**（2026-08-25 已修复）：`DELETE /api/local-data`
  曾只检查 running 标志就删目录，检查与删除之间可插入同步启动，在被清空的目录里重建半套数据。
  清除与 sync begin 现共用 `_lifecycle_lock` 串行化；清除后还须 `SyncEngine.reset()`，
  否则残留累加器会伪装成「可续传」快照指向已删除的数据。
- **auth 锁序全局固定为 `_persist_lock` → `_state_lock`**：configure/reset 与轮换持久化都按此序获取；
  反序获取会在 configure 换血与迟到响应持久化之间形成死锁窗口。
- **只有当前 client 可以持久化轮换 Cookie**（2026-08-25 已修复）：rebuild 后旧 client 的在途响应
  若仍触发 `_persist_rotated_cookies`，会把旧 jar 写盘覆盖新凭据。持久化前必须核对
  `_http_client is client`。
- **归档文件追加序 = 时间序是不变量**（2026-08-25 已维护）：`Archive.query` 的 newest-first
  直接依赖它。任何批量写入路径都必须先按时间戳升序排序再追加（站内 feed 是新→旧，直接追加即倒序）。

## 输入校验

- **Pydantic `X | None = None` 字段必须显式拒绝 null**（2026-08-25 已修复）：
  `exclude_unset` 区分「未传」与「显式 null」，但 null 值一旦进入处理链——数字字段
  `float(None)` 直接 TypeError 500，字符串字段被 `str(None)` 成 `"None"` 写进配置
  （之后 `Path("None")` 解析成相对目录）。规则：任一字段显式传 null 一律 422，
  提示省略字段即为保留现值；且该矩阵要逐字段测试，不能只测一个代表。
- **环境变量覆盖必须在启动期校验**（2026-08-25 已修复）：坏值若等到 `effective_config()`
  才爆炸，会让所有接口 500——包括本可用于修复它的 /api/settings。启动时
  `validate_environment()` 一次性校验并指名变量，coach 退出码 2。

## 前端与服务

- **SPA history 路由刷新 404**：FastAPI 需 catch-all 回退 index.html。
- **打包后 dist 定位**：pip 安装态下 `coach` 必须能定位 web/dist（package data /
  importlib.resources / 可配置路径），阶段 7 验收包含「安装态正常打开前端页面」。
- **本机 API 防护**：校验 Origin / Sec-Fetch-Site + Host 头。DNS rebinding 场景下缺失
  Origin 会穿透；dev 模式 Vite proxy 透传原始 Origin `http://localhost:5173` 必须在白名单；
  按方法分级——POST/PUT 等 state-changing 方法强制白名单 Origin（同源 fetch POST 也带
  Origin，不影响正常使用），仅 GET 允许缺失 Origin + Host 校验兜底。
- **多标签页同题双编辑**：接受 last-write-wins（localStorage 快照恢复仅覆盖「下次打开」场景）。
- **前端 i18n 缺键是静默的**：`t()` 找不到键时原样返回 key 字符串，界面会出现「cookie_invalid」
  这类裸键且无报错。新增服务端 `message_key` 或界面文案时，必须确认 zh/en 两份 catalog 都有
  对应条目（auth 横幅曾因此长期显示裸键）。同一领域概念（如判定文案）禁止两处各自实现映射——
  History 曾绕过 verdict_* 目录显示原始英文枚举；已收敛到共享 `utils/verdict.js`。
- **错误文案语言以 UI 语言为准**：服务端错误 payload 只保证 `message_key` 稳定，`message`
  文本跟随后端进程 locale；前端必须在 api 层集中按 message_key 翻译后再展示，
  各视图自行取 `error.message` 会导致中英混杂。
- **信息性行不得遮蔽错误通道**：Problems 页头曾把显示优先级排成
  `syncing > 成功提示 > 上次同步时间 > 错误文本`——只要成功同步过一次，后续任何同步
  失败的错误都永远渲染不出来（被「上次同步」分支短路）。教训：错误必须走独立通知
  通道（现为 toast store，错误驻留至手动关闭），页面内只保留信息性状态行；
  同一插槽内做优先级级联时，错误分支必须排在任何历史状态之前。
- **致命/瞬态错误分离是全站约定，不是单页特例**（2026-08-25 补齐 Analyze）：
  「首次加载失败才允许整页替换；操作失败一律行内/toast 并保持界面存活」。工作台修过一次后
  分析页仍复发了同类 bug（LLM 生成失败炸掉整页统计），新页面落地时必须主动套用该模式。
- **跨请求存续的派生状态不得从单次响应重建**：Analyze 的 AI 报告曾每次 reload 都用
  响应体里的 ai_report（普通刷新恒为 null）覆写本地 HTML——用户刚花 1–2 分钟生成的报告
  被静默清空。仅在响应真正携带报告时才更新。
- **IME 组合输入期间 Enter 不是提交意图**：中文输入法确认候选词走 Enter，事件带
  `isComposing=true`（或 keyCode 229）。所有「Enter 发送/提交」入口必须检查组合态，
  否则中文用户会不断发出半截拼音。（2026-08-25 已修复 AI 输入框）
  测试提示：VTU `trigger('keydown', {...})` 不设置 `key` 会被 Vue 的 `.enter` 修饰符过滤、
  且原型只读属性要用 `Object.defineProperty` 模拟——直接构造 KeyboardEvent 再 dispatch 更可靠。
- **「清除全部数据」的范围包括浏览器侧**（2026-08-25 已修复）：编辑器草稿快照存在 localStorage，
  服务端擦除后 `solution_mtime` 归零会让所有快照看起来"更新"，旧代码以恢复条形式复活。
  擦除动作必须同时清除 `algocoach-snapshot:*`（主题/语言等偏好类保留）。
- **URL query 是筛选状态的唯一事实源**：列表筛选若只在 query 出现时单向写入，
  用户手动改回默认值后 URL 与实际过滤态脱钩。query 变化时对它承载的每个键做全量赋值
  （缺席即重置为默认）。
- **CodeMirror 默认语法高亮只有浅色调色板**：暗色模式下需自备 HighlightStyle
  （`@lezer/highlight` 为 CodeMirror 官方包，已列入依赖政策白名单）；容器 chrome 用
  设计 token 的 CSS 变量即可自动随 `data-theme` 切换。
- **AbortSignal.timeout 需降级路径**：前端 fetch 统一加截止时间防「后端挂起永不返回」，
  但旧浏览器无该 API——封装处检测其存在性，缺失时退化为无超时而不是整个请求报错。
- **双 coach 实例并存**：由单实例守卫杜绝（绑定失败探测拒启 + instance.lock 锁文件封堵
  「端口顺延后新实例直接绑成功」盲区）；锁仅用于实例互斥而非数据文件加锁。若守卫被绕过仍按
  jsonl 单次小写入（O_APPEND 级别）接受 last-wins；同理，「清除数据瞬间恰有判题在途」时
  该条结果落进新建归档属可接受的 last-wins，不视为复活 bug。

## 已知限制（明示决策，非遗留 bug）

- v0.1 题面 LaTeX 公式以原文展示、图片断网失效（不做图片本地化，KaTeX 见 ROADMAP）。
- 站内提交列表（`submissionList(limit, offset)`，见上）仅能取到最近约 20 条。
- Windows 上 chmod 无 POSIX 权限语义，`~/.algocoach` 安全性依赖「仓库外存储 + 用户目录」保护。
- 桌面优先工具：移动端/触屏无适配（三栏拖拽工作台 + mouse 事件拖拽），见 ROADMAP【延】。
