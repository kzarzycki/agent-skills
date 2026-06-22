---
name: operating-omnigent
description: Use when diagnosing or operating a local Omnigent install — "did omnigent crash?", can't open it / new tab shows {"detail":"Not Found"}, web UI blank, restarting the server, listing/attaching/resuming/disposing sessions, or making sense of the many omnigent processes (runners, terminals). Also when spawning, delegating to, or monitoring other agents/sessions from inside a turn via the sys_* MCP tools. Saves a fresh agent from port-scanning and source-diving to relearn the topology.
---

# Operating Omnigent

Omnigent runs as **one server (control plane) + N runners (one per open session)** on the user's machine. Most "is it broken?" questions are answered by hitting the server's `/health` and `/v1/sessions` — not by killing processes or reading source. Use the HTTP API and the `omnigent` CLI; reach for `kill` only as a last resort (auto-mode blocks raw kills, and killing a runner orphans it rather than disposing the session).

## Topology (what's running and why)

| Piece | Process / how to find | Notes |
|---|---|---|
| **Server** (API + web UI) | `omnigent.cli server`, binds `127.0.0.1:6767` | FastAPI/uvicorn. DB = `~/.omnigent/chat.db`, artifacts = `~/.omnigent/artifacts`. One per machine. |
| **Runner** (one per session) | `omnigent.runner._entry`, ~1 PID per open chat | Idle-reaps after **1h** (`runner.idle_timeout_s`, default 3600s). Each also spawns its own `tmux` + `claude`/`codex` terminal — that's why `ps | grep omnigent` looks crowded. |
| **Logs** | server: `~/.omnigent/logs/server/local-server-*.log`; runner: `~/.omnigent/logs/host-runner/runner-<id>.log`; cli: `~/.omnigent/logs/cli-*.log` | Log *files* accumulate one-per-session-ever — they are NOT live processes. Count `omnigent.runner._entry` PIDs for the real number. |

Probe with `python3` urllib or the `omnigent` CLI — **`curl` is often not on PATH** in non-login shells here.

## Diagnose "can't open omnigent" / `{"detail":"Not Found"}`

```python
import urllib.request, json
g = lambda p: urllib.request.urlopen("http://127.0.0.1:6767"+p, timeout=5)
print(g("/health").read())          # {"status":"ok"}  -> server is ALIVE
g("/docs"); g("/openapi.json")      # API up
```

- **`/health` ok but `/` returns `{"detail":"Not Found"}`** → server is fine; the **web SPA isn't mounted**. The SPA is mounted **once at startup** (`omnigent/server/app.py`, `_WEB_UI_DIST = .../server/static/web-ui`) only if `web-ui/index.html` exists *at boot*. If the server booted **before** the frontend was built (common with editable/dev installs that rebuild the UI later), `/` 404s for every fresh page load until restart. An already-open tab keeps working over its websocket; only **new** tabs fetch `/` and break.
  - **Verify:** server start time (`ps -o lstart -p <pid>`) vs `web-ui/index.html` mtime. UI built after boot ⇒ this is it.
  - **Fix:** restart the server (see below). It re-evaluates the mount.
- **`/health` unreachable** → server is actually down. `omnigent server start`.

## Sessions via the API

```python
s = json.load(g("/v1/sessions"))            # {object, data:[...], has_more, first_id, last_id}
# each item: id (conv_...), agent_name, status (running|idle|failed), title,
#            runner_id, workspace, external_session_id, archived
json.load(g("/v1/sessions/conv_xxx"))       # full detail: items, todos, llm_model, parent_session_id, ...
```

Map a **runner PID → session**: find its log via `lsof -p <pid> | grep host-runner`, then `grep -oE 'conv_[0-9a-f]{32}' <log>` and cross-ref `/v1/sessions`.

## Spawn & drive agents (MCP `sys_*`, from inside a turn)

Available when an Omnigent turn advertises the `sys_*` tools. This is the runtime delegation path — launch an **already-registered** agent and drive it; no files. (Authoring a *new* agent type is a separate skill, `build-omnigent`: write a `config.yaml` dir, then launch with `config_path=` below.)

