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
| 4 | 答题工作台：ProblemDetail + CodeEditor + Run/Submit + 结果面板 + 自定义用例面板 | ✅ 已完成（two-sum 全流程真网实测通过，见下方回归表） |
| 5 | 题库列表页 + setup 向导 + daily | ✅ 已完成（真网联调回归通过，2026-08-23） |
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

### 第一批

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

### 第二批（功能补全 + 深度体检，2026-08-24）

| 类别 | 交付/修复 | 根因 |
|---|---|---|
| 功能 | 题库状态筛选（已通过/尝试过/未做/收藏）、收藏索引 favorites.json、随机一题、紧凑密度 | 归档已有练习态数据但列表查询未暴露；列表页需对全量题目渲染收藏态而工作区目录只为打开过的题目存在 → 独立索引文件 |
| 功能 | `/history` 提交历史页 + `Archive.query()` 加锁扫描原语（?qid 过滤） | 归档数据无处回看；recent/query 各自扫档会漂移 → 收敛为单一原语 |
| 功能 | 每题笔记 notes.md（debounce 自动保存，refresh 不触碰） | 复盘沉淀无落点；沿用 solution 的用户所有语义 |
| 功能 | AI 提问可显式附带当前编辑器代码（截断 6000 字符） | 整题上下文不含代码本体，报错分析无从谈起；显式附带避免每次闲聊都上传长代码 |
| Bug | 同步失败错误永不显示 | 页头显示优先级把历史状态排在错误之前；错误改走独立 toast 通道（错误驻留至关闭） |
| Bug | 保存瞬时失败炸掉整个工作台 | 致命/瞬态错误共用一个 errorText → 分离 loadError（整页替换）与 toast（保持界面存活） |
| Bug | 切页丢同步进度；后端重启后假报「同步完成」 | 轮询归视图所有（跨路由即失联）；progress 空快照与完成态不可区分（缺 started_at/finished_at 校验）→ 轮询上移应用级 sync store + 真实完成判定 |
| UI | 语义色 token（ok/warn/danger）贯穿难度 chip、判定结果、banner；暗色卡片层次恢复 | 全局仅一个 accent 蓝，难度/通过失败无视觉差；暗色 shadow:none 致边界融化 |
| UI | 列表加载骨架屏、快捷键常驻提示（Ctrl↵ / Ctrl+⇧↵）、toast 统一反馈 | 纯文本空态感知等待差；快捷键只藏于 title 属性 |
| 逻辑 | 前端 fetch 统一截止时间（默认 45s，LLM/提交 150s，AbortSignal.timeout 缺失时降级） | 无超时则后端挂起时视图永久冻结 |
| 测试 | 新增 Problems/History/Daily/Analyze/Settings 视图测试、sync/toast store 测试、路由 smoke（36→78 用例）；后端新增收藏/笔记/历史/AI-code/API 用例（188→199）；i18n 键一致性校验脚本入 CI（首跑即抓到 auth 横幅裸键漏网）；pytest-cov 默认输出覆盖率 | 视图零测试区正是错误遮蔽 bug 的藏身处；t() 缺键静默无护栏；覆盖率盲区不可见 |
| 文档 | ARCHITECTURE 存储/契约同步；USAGE 新功能与报错对照；PITFALLS 回填 5 条新坑；DEVELOPMENT 补 check:i18n 与覆盖率用法；双语 README 功能清单同步 | 文档落后于实现 |

### 第三批（三维度复查，2026-08-24）

