---
name: playwright
description: "Drive a browser via Playwright MCP — navigate, fill forms, click, scrape, or run e2e tests/scripts. Two servers: `playwright` (fresh, no logins) and `user-browser` (the user's live logged-in browser via CDP)."
when_to_use: "Any browser-automation task once the Playwright MCP is enabled. Use user-browser only when the task needs existing sessions/logins. Distinct from claude-in-chrome and brave-automation."
---

# Playwright MCP

Microsoft's `@playwright/mcp` — browser automation as MCP tools. This plugin registers two servers; pick by task:

| Server | Tool prefix | Browser |
|--------|-------------|---------|
| `playwright` | `mcp__plugin_playwright_playwright__browser_*` | Fresh headed browser, temp profile. Default for general automation/scraping. |
| `user-browser` | `mcp__plugin_playwright_user-browser__browser_*` | The user's own live, logged-in browser and open tabs. Attaches over CDP to the running browser on `:9222` (currently Brave). Requires that browser running with `--remote-debugging-port=9222`. |

So switching "use case" = calling a different server's tools. The default server does NOT share the logged-in Brave/Chrome session.

## More profiles / use cases

Add named servers to this plugin's `.mcp.json` (then `/reload-plugins`). Each is its own tool namespace:
- `--user-data-dir <path>` — a persistent Chromium profile (logins survive). One dir per identity. Can't point at Brave's live profile while Brave runs (locked) — use `--cdp-endpoint` for that.
- `--isolated` (+ optional `--storage-state <file>`) — ephemeral clean room, optionally seeded with saved auth.
- `--headless` — no window, for unattended/bulk runs.
- `--config <file.json>` — move long arg sets into a preset file.

Each enabled server is one idle node process; the browser launches lazily on first tool call. Don't declare presets you won't use.

## The one rule: snapshot, don't screenshot

`browser_snapshot` returns an accessibility tree with stable element `ref`s. It's cheaper and more reliable than screenshots for deciding what to click/type. Reserve `browser_take_screenshot` for visual verification a human will look at. Most click/type tools take a `ref` from the latest snapshot.

Loop: `browser_navigate` → `browser_snapshot` → act on a `ref` → snapshot again.

## Scripting (the playwright-cli equivalent)

When the task is more than a couple of clicks — loops, extraction, conditional logic — **don't chain tool calls, write code.** Three ways, in order of preference:

1. **`browser_run_code_unsafe`** — pass an `async (page) => { ... }` function (full Playwright API), or a `filename` to load it from disk. Returns whatever you `return`. This is the direct analog of a playwright-cli script and is enabled by default (core capability). RCE-equivalent — runs in the server process — so only run code you wrote.
   ```js
   async (page) => {
     const rows = await page.locator('table tr').all();
     return Promise.all(rows.map(r => r.innerText()));
   }
   ```
2. **`browser_evaluate`** — run JS *inside the page* (DOM context, no Playwright API). Use for quick DOM reads/tweaks.
3. **Codegen → reusable script** — the server runs `--codegen typescript` by default: your tool-driven actions are recorded as a Playwright `.ts` script you can save (`--save-session` / `--output-dir`) and re-run later with `playwright-cli`. Use this when the user wants a repeatable artifact, not a one-off.

Rule of thumb: 1–2 interactions → individual tools; a flow with iteration/extraction → `browser_run_code_unsafe`; "give me a script I can rerun" → codegen.

## Tool map

| Need | Tool |
|------|------|
| Go to URL / back | `browser_navigate`, `browser_navigate_back` |
| See the page | `browser_snapshot` (default), `browser_take_screenshot` (visual only) |
| Click / type / hover / drag | `browser_click`, `browser_type`, `browser_hover`, `browser_drag` |
| Whole form at once | `browser_fill_form` |
| Dropdown / key / upload | `browser_select_option`, `browser_press_key`, `browser_file_upload` |
| Run Playwright code | `browser_run_code_unsafe` |
| Run JS in page | `browser_evaluate` |
| Wait for condition | `browser_wait_for` |
| Assertions (testing) | `browser_verify_text_visible`, `browser_verify_element_visible`, `browser_verify_value` |
| Console / network | `browser_console_messages`, `browser_network_requests` |
| Tabs | `browser_tabs` |
| Cookies / storage | `browser_cookie_*`, `browser_localstorage_*`, `browser_sessionstorage_*`, `browser_storage_state` |
| Save PDF | `browser_pdf_save` |
| Generate a selector | `browser_generate_locator` |

## Useful launch flags

Set these by editing the plugin's `.mcp.json` args, or per-task. Defaults are usually right.

- `--headless` — run without a visible window (CI / unattended).
- `--cdp-endpoint <url>` — attach to an already-running Chrome/Edge (DevTools port) to reuse a logged-in profile instead of a fresh browser.
- `--device "iPhone 15"` / `--viewport-size 1280x720` — emulation.
- `--isolated` + `--storage-state <file>` — ephemeral profile seeded from a saved auth state.
- `--caps vision,pdf,devtools` — opt into coordinate-based clicks, PDF tools, devtools. Core automation (incl. `browser_run_code_unsafe`) needs no caps flag.
- `--init-page <file.ts>` — run your own `export default async ({ page }) => {...}` setup script at startup (grant permissions, set geolocation, etc.).
- `--secrets <.env>` — inject secrets without putting them in tool calls.

## Gotchas

- Fresh browser ≠ your logged-in session. Use the `user-browser` server (or `--cdp-endpoint`) for authenticated sites.
- `ref`s go stale after navigation/DOM change — re-`browser_snapshot` before acting.
- `browser_run_code_unsafe` executes in the Node server, not the page sandbox — never feed it untrusted code.
- Inside `browser_run_code_unsafe` the scope is tight: no `require`, no global `fetch`. For node-side HTTP (e.g. hitting a CDP endpoint), use Playwright's own client: `await page.request.get(url)`. `chromium.connectOverCDP` to a browser with many tabs/extensions can hang — prefer the CDP HTTP API (`/json/list`) via `page.request`.
