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
| `/groups` | Groups | Custom practice plans: nestable (10-level cap), ordered groups that record slugs only; collapsible nodes (state remembered); mark key problems (bold + accent, bookmark toggle); per-group or whole-tree share codes (`algocoach-groups:v1:…`) to copy out / paste in, marks included; unresolved slugs (not yet synced) show as "Unknown" and resolve after a sync; add problems from list-row hover buttons or the workbench title row |
| `/problem/:qid` | Workbench | Statement, CodeMirror editor, Run/Submit, custom testcases, notes, favorite, AI coach sidebar; drag the splitters to resize (remembered) |
| `/daily` | Daily problem | Today's problem card into the workbench |
| `/history` | History | Every local archive record with expandable WA diff and CE/RE details, filterable by problem |
| `/analyze` | Analytics | Solved stats, tag mastery, recommendations, AI weakness report (generate/regenerate) |
| `/settings` | Settings | Appearance (UI language / theme / debug), default coding language, AI (LLM) card, cookie status, data erase (type `DELETE` to confirm) |

Shortcuts: `Ctrl+Enter` run, `Ctrl+Shift+Enter` submit, `Esc` closes the AI
panel. Code and notes autosave ~1–2 s after you stop typing and flush on
leave; transient failures only surface as toasts and never tear down the page.

## Group share code

A share code is the plain-text form of a group tree — names, item order and
key-problem marks — shaped `algocoach-groups:v1:…`. Paste it under
Groups → "Import share code" to recreate the plan as new top-level groups;
export via each group's share button or the header "Export all". Groups
record slugs only, so importing never copies problem data.