| 类别 | 交付/修复 | 根因 |
|---|---|---|
| 逻辑 | favorites 读-改-写竞态：并发切换两个不同收藏可能互相覆盖丢失其一 | RMW 拆在两个公有函数里，锁只护住写半程、读半程裸奔 → 整个读-改-写收敛到同一临界区（附并发回归测试） |
| 逻辑 | `GET /api/problem/{qid}/template` 省略 `?lang=` 时永远回退 cpp | 唯一硬编码默认值的端点；其余端点均读配置 default_language → 统一从 `_default_lang()` 取默认 |
| 逻辑 | `PUT /api/settings` 显式传 `cookie:null` 被静默忽略 | Pydantic exclude_unset 区分「未传」与「显式 null」，但 null 分支两头落空 → 按项目「宁可报错不可静默」惯例返回 422 |
| 逻辑 | Run 本地用例文件 exists→read 之间存在 OSError 窗口（→500） | 与 cases.json 分支错误策略不一致（后者捕获 OSError）→ 两分支对齐同一降级语义 |
| UI/逻辑 | 未匹配的 `/api/*` 路径误报「未找到该题目」 | SPA 回退复用了题目域的文案键 → 改为通用 not found（客户端路径笔误≠题目缺失） |
| UI | 工作台「N × hint」英文硬编码、笔记占位符中文硬编码、设置页主题行标签误用 `theme_system` 键（显示为「跟随系统」）、账号卡请求失败时显示假的「API: 127.0.0.1:8000」 | 文案绕过 i18n catalog；check:i18n 只能查 t() 引用的键，拦不住不经过 t() 的字符串 → 全部收编进 catalog；失败态显示中性占位符而非编造状态 |
| UI | History 加载态借用 Analyze 的「正在统计…」文案；日期时间跟随浏览器语言而非界面语言（zh 界面 + en 浏览器出现 AM/PM） | 复制粘贴复用近义键；日期格式化散落各视图各自调 toLocaleString → History 专用 loading 键；日期格式化收敛到 i18n store 的 formatDateTime（附单测） |
| UI | 分析页 AI 报告禁用提示引导用户去「设置页」配置 LLM Key，但设置页并无该表单 | 文案与页面能力漂移（LLM 配置只在 /setup 第二步）→ 文案改指引导配置页 |
| 测试 | 最具破坏性的 `DELETE /api/local-data` 零测试覆盖；template 默认值、settings null cookie、未知 API 路径均无断言 | 端点越危险越晚写测试的风险倒挂 → 补齐擦除保留 lock/409 并发拒绝/配置默认语言/null 拒绝/通用 404 共 5 个后端用例（199→204），前端 formatDateTime 单测 2 例（78→80） |
| 文档 | README 状态行停留在「v0.1.0 开发中的骨架」与 ROADMAP/CHANGELOG 的已交付事实矛盾；ROADMAP 阶段行「待真网实测」与下方验证表矛盾；PITFALLS 内文自引不存在的 `recentSubmissionList` 字段名；USAGE 设置页承诺不存在的 LLM 表单、`?debug=1` 暗示值敏感 | 文档更新只增不改旧账 → 本次全部对齐实现现状 |

### 第四批（用户/开发者双视角体检，2026-08-25）

