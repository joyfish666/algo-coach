# PITFALLS

> **开发前必读。** 解决新坑后必须回填本文件。

## 站点与请求

- **Referer 缺失导致 403**：对 leetcode.cn 的 GraphQL 请求需注入浏览器 UA + Referer + csrfToken。
- **内部 question_id ≠ 前端题号**：frontendQuestionId 可能非纯数字（如「剑指 Offer 03」「面试题 17.16」「LCP 07」，含空格与中文）。规范键一律用 slug；题号全数字时目录命名 `0001-two-sum/`，否则直接用 slug。
- **UA 风控**：使用真实浏览器 UA。
- **每日一题时区**：以 00:00 UTC+8 为界。
- **自定义用例输入序列化格式**：testcases.txt 与远程 interpret 接口的输入格式转换需注意（实现时验证并在此记录）。
- **GraphQL 字段名【已真网回填 2026-08-23】**：cn 站实测确认——
  - 题库列表：顶层 `problemsetQuestionList(categorySlug, limit, skip, filters)` 直接调用（**不存在**底层 `questionList` 字段）；行节点是 `QuestionLightNode`，字段为 `acRate / difficulty / title / titleCn / titleSlug / paidOnly / frontendQuestionId / topicTags { slug name nameTranslated }`（CommonTagNode）；**没有** `isPaidOnly`、`categoryTitle`、`translatedTitle`、`questionFrontendId`
  - 题目详情：`question(titleSlug:)` 节点用 `translatedTitle`（**无 `titleCn`**），标签节点是 `TopicTagNode` 用 `translatedName`，含 `exampleTestcases` 与内部 `questionId`（判定接口必需）
  - 每日一题：`todayRecord { date question { … } }`，question 无 topicTags
  - 站内提交列表：**不存在 `recentSubmissionList`**；用 `submissionList(limit, offset) { hasNext lastKey submissions { id statusDisplay lang runtime timestamp url title } }`（节点 `SubmissionDumpNode` 无 titleSlug，slug 从 url `/problems/<slug>/` 正则提取）；未登录返回**空列表而非报错**
  - REST `/api/submissions/` 存在但需有效会话（401 JSON）
  - 判定 submit/interpret 形态仍未实测（需有效会话），维持「status_msg 文本优先分类」策略，实测后回填
- **会话轮换陷阱**：重新登录 leetcode.cn 会使旧的 LEETCODE_SESSION 在服务端立即失效——本地 Cookie 文件再完好也无法通过校验；用户报「明明复制对了却提示失效」时优先怀疑此因，请以最新一次登录后复制的为准。
- **Windows 上 os.kill(pid, 0) 会杀进程**：CPython 在 Windows 把非 CTRL 信号一律走 TerminateProcess，信号 0 也不例外。进程存活探测必须用 ctypes `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)` + `GetExitCodeProcess == STILL_ACTIVE(259)`（见 cli.py `_pid_alive`）。
- **打包后 dist 定位链**：`ALGOCOACH_DIST` → 向上搜索仓库 `web/dist`（可编辑安装/源码态）→ 安装目录内 `server/webdist`（wheel 态，发布前需 npm build 后拷贝，package-data 打包）。三处都未命中则 API-only 模式，根路径返回 JSON 提示。
- **console_script 监听者是 python.exe**：Windows 下 pip 生成的 coach.exe 只是启动器，真正监听端口的进程名是 python——按端口清理进程时勿只匹配 coach.exe。
- **TestClient 需本地 base_url**：Origin/Host 守卫会拒绝非本机 Host，pytest 必须用 `TestClient(app, base_url="http://127.0.0.1:8000")`，curl POST 需带 `-H "Origin: http://localhost:5173"`。

## Cookie 失效识别（三形态）

- 403
- 302 重定向到登录页
- **200 + errors 载荷**：cn 站 GraphQL 会话过期常返回 200 + errors（认证失败信号），只看状态码会漏检。
- 实测形态清单待真网 integration 验证后回填。

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
- **双 coach 实例并存**：由单实例守卫杜绝（绑定失败探测拒启 + instance.lock 锁文件封堵
  「端口顺延后新实例直接绑成功」盲区）；锁仅用于实例互斥而非数据文件加锁。若守卫被绕过仍按
  jsonl 单次小写入（O_APPEND 级别）接受 last-wins。

## 并发模型

- **async def 内调阻塞 requests 会卡死整个事件循环**：judge 长轮询、题库同步等长端点必须声明为普通 `def`（FastAPI 自动放入线程池）。
- **线程池并发下共享状态必须加锁**：限速间隔记账（2s+jitter）、同步进度计数、qid→最近判定增量索引——漏锁则并发穿透限速闸门、进度轮询读到半更新状态。

## 已知限制（明示决策，非遗留 bug）

- v0.1 题面 LaTeX 公式以原文展示、图片断网失效（不做图片本地化，KaTeX 见 ROADMAP）。
- recentSubmissionList 仅能取最近约 20 条。
- Windows 上 chmod 无 POSIX 权限语义，`~/.algocoach` 安全性依赖「仓库外存储 + 用户目录」保护。
