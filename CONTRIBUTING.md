# Contributing

> **English summary**: backend dev — `python -m venv .venv`, `pip install -e ".[dev]"`,
> run `ruff check .` and `pytest` (all HTTP mocked; live-network cases need
> `ALGOCOACH_TEST_COOKIE` + `pytest -m integration`); frontend dev —
> `cd web && npm install && npm run dev` (strict port 5173, backend on 8000),
> then `npm run lint && npm test`. Bug fixes require a root-cause analysis in the PR.
> Read `docs/zh/PITFALLS.md` before development and record every newly solved pitfall back.
> Use conventional commits. Contributions of any size are welcome!

欢迎任何形式的贡献！无论是提出问题（issues）还是提交代码（pull requests），即使是再小的毛病、再小的改动，我们都非常欢迎。

## 开发环境

### 后端

要求 Python ≥ 3.10。

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
ruff check .
pytest
```

单元测试全部 mock HTTP，不真连网络；真网用例标记 `integration`（默认排除），
设置 `ALGOCOACH_TEST_COOKIE` 后手动运行。提交前请确保 `ruff check .` 通过。

### 前端

要求 Node.js ≥ 18。开发模式为双服务：后端 `coach`（:8000）+ Vite（:5173，
已配置 `/api` 代理与 `strictPort`）。Vite 必须固定 5173 端口——顺延到其他端口会击穿
后端 Origin 白名单。

```bash
cd web
npm install
npm run dev
```

提交前请运行 `npm run lint` 与 `npm test`。

## 提交规范

- 使用 conventional commits：`feat:` / `fix:` / `docs:` / `refactor:` / `test:` / `chore:`
- 修复 bug 必须附根因分析，禁止打补丁掩盖症状
- 开发前必读 [docs/zh/PITFALLS.md](docs/zh/PITFALLS.md)；解决新坑必须回填该文件
- 涉及 docs/ 的改动需同步登记 [ROADMAP](docs/zh/ROADMAP.md)
- README 中英双份必须同步修改
- 新增依赖须遵守 README「开发规则」中的依赖政策