| 类别 | 交付/修复 | 根因 |
|---|---|---|
| 逻辑 | `PUT /api/settings` 只有 cookie 有显式 null 守卫：`request_interval:null` → TypeError 500；字符串字段 null → 把字面量 "None" 写进 config.toml（之后 workspace_root 解析成相对目录 `Path("None")`） | 「显式 null ≠ 未传」的 fail-loud 约定只落在一个字段上，未成为端点级统一规则 → 所有字段统一 422 |
| 逻辑 | 清除数据与同步启动存在 TOCTOU：检查 running 与删除目录之间可插入 begin()，被清空的目录里重建出半套缓存；清除后引擎残留累加器还会伪装成「可续传」快照 | 破坏性端点与后台任务生命周期没有共享互斥 → 引入 `_lifecycle_lock` 串行化两侧，清除时同步 `SyncEngine.reset()` |
| 逻辑 | 站内导入按 feed 序（新→旧）追加，而归档查询以文件追加序为时间序：批次截断后「最新」位置实为批次内最旧记录 | 追加时序不变量未在写入侧维护 → 批次按时间戳升序排序后再追加 |
| 逻辑 | 判题上下文缺内部题号时静默回退 slug 提交，站点报晦涩错误被包成 502 | 兜底链把「必然失败的请求」当默认路径而非显式报错 → 缺 id 直接 422（新增 judge_missing_question_id 文案键） |
| 逻辑 | Cookie 轮换持久化只重组两个管理键，用户粘贴的其余 cookie 对在首次轮换后被无声剥离；且被替换旧 client 的迟到响应可把旧 jar 回写覆盖新凭据 | 持久化逻辑把 cookie 串视为两键所有、把 client 身份视为永久有效 → 改为向原串合并保序保留其余键对；仅当前 client 可写（锁序 _persist→_state 全局一致） |
| 逻辑 | 工作区文件（题面/用例/meta/代码/笔记）是全仓唯一非原子写，并发读可能读到半截内容 | 原子写纪律只在 config/缓存/归档落地，工作区漏掉 → 收敛到统一 `_atomic_write_text` 原语 |
| 逻辑 | 一个格式错误的 `ALGOCOACH_*` 环境变量让所有接口 500——包括本可用于修复它的 /api/settings | 配置错误在每次读取点爆炸而非启动门口失败一次 → `validate_environment()` 启动期校验并指名变量，coach 退出码 2；端口耗尽同样给友好提示替代裸栈 |
| 功能 | `llm_timeout` 纳入 settings API（GET 脱敏视图 + PUT [5,600] 越界拒绝） | 该键是唯一只能改 toml/env 的配置项，管理面与其余设置不一致 |
| 安全 | mask_secret 对 >8 字符即露尾 4：12 位 token 泄漏约 1/3 熵；独立校验 Session 不关闭靠 GC | 泄漏比例阈值缺失 → <16 字符全遮；Session 换血/重置时显式 close |
| UI | AI 输入框 IME 组合期间 Enter 直接发送半截拼音（中文核心用户伤害最大）；Analyze 页 LLM 生成失败炸掉整页统计、普通刷新清空刚生成的报告；Run/Submit 并行竞速互相覆盖判定结果；语言切换窗口期可发出 lang/code 错配请求 | 工作台已修过的「致命/瞬态错误分离」「单一 inflight 门」教训未应用到这些后写页面 → Analyze 拆分 loadError/actionError 且报告跨刷新保留；judgingBusy 单门互斥三类操作 |
| UI | History 结果列显示原始英文枚举（wrong_answer），与工作台的 verdict_* 翻译同概念两套呈现；「清除全部数据」后浏览器侧草稿复活弹出恢复条；筛选与 URL query 单向脱钩；灰字对比度 2.1:1/2.9:1 远低于 WCAG AA；暗色模式编辑器语法高亮仍是浅色调色板 | 映射逻辑重复实现各自漂移 → 抽取共享 verdict 工具；擦除范围遗漏 localStorage 快照 → 擦除时一并清除（偏好类保留）；query 作为唯一事实源；token 重校色；编辑器接入 @lezer/highlight 双调色板随 data-theme 切换 |
| UI | 小项集中修：AI 面板 Esc 关闭+越界重钳制（原 clamp 允许下缘出屏 120px）、status 启动双请求合并、theme 监听防堆叠、sync 轮询防重叠、debug 关闭还原 console.error、Vue 渲染错误进调试日志、/setup 页不再叠加全局 Cookie 失效横幅、导入成功/失败同色、掌握度图 tooltip 补全名与数字含义、🎲 emoji 换 SVG 图标、判定面板隐藏无意义的 "0 / 0"、死标记清理 | 各自独立的小型一致性缺陷，逐一对齐既有设计约定 |
| 测试 | 后端 204→216（settings null 矩阵 / llm_timeout 边界 / mask 阈值 / 引擎重置 / 缺 id 显式失败 / 无 .tmp 残留 / 导入时序 / 陈旧 client 禁写 / 键对保留 / env 校验指名）；前端 80→89（IME 组合、Esc+重钳制、报告跨刷新保留、行内生成错误、快照清除、本地化历史 chip、JudgeResultPanel 首个直测套件） | 上表每项修复各配回归测试，非法输入维度的盲区与缺陷一一对应 |

### 第五批（UI 极简化 + LLM 设置解耦，2026-08-26）

