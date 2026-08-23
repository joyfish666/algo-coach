# DEVELOPMENT

面向开发者的环境搭建与日常流程。

## 后端

要求 Python ≥ 3.10。

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
```

- 单元测试 HTTP 全 mock，不真连网络。
- 需要真网验证的用例标记 `@pytest.mark.integration`，手动运行：
  `pytest -m integration`。

## 前端

要求 Node.js ≥ 18。

```bash
cd web
npm install
npm run dev      # http://localhost:5173
npm run build    # 产物 web/dist/
npm run test     # vitest
```

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

待 v1.x 补充（构建 wheel、附带前端产物、PyPI 发布）。
