# DEVELOPMENT

面向开发者的环境搭建与日常流程。

## 后端

要求 Python ≥ 3.10。

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
ruff check .                   # CI 会跑，提交前先本地过一遍
pytest                         # 快速全量回归（HTTP 全 mock）
pytest --cov=lc --cov=server --cov-report=term-missing   # 需要看覆盖率时显式加上
```

- 单元测试 HTTP 全 mock，不真连网络；默认通过 pyproject `addopts` 排除
  `integration` 标记（CI 同样不跑）。
- 覆盖率**不在**默认 pytest 里：CI 在 ubuntu/py3.12 单格计算并以
  `--cov-fail-under=80` 设门槛（当前约 87%），本地全矩阵各算一遍纯属浪费；
  需要时按上面命令显式开启，只看某个文件：
  `pytest tests/test_archive.py --cov=lc.archive --cov-report=term-missing`。
- 真网回归用例集中在 `tests/test_integration_live.py`，手动运行：

  ```bash
  ALGOCOACH_TEST_COOKIE="csrftoken=...; LEETCODE_SESSION=..." pytest -m integration
  ```

  未设置该环境变量时用例自动 skip。

## 前端

要求 Node.js ≥ 18。

```bash
cd web
npm install
npm run dev         # http://localhost:5173
npm run build       # 产物 web/dist/
npm run lint        # eslint
npm run test        # vitest
npm run check:i18n  # i18n 目录完整性校验（CI 会跑）
```

`check:i18n` 双向校验 i18n catalog 的完整性：

- **正向**：静态扫描全部 `t('...')` 调用键，要求键同时存在于 zh 与 en 目录，且两份目录键集合一致；
  目录形状与提取正则不符（提取到 0 键）时直接失败而非静默全绿。
- **反向（死键检查）**：每个 catalog 键必须「可达」——字面 `t()` 调用、
  `titleKey/labelKey/key` 对象字面量、显式声明的动态键族（`verdict_`/`diff_`，各注明构造点）、
  或 `lc/i18n.py` 解析出的服务端驱动键，四者其一。不可达的死键（曾滞留过与产品事实矛盾的
  `setup_body` 文案）会让 CI 失败：删掉它，或把它接回真实调用点。
- 服务端键的后端侧镜像护栏在 `tests/test_i18n.py`：每个 message_key 必须在 lc/ 或 server/
  源码中被真实 raise。

`t()` 对缺键静默回退原键名，这类缺陷（曾把裸键渲染上屏）现在会在 CI 直接失败。
动态拼接的键超出静态扫描能力，由后端平价测试 + 显式声明键族补位：
`tests/test_i18n.py` 保证后端 `lc/i18n.py` 的每个 message_key 都存在于前端两个
locale 块（服务端驱动的 `i18n.t(keyFromServer)` 曾因此缺 11 个键而无人察觉）。

## 开发模式双服务

后端与前端分别启动：

```
coach            # FastAPI，127.0.0.1:8000
cd web && npm run dev   # Vite，localhost:5173，/api 代理到 8000
```

**Vite 必须 strictPort 固定 5173**（已在 vite.config.js 写死）。端口被占时 Vite 会直接报错
而不是顺延——顺延到 5174 会击穿后端 Origin 白名单。若 5173 被占请先释放端口。
后端中间件白名单包含 `http://localhost:5173`（Vite proxy 透传原始 Origin），
因此开发模式下跨端口调用不会被自家防护打断。

## 发布流程

构建可分发的包（wheel 内附带已构建前端）：

```bash
cd web && npm run dist && cd ..
python -m build
```

`npm run dist` = 构建 + 跨平台拷贝到 `server/webdist/`（取代了旧的 POSIX-only
shell 片段——拷贝步骤只写在文档里时，漏拷会发出 UI-less wheel 且无环节能发现；
CI 的 package job 会构建 wheel 并断言其中含 `server/webdist/index.html`）。

`server/webdist/` 为构建产物（已 gitignore），打包时经 package-data 进入 wheel；
运行期 dist 解析链与单实例守卫的完整机制在
[ARCHITECTURE「前端托管与单实例」](ARCHITECTURE.md) 单点维护，此处不再复制。

验收命令（模拟用户安装态）：

```bash
python -m venv /tmp/ac-check && /tmp/ac-check/Scripts/pip install .
cd /tmp && /tmp/ac-check/Scripts/coach --no-browser
curl http://127.0.0.1:8000/          # 应返回前端 index.html
curl http://127.0.0.1:8000/settings  # SPA 深链应同样返回页面
```

## 单实例守卫

`coach` 全局只允许一个实例（锁文件 + PID 存活探测 + 端口探测 + 预绑定 socket）。
机制的完整描述在 [ARCHITECTURE「前端托管与单实例」](ARCHITECTURE.md)，
日常开发只需知道：重复启动会拒绝并打印运行中实例的地址；崩溃残留锁自动接管。