| 类别 | 交付/修复 | 根因 |
|---|---|---|
| 功能 | LLM 配置从 `/setup` 向导（3 步→2 步：Cookie+偏好）解耦到设置页独立「AI（LLM）」卡片：Key/地址/模型随时可改，与 Cookie 互不影响 | LLM 与 Cookie 生命周期完全不同（Cookie 会过期、LLM 是增值能力），捆在首启向导里导致「改个 Key 要重走向导」且设置页无表单可改 |
| 功能 | `POST /api/llm/test` 连通性探测：表单值覆盖已存配置（缺省回退）、`max_tokens` 限幅 ping、30s 超时上限；卡片显示模型名+实测延迟或服务端错误原文 | 「保存后才知道配得对不对」反馈链太长；测试与保存分离（测试不落盘） |
| 功能 | 思考模式 `llm_thinking`（default/off/low/medium/high）：非默认档映射 OpenAI 兼容 `enable_thinking`+`reasoning_effort`，default 不发任何额外字段；PUT 校验 422；环境变量 `ALGOCOACH_LLM_THINKING`；「测试连接」承担验证 | 各厂商思考参数四套标准且严格服务商对未知字段 400 → 只映射最大公约数、默认档绝对安全（PITFALLS 已回填兼容性矩阵） |
| UI | 极简白风格落地：白色侧边栏+发丝分割线+灰色胶囊激活态、近黑主按钮、卡片大圆角轻描边、eyebrow 大写小标签、主题/语言开关统一 32px 控件高度 | 视觉噪声来自灰底侧栏/彩色主按钮/过重描边等执行层细节，而非配色 token 本身 |
| UI | AI 教练面板标题栏「清空对话」按钮（回复中/空会话禁用，不干扰拖拽） | 长对话只能靠切题重置，无主动清空入口 |
| 逻辑 | `POST /api/analyze` 的 `ai_configured` 只在 `use_llm=true` 分支计算，而页面初载恒传 `use_llm=false` → 报告按钮永不出现（Key 已保存也显示「未配置」） | 可用性判定与「本次是否生成」两个正交概念被写进同一分支 → `ai_configured` 恒由保存配置推导（附回归测试） |
| 逻辑 | `coach` 启动即崩：`uvicorn.Config(sock=...)` 从不接受该参数 | 预绑定 socket 应走 `Server.run(sockets=[...])`；真实启动路径无测试覆盖 → 修复并回填 PITFALLS |
| 测试 | 后端 216→227（llm/test 六用例：未配置 400/保存配置/payload 覆盖/部分回退/NetworkError→502/未知字段 422；thinking 映射与校验；analyze ai_configured 回归）；前端 89→90（清空对话按钮状态机） | 新端点与映射逻辑逐分支配测试；测试污染（类属性赋值泄漏）改用 monkeypatch 自动还原 |

### 第六批（用户/开发者双视角体检，2026-08-28）