The repository ships an official share code for the 代码随想录 practice plan:
12 sections, 173 problems, ordered exactly after the
[leetcode-master](https://github.com/youngyangyang04/leetcode-master) study
guide. The 148 problems the guide's articles introduce are marked as key
problems; the extra related problems nested inside articles are not marked.

<details>
<summary>Click to reveal the share code (~2.5 KB)</summary>

```text
algocoach-groups:v1:eNrtWV9vFDcQ_y73jB-q9omvUvHg2_Xtmuzai-3N5UBIRSA1rWhRQYiqlVqqSi2qWopKHxCo9MskIfkW_c14d893uVxCKIKgKFLubI_t-fOb8czctZHPSlXL0cWPLowKZ9vGjy5-em1kZK1GF0c7L35-9fDGwXd39m4-3f3n_ujCyFdtQSSXLoyyUle5UybdsHf_yasXtxK60Vgb6WbCK-mykhauuLCFz01Z6Vw0yk1UFoS_0kqnMO1UbTeVUJWqlQnzibxtKp3JoLyYOFsLb11QuZDOyRmomOaqclZ5jMYy2_CNzJTwwWlTiMzWTTw_XuSFnQh56BBtdN3ibH0VO9sxz-NLjbWJa3UQ2gQrxtJvqOCTDVNtcjulLfE-uqfRTlailpjYElovT9G4bI3wpRZXS2VELsVMG3G5jcMqs5PRopIxqqXbUPkqtR7S22kFPcT4pesXBvMe3Hu5_9Oj1LzdvZU2YAwfPvQ8kIJy5XVh0lVmdVM5r5Zm_VQ2wljsgJZFI7Xzc7FMKHkt2l6ZnMTqNsImdFwWtDU0HaY2PdpDlRmpP2Uxm2WVYuGO1vBZlywx2-697d1nt5csFx1QGlk4SYZn7-_HxOEEqBayqoY5Yl-KAeK8Ds-qwV1WSiczYvcIvhli6xejl5SyaWbCtPVYOQxpOQLzE3xEEieNh7KMDeTRH8-X15lzWdzTcf9m3KUm-ePBq99_2Xn216IzRfwMKl6c6M7v5qbW5StNEkoAwORqi7nHYALEBWGzrHVQTKaWNjnVKEnhYYhfAGmAEsx693jfeE21e-f23u3PD-5u7z29vyJavbXX5UilrFLA6mjxtuPCiR1mha7OmnAJIvYebu88-_rg2x93tx-kiNB1EwUUV1rVKtF6sqgPZGPiZljmqW6ZSf08iYHxIZLyKgnsHDjzy4AJNif4gpoGJSnsbzErem01FvKQboIk-ZlRndOVXYpRyy16uSn02EZsQIEKzJjkaVpj0Q9P1sTAO89v7975Yu_hNyuSz-AU7nMKOFUOI0kcyIp8OSWwPqyn0Gb9egXRKnEKmojdlMzpooQhNJxkU6spVolUFopdhc5g9SZbQAIPPI4VjrqVdIWC35BJOMIqmZXdvZbuamzTVjALjGHUVui4aWx0zmEH-fDrUUdBtQE_YYl5P6trBbRk_URnf5GrBvECYi_SH1qeS5-kuEdszmwLIFHgrhQwyaJzisbxvZJ4efKlLQtQkaEkUg_sDfy3Y16jhBugLlnx3UodrTYJ-AdbDNnV2IaACMgrvJktQirFBV1m0X-NqsusgUu12YL2Yhzt0Slx8Gosr9k8eAftXoXzXt1LRlBAEsfoZJ41w4VJfBQWapV-J4cTigcrV3vzybG3VQuqXE8masgIxvxUsAprRpVZfUxlp4TzLs0jq5JaYk20KMgJKBeP1sYThrkiPIIkVwwu03EoO7aB8fqoLbAQu0aagIhg1xPjWKIpHKVGHeqOLx3fdVD8f4LAB-Pmb-TY5855tpwzLVW-_2Hv-Z-vHj9YKlUgLJ1LqZHn44Zh9xhwEqyo9hEpbdRKU1qj5nXq0u6V5zEckVXngBxB3wVNq306TxqHptAhyBFUfMz_qAqLrbDuWzzH4NBcZRA5Zpi0RqlbxpvQ86vbMEiWDvuqce4M4MEg73EzTm9wiDLxutxutLBEBSWvC3bnanwNNSaw3P_7t91_bx6GpfTc98qs3dDMxlQXRaVS5pJ41PcWKa6SBwdNgRQe0844mnmFygEqQbXBLF9u60YUxEHyPS7xkbFfyWE2ep-ckOE2kHcWgyYK6amC6YqKDPfM2MaIHRLOjmaPKeiCWAQlWiIjjmeiVJS_JnEu2r-71E59lID6FHhDKhtvJWOhFnIVOkTc_6DkF3GUbdOjAJn3WPFUjM0pEdizgeCmzWDyXBeacZG-CRl04uTaSu_cSu-PldJY_-Wjvc9u7P96a3f7bupUEz2G1OhrJKGm0hRZuDyPDWPICYPSM3hoqTUaahrSlXTYF1xBFVDOGCxvzCkOP1yLegBUUJvGmNQFvEp66g-QBqZsgXhBoIqyp8GiZ-AMLbPMatOZtC9jluLm5iJVDGjJT0MMYiQ-gwilbT2Vq-Oor3TYNZIXZ_Tx6D4p_o8nOhHV5gmIphoJIty4QkPEnJQ-UAtaRk-ZdAmU4YI_Ae1iKOgJ4GV4KVqo7mjaPmxUyhQx6U67sn0kmZ_ISdviES3Otnj8qH9n2LYrYpH2S7ty9PrAVVh-CbtUzgIxEVETJIfcmufmE5GoHL_e0X4ZjxqeaFQaQyvZJ2wvE_RcrAm651587sXnXnw2vDh9lL-6v__kJn4fSF_kXOoKD7mqmZs2Ipebm30h1zWhhT5ygT3KdYmGk_CKKRGw-8X-K7IaiEKJGRZLyGX5x8k1Mebd8rVQtr7cf_x8oTIAfGOw6n5Ca13GAI9RhdgZMjTt0XvJ16ewpznuOv39Bw1nulI=
```

</details>

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
