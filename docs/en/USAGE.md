# USAGE (English quick guide)

The canonical documentation is the Chinese set under [docs/zh/](../zh/); this
page is a compact English entry point covering install, launch and the most
common errors. Deep documentation (architecture, REST contract, pitfalls) is
Chinese-only for now — full English docs are planned for v1.x (see ROADMAP).

## Install & run

Requires Python ≥ 3.10 (Node.js ≥ 18 only to build the frontend from source):

```bash
git clone https://github.com/joyfish666/algo-coach.git
cd algo-coach && pip install -e .
cd web && npm install && npm run build && cd ..
coach
```

- The server binds `127.0.0.1` only (default port 8000, auto-incremented when
  occupied), prints the final URL, and opens your browser when ready.
- A single-instance guard refuses duplicate launches and points at the
  running instance; stale locks from crashed processes are taken over.
- Options: `--port` (preferred port), `--no-browser`, `--debug` (verbose log).
- Config priority: CLI > environment (`ALGOCOACH_*`, validated at startup) >
  `~/.algocoach/config.toml`.
- All data lives under `~/.algocoach/`. Nothing leaves your machine except
  requests to leetcode.cn and the LLM endpoint you configure yourself.

First launch opens `/setup`: paste `LEETCODE_SESSION` and `csrftoken` from
your logged-in browser cookies (F12 → Application → Cookies), validate, and
pick your preferences. LLM keys are configured later in **Settings → AI (LLM)**
— API key, base URL, model and thinking mode, with a "test connection" probe
(testing never saves).

## Pages

| Route | Page | What it does |
|---|---|---|
| `/problems` | Problem list | Full sync (~4400 problems, rate-limited, a few minutes); solved/attempted/todo/favorites + difficulty/tag/keyword filters, random pick, density toggle; filters are URL-driven |
| `/problem/:qid` | Workbench | Statement, CodeMirror editor, Run/Submit, custom testcases, notes, favorite, AI coach sidebar; drag the splitters to resize (remembered) |
| `/daily` | Daily problem | Today's problem card into the workbench |
| `/history` | History | Every local archive record with expandable WA diff and CE/RE details, filterable by problem |
| `/analyze` | Analytics | Solved stats, tag mastery, recommendations, AI weakness report (generate/regenerate) |
| `/settings` | Settings | Appearance (UI language / theme / debug), default coding language, AI (LLM) card, cookie status, data erase (type `DELETE` to confirm) |

Shortcuts: `Ctrl+Enter` run, `Ctrl+Shift+Enter` submit, `Esc` closes the AI
panel. Code and notes autosave ~1–2 s after you stop typing and flush on
leave; transient failures only surface as toasts and never tear down the page.

## Common errors

| Message | Meaning & fix |
|---|---|
| 403 / cookie expired | Your session was rotated (re-login invalidates it); paste the newest values |
| "Open the problem and select this language" | That language's template is not on disk yet and you are offline; go online, open the problem, switch language |
| Rate limited (429) | Backoff is automatic; slow down or raise the request interval |
| "Unknown result, verify on the website" | Submit polling timed out but the submission entered the site history; it is archived with its submission_id |
| "Debug service unavailable" | leetcode.cn's interpret endpoint hiccups occasionally; retry later |
| "Request timeout" / "Cannot reach the local server" | The backend did not answer in time (or is not running); check the `coach` process |
| HTTP 500 | Enable debug mode in Settings (or `?debug` in the URL), copy the frontend log, and run `coach --debug` for the backend traceback |

## Where to go deeper

- Architecture and the full REST contract: [docs/zh/ARCHITECTURE.md](../zh/ARCHITECTURE.md)
- Development commands and release packaging: [docs/zh/DEVELOPMENT.md](../zh/DEVELOPMENT.md)
- Known implementation pitfalls: [docs/zh/PITFALLS.md](../zh/PITFALLS.md)
- Contribution rules (root-cause-first, minimal dependencies): [CONTRIBUTING.md](../../CONTRIBUTING.md)
