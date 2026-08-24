# DEVELOPMENT

面向开发者的环境搭建与日常流程。

## 后端

要求 Python ≥ 3.10。

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
ruff check .                   # CI 会跑，提交前先本地过一遍
pytest                         # 自带 --cov 覆盖率报告（lc/ + server/，含分支覆盖）
```

- 单元测试 HTTP 全 mock，不真连网络；默认通过 pyproject `addopts` 排除
  `integration` 标记（CI 同样不跑）。
- `pytest` 默认输出覆盖率表（pytest-cov 在 dev 依赖组）；只看某个文件的缺失行：
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

`check:i18n` 静态扫描全部 `t('...')` 调用键，要求：键必须同时存在于 zh 与 en 目录，
且两份目录键集合一致。`t()` 对缺键静默回退原键名，这类缺陷（曾把裸键渲染上屏）
现在会在 CI 直接失败。动态拼接的键（如 `` t(`verdict_${key}`) ``）不在校验范围。

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
cd web && npm run build && cd ..
rm -rf server/webdist && mkdir -p server/webdist
cp -r web/dist/. server/webdist/
python -m build
```

`server/webdist/` 为构建产物（已 gitignore），打包时经 package-data 进入 wheel；
运行期 dist 解析链：`ALGOCOACH_DIST` 环境变量 → 仓库 `web/dist` → 安装目录内
`server/webdist`，均未命中则进入 API-only 模式。

验收命令（模拟用户安装态）：

```bash
python -m venv /tmp/ac-check && /tmp/ac-check/Scripts/pip install .
cd /tmp && /tmp/ac-check/Scripts/coach --no-browser
curl http://127.0.0.1:8000/          # 应返回前端 index.html
curl http://127.0.0.1:8000/settings  # SPA 深链应同样返回页面
```

## 单实例守卫

`coach` 通过 `~/.algocoach/instance.lock`（O_CREAT|O_EXCL 原子创建，记录 PID+端口）
保证全局单实例：存活实例拒绝重复启动并打印其地址；崩溃残留锁自动接管；
首选端口被占用时先探测 `/api/status`——是 coach 则拒启，是其他程序才顺延端口。