| 类别 | 交付/修复 | 根因 |
|---|---|---|
| Bug | 工作台挂载/切题即静默损坏已保存代码：`loadProblem` 先赋 `problem.value` 再改 `lang.value`，而 Vue watcher 异步 flush，`!problem.value` 守卫在回调执行时已失效——加载被当成「用户切换语言」，把刚加载的代码用**旧语言** PUT 覆盖无关的 `solution.*`，随后再用新模板覆写编辑器内容 | 「程序化赋值」与「用户切换」两个事件共用一个无差别 watcher；守卫只检查赋值时点的快照，不检查 flush 时点 → 引入跨 nextTick 的 hydration 栅栏，程序化赋值（加载/模板应用/切换失败回退）全程抑制 watcher |
| Bug | 切换语言模板拉取失败回退选框时，watcher 再次触发把当前（旧语言）代码写到失败语言的文件里 | 回退赋值与用户切换不可区分 → 同一 hydration 栅栏覆盖回退路径 |
| 功能 | 重开题目续用上次语言：`read_problem_state` 返回最近写入的 `solution.*`（mtime 最新）而非配置默认语言 | 两侧都没有「这题上次用什么语言」的记忆——python3 用户重开题目落在空白的 C++ 编辑器里，代码其实还在盘上但无从知晓；模板拉取与判定前保存都恰好更新对应语言文件的 mtime，它就是天然的「上次在玩哪个语言」记录 |
| 功能 | AI 教练面板未配置 LLM 时显示引导横幅（含设置页链接）并禁用发送；`GET /api/status` 新增 `llm_configured` | 分析页有未配置门控而工作台没有，用户只能靠每次发送失败的错误气泡发现缺 Key——两个 LLM 入口共用状态却各写一套门控 |
| 功能 | 分析页报告渲染后出现「重新生成」按钮 | 报告存在与否曾是生成按钮的唯一开关，导入新提交后无法刷新报告 |
| 逻辑 | config.toml 多个整文件写者（设置保存/轮换持久化/清除数据）各自为政：设置保存可被并发轮换持久化的旧快照整体回滚；清除数据后未过 still-current 复核的在途持久化可把已擦除的 Cookie 复活进新 config.toml | 互斥锁放在了某一个调用方（auth._persist_lock）而不是文件旁边 → 锁收敛进 `lc.config.update_lock()`；持久化的 still-current 复核移入临界区内部；清除数据先重置 auth 再删文件 |
| 逻辑 | Windows 上 `os.replace` 与无锁读冲突：CPython 打开文件不带 FILE_SHARE_DELETE，并发读者（GET /api/problems 流式读 problems.json）会让原子替换抛 PermissionError → 随机 500/假同步失败 | 「原子替换使裸读安全」只在 POSIX 成立 → 新建 `lc/atomicio.py` 单点原语：有界重试吸收微秒级读者窗口，config/favorites/problems cache/工作区四处写盘全部收敛 |
| 逻辑 | 提交成功后归档 append 的 OSError 会把已无法重放的判定包成 500，诱导用户重复提交 | 致命（提交）与瞬态（落盘）错误策略未对齐 → 归档失败降级为 `archived:false` + 前端 toast 提示 |
| 逻辑 | `read_problem_state` 里 statement/code/testcases 三个裸读没有 OSError 守卫（同函数的 cases/notes 却有）；模板读取同样裸奔 | 同一模块内降级策略漂移 → 统一「瞬时读失败降级为空」 |
| 逻辑 | 429 的 `Retry-After` 原样照睡：恶意/故障响应头可让同步线程睡一天且无法取消 | 退避有封顶而 Retry-After 没有 → 重试等待同样封顶 30s（抛出的 RateLimitError 仍携带原值供响应头使用） |
| 逻辑 | LLM 返回 `content: null`（推理型端点/思考耗尽 max_tokens）被 `str(None)` 成字面量 "None" 当回答返回 | 形状守卫只捕缺失/结构错误，不捕 None → 视为空回答报错，`reasoning_content` 非空时先回退（否则 max_tokens 限幅的连接测试对思考模型必失败） |
| 逻辑 | 单实例守卫两个漏洞：O_EXCL 建文件与写 payload 之间的零字节窗口会被第二个并发启动当成「陈旧锁」删掉赢家的锁（双双存活）；退出时无条件 unlink 会删掉接管者的锁 | 锁内容与锁存在性被当成同时成立；释放不核对归属 → 零字节窗口给短宽限期（期间重读），释放仅当 payload 记录的 pid 是自己 |
| 逻辑 | 手改的/未来版本的 config.toml 让服务正常启动后所有接口 500 | 配置文件没有像环境变量一样在启动门口失败 → `coach` 启动时 `effective_config()` 探测，失败打印文件路径并退出码 2 |
| 逻辑 | `ALGOCOACH_REQUEST_INTERVAL=0.01` 启动通过，静默关掉限速闸门 | 范围策略只定义在 settings API 一处，env 覆盖旁路 → 边界常量上移 `lc.config`，`validate_environment` 与 API 共用同一策略 |
| UI/逻辑 | `HTTPException(detail=t(key))` 端点（404 题目/409 同步冲突/400 未配置 LLM 等）从不携带 message_key，前端只能显示后端进程 locale 渲染的文本；前端补齐了 10 个缺失的后端 message_key（10/15 曾缺失） | 结构化错误形状只覆盖领域异常一条路 → 统一 `http_domain_error()` 助手让 HTTPException 也携带 message_key；前端 api 层识别 `detail.message_key` |
| UI | 后端已重启/断连时前端裸显英文 "Failed to fetch"；History 筛选无结果显示「还没有提交记录」；工作台难度 chip 显示原始英文枚举；工作台在侧边栏无激活态；导航滚动位置跨页残留 | 浏览器网络异常未做归一化；空态一稿两用；难度映射漏了工作台一处；路由记录与 /problem/:qid 无前缀关联；无 scrollBehavior → api 层 TypeError 归一为本地化文案；History 区分两种空态；复用 diff_* 目录；problem-detail 高亮题库项；补 scrollBehavior |
| UI | 重新部署后旧标签页引用的哈希 chunk 404，被 SPA 回退改写成 index.html（JS 请求收到 HTML），所有点击静默失效 | catch-all 回退不区分「深链路径」与「资源路径」→ 资源形态（含扩展名）未命中一律 404；router.onError 检测 chunk 失败后整页刷新接管 |
| UI/逻辑 | 笔记自动保存只在切换/离开时被取消而非冲刷（最后一次按键永久丢失）；代码快照每次按键同步写 localStorage | 代码与笔记两套 debounce 只有一套有 flush 路径；快照写入没有防抖 → 离开/切题/关闭三处统一 flush（显式传旧 qid 防错题写入）；快照 300ms 防抖 |
| 测试 | i18n 平价无护栏：check:i18n 只能查字面 `t('...')`，服务端驱动的动态 `t(key)` 全部不可见（后端 15 键缺 11 个仍全绿）；check 脚本目录形状变了会提取到 0 键并静默全绿 | 动态键用法超出静态扫描能力 → 新增 pytest 平价测试（后端 catalog ⊆ 前端两 locale 块）+ 提取零键 fail-loud + 防空转锚定 |
| 测试 | conftest 重置不覆盖同步引擎单例：任一同步用例失败会把 `_running/_failed/rows` 泄漏给后续用例（409 级联或跨数据目录「续传」）；3 个测试文件手搓 `_archive = None` 第二套重置习语 | reset_app_state 只重置了归档 → 收敛（引擎并入 reset_app_state），手搓处全部改调用 |
| 测试 | 打包契约零验证：vite 产物 web/dist → server/webdist 的拷贝只存在于 DEVELOPMENT.md 的 POSIX shell 片段里，漏拷会发出 UI-less wheel 且无任何环节能发现 | 契约只写在文档里 → `npm run dist`（跨平台 copy 脚本）+ CI 新增 package job：构建后 `python -m build` 并断言 wheel 内含 `server/webdist/index.html` |
| 测试 | 覆盖率纯装饰：`--cov` 在 addopts 里 9 个 CI 矩阵格各算一遍且从无门槛无消费；CI 注释错误声称 3.10/3.11 都走 TOML 回退解析（tomllib 3.11 已内置，只有 3.10 走回退）；ruff 未锁版本；pytest 矩阵无 pip 缓存；test_cli_guard 有一处恒真断言 | 覆盖率加在没人看的位置 → 移出 addopts，CI 单格 `--cov-fail-under=80`（当前 87%）；其余逐项修正 |
| 文档 | 本批全部改动同步进 USAGE / ARCHITECTURE / DEVELOPMENT / PITFALLS（新增 7 条坑）与双语 README | 文档随实现同步是仓库既定规则 |

### 登记【延】

- **浏览器级 E2E（Playwright 等）**：当前以路由 smoke（全部懒加载 chunk 可解析 +
  守卫重定向断言）+ 各视图挂载测试替代主干回归。引入浏览器 E2E 意味着新增重型
  devDependency 与 CI 浏览器安装成本，与本仓库最小依赖政策冲突，待主干功能稳定
  后再评估。
- **移动端/触屏适配**：产品定位为桌面优先工具——三栏拖拽分割的工作台布局、
  mousedown/mousemove 拖拽交互在窄屏与触屏上均不可用，当前仅分析页有一处
  <960px 断点。完整的响应式改造需要重排工作台信息架构，成本远超打磨范畴；
  待 v1.x 结合真实移动使用需求评估。
- **同步任务主动取消**：同步引擎只有 begin/progress，无法中途终止
  （删除数据靠 lifecycle 锁互斥规避）。需要协作式取消标志 + UI 取消按钮，
  待出现真实需求再评估。

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
