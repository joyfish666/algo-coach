# AlgoCoach

A local-first practice workbench for LeetCode China (leetcode.cn) with an AI learning coach.
All data — cookies, configs, submission archives — stays on your machine. No cloud dependency.

> **Status**: pre-release skeleton under active development towards v0.1.0. See the
> [ROADMAP](docs/zh/ROADMAP.md) for the delivery plan.

## Features (planned for v0.1.0)

- Guided `/setup` wizard: paste your cookie, validate it instantly, optionally configure an LLM key
- Full problem-list sync with local caching and progress feedback
- Answering workbench: rendered statement, CodeMirror 6 editor, Run / Submit with rich verdicts
  (runtime/memory percentiles, WA case diff, CE/RE details)
- Offline review: opened problems are materialized to local files you own
- Daily problem shortcut; analytics dashboard with AI weakness reports (bring your own key)
- Bilingual UI (zh/en) and a minimalist light/dark design system

## Installation

Requires Python ≥ 3.10. Node.js ≥ 18 is only needed to build the frontend from source
(release wheels will ship a pre-built frontend).

```bash
git clone https://github.com/joyfish666/algo-coach.git
cd algo-coach
pip install -e .
cd web && npm install && npm run build && cd ..
```

## Quick start

```bash
coach
```

The server binds to `127.0.0.1` only (default port `8000`, auto-incremented when occupied),
prints the final URL in a banner, and opens your browser as soon as it is ready.
First launch guides you through `/setup`.

Options: `--port`, `--no-browser`, `--debug`.

## Privacy model

Cookies, configuration and submission archives live under `~/.algocoach/` — outside any repo,
with restrictive file permissions on POSIX systems. Nothing leaves your machine except requests
to leetcode.cn itself (and to whichever LLM endpoint you configure yourself).

## Documentation

- [中文文档](docs/zh/)：USAGE · DEVELOPMENT · ARCHITECTURE · ROADMAP · PITFALLS
- English docs are planned for v1.x (see [ROADMAP](docs/zh/ROADMAP.md))

## Development Rules

All human developers and AI agents must follow these rules:

1. **Fix bugs at the root cause.** Symptom-hiding patches are forbidden; PRs must include a
   root-cause analysis.
2. **Read [docs/zh/PITFALLS.md](docs/zh/PITFALLS.md) before developing**; every newly solved
   pitfall must be recorded back into that file.
3. **Dependency policy:** only general-purpose foundational libraries are allowed — backend
   `requests` / `fastapi` / `uvicorn` / `rich`; frontend `vue` / `vite` / `pinia` /
   `vue-router` / `codemirror` plus official CodeMirror language packages (e.g.
   `@codemirror/lang-cpp`) and `markdown-it` (statement rendering, HTML escaped by default).
   Copying code from any existing LeetCode-related project is strictly forbidden — all business
   logic must be original.
4. **Documentation policy:** the README must stay synchronized in both English and Chinese;
   every change under `docs/` must be registered in the ROADMAP.

Welcome in any form of contribution — issues or PRs, no matter how small!
欢迎任何形式的贡献！无论是提出问题（issues）还是提交代码（pull requests），再小的毛病、再小的改动都欢迎。

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE)
