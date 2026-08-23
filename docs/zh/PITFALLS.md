# PITFALLS

> **开发前必读。** 解决新坑后必须回填本文件。

## 站点与请求

- **Referer 缺失导致 403**：对 leetcode.cn 的 GraphQL 请求需注入浏览器 UA + Referer + csrfToken。
- **内部 question_id ≠ 前端题号**：frontendQuestionId 可能非纯数字（如「剑指 Offer 03」「面试题 17.16」「LCP 07」，含空格与中文）。规范键一律用 slug；题号全数字时目录命名 `0001-two-sum/`，否则直接用 slug。
- **UA 风控**：使用真实浏览器 UA。
- **每日一题时区**：以 00:00 UTC+8 为界。
- **自定义用例输入序列化格式**：testcases.txt 与远程 interpret 接口的输入格式转换需注意（实现时验证并在此记录）。
- **GraphQL 字段名待真网回填**：sites/cn.py 的查询文档与字段名（如 `titleCn`/`nameTranslated`/`categoryTitle`/`todayRecord`）基于公开 schema 组织。阶段 2 冒烟已验证 `/graphql` 端点连通与 Cookie 失效识别链路；字段级验证在题库全量同步真网 integration 时逐一确认，差异回填本条目。
- **判定接口形态待真网验证**：submit 走 REST（POST /problems/{slug}/submit/ → 轮询 /submissions/detail/{id}/check/），run 走 GraphQL interpretSolution mutation 后复用同一 check 端点轮询；结果分类优先依据 status_msg 文本而非 status_code 数字（两站数字语义有漂移风险）。真网实测 two-sum 与剑指 Offer 后回填差异。
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