| Step | Tool | Notes |
|---|---|---|
| Find agents | `sys_agent_list` | returns `agent_id`s. Builtins: `claude-native-ui` (full Claude Code coding harness), `codex-native-ui`, `polly` (delegating orchestrator), `debby` (Claude+GPT brainstorm). |
| Spawn | `sys_session_create(agent_id, message?, title?)` | runs **async**, returns `conversation_id`. **Children only** — no top-level/sibling sessions. `config_path=` instead of `agent_id` uploads + launches a fresh agent from a local YAML/dir/.tar.gz. |
| Drive / delegate more | `sys_session_send(session_id, args)` | posts a turn to a child; **blocks until that turn completes and returns its output**. Parallel fan-out: emit several `sys_session_send` calls in one response. |
| Monitor | `sys_session_get_info(session_id)` | poll `status`: `running` → `idle` = turn done; `failed` = dead. Metadata only. |
| Collect | `sys_session_get_history(conversation_id, tail_items)` | transcript tail (≤50). Global read — any session you can access, not just your children. |
| Non-blocking fan-out | `sys_call_async` + `sys_read_inbox` | dispatch background work; completions auto-deliver to the inbox. |

Minimal loop: `create(agent_id, message=task)` → poll `get_info` until `status != running` → `get_history` for the result. For a single delegated turn, `sys_session_send` already blocks-to-completion, so no separate poll loop is needed.

**Don't hand-roll multi-agent coding.** `polly` already plans a goal → delegates to Claude/Codex/Pi sub-agents in parallel worktrees → routes each diff to a different-vendor reviewer. Launch it: `sys_session_create(agent_id=<polly>, message=<goal>)`.

## Commands & endpoints (no exploration needed)

| Action | How |
|---|---|
| Restart server | `omnigent stop && omnigent server start` (`server status` to check). **Drops every websocket — all live tabs/sessions reconnect; mid-turn work is interrupted.** Sessions persist (sqlite). |
| Attach to a LIVE session | `omnigent attach conv_xxx` — joins & streams I/O, starts nothing. Interactive REPL → run in a real terminal (or `!`-prefix), not headless. |
| Reopen a stored session | `omnigent resume conv_xxx` (claude-native lands in `omnigent claude`). |
| **Dispose** a chat (hard) | `DELETE /v1/sessions/conv_xxx` → tears down tasks/terminals/files/conv row. **Irreversible.** Owner-level. Does **NOT** kill the runner process — it orphans it (reaps on idle timeout). |
| Archive (reversible) | `PATCH /v1/sessions/conv_xxx` body `{"archived": true}` — hides it, keeps transcript. |

## Gotchas

- **Editable/dev install:** `omnigent` may be an editable install from a clone (e.g. `/Users/zarz/dev/ext/omnigent`). `omnigent` is a **namespace package** — `omnigent.__file__` is `None`; resolve source with `list(omnigent.__path__)` or `importlib.util.find_spec("omnigent.cli").origin`. Don't delete/move the clone or switch its branch — it breaks the running install.
- **You may be running INSIDE omnigent.** If `OMNIGENT_RUNNER_ID` is set, this session IS an omnigent runner — restarting the server kills your own session. Prefer telling the user to restart from a normal terminal.
- **`DELETE` ≠ kill.** Deleting a session removes it from the DB/UI but leaves the runner OS process running (orphaned); it self-reaps within the idle timeout (~1h). To stop it *now*, the user must approve a `kill <pid>` (auto-mode blocks the agent from killing processes it only identified from internal output).
- **`sys_session_close` (MCP) is narrow.** It only tombstones `sys_session_send`-style *named* sub-agents in your spawn tree — returns `session_out_of_tree` for independent top-level chats and `session_not_a_sub_agent` for sessions you made with `sys_session_create`. Don't rely on it for cleanup: spawned runners idle-reap in ~1h anyway, or use HTTP `DELETE`/`PATCH` to dispose/archive now.
- **CLI path fallback:** if `omnigent` isn't on PATH, the uv-tool interpreter runs everything: `~/.local/share/uv/tools/omnigent/bin/python3 -m omnigent.cli ...`.
- **Don't trust stale counts.** "~50 sessions" in notes usually means 50 *log files*, not live runners. Always recount live `omnigent.runner._entry` PIDs.
