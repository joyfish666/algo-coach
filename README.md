# AlgoCoach

A local-first practice workbench for LeetCode China (leetcode.cn) with an AI learning coach.
All data — cookies, configs, submission archives — stays on your machine. No cloud dependency.

> **Status**: v0.1.0 delivered and live-verified (see the [ROADMAP](docs/zh/ROADMAP.md)).

## Features

- Guided `/setup` wizard (cookie + preferences); LLM configuration lives separately in
  Settings with a one-click connection test and a thinking-mode control
- Full problem-list sync (~4400 problems) with progress that survives page switches;
  practice-status / difficulty / tag / keyword filters, random pick, favorites, density mode
- Answering workbench: rendered statement, CodeMirror 6 editor, Run / Submit with rich
  verdicts (WA case diff, CE/RE details, percentiles), per-problem notes and custom
  testcases; reopening a problem resumes at the language you last used
- Submission history and one-click site import over the local archive; offline review of
  opened problems (materialized as local files you own)
- User-defined groups (practice plans): nestable, ordered problem lists that record
  slugs only, shareable via versioned share codes; add problems from the list, the
  workbench, or the groups page
- Daily problem shortcut; analytics dashboard with tag-mastery chart, recommendations and
  an AI weakness report; stateless AI coach sidebar on every problem (replies follow the
  interface language, opt-in editor-code attachment)
- Bilingual UI (zh/en); light/dark design system; uniform toasts and request timeouts

## Quick start

Requires Python ≥ 3.10 (Node.js ≥ 18 only to build the frontend from source):

```bash
git clone https://github.com/joyfish666/algo-coach.git
cd algo-coach && pip install -e .
cd web && npm install && npm run build && cd ..
coach
```

`coach` binds to `127.0.0.1` only (default port 8000, auto-incremented), opens your browser
when ready, and refuses a second instance. First launch guides you through `/setup`.
Options: `--port`, `--no-browser`, `--debug`.

## Privacy model

Cookies, configuration and submission archives live under `~/.algocoach/` — outside any repo,
with restrictive file permissions on POSIX systems. Nothing leaves your machine except requests
to leetcode.cn itself (and to whichever LLM endpoint you configure yourself).

## Documentation

中文文档为权威（English summary below）：

- [使用手册 USAGE](docs/zh/USAGE.md)（安装/启动/页面/报错对照）·
  [English quick guide](docs/en/USAGE.md)
- [开发环境 DEVELOPMENT](docs/zh/DEVELOPMENT.md) ·
  [系统架构 ARCHITECTURE](docs/zh/ARCHITECTURE.md)（含 REST 契约）
- [实现陷阱 PITFALLS](docs/zh/PITFALLS.md) · [ROADMAP](docs/zh/ROADMAP.md) ·
  [CHANGELOG](CHANGELOG.md)
- Contribution rules: [CONTRIBUTING.md](CONTRIBUTING.md)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) — root-cause-first bug fixes, a minimal-dependency
policy and bilingual doc sync are spelled out there. Issues and PRs of any size are welcome;
欢迎任何形式的贡献，再小的改动都欢迎。

## License

[MIT](LICENSE)
