# Omnigent web UI extension points for a live "leads status" view

Source: /Users/zarz/dev/ext/omnigent/omnigent, branch `mine` (upstream/main
tip e1cc4a0, 2026-10-08, is an ancestor of the extension work cited below).
Upstream state read with `gh` on 2026-10-20. Nothing was changed, filed or
commented upstream; no server was restarted. The local server is not on
`http://localhost:6767` (config `server:` is the tailnet https URL), so no live
probe was made; "exists today" below means "in the source tree of `mine`".

Legend: EXISTS = usable now with no Omnigent source change. FORK = needs a
change on `mine`. UPSTREAM = needs an omnigent-ai/omnigent PR.

## Short answer

- A real browser extension framework exists (pages + sidebar nav entry, sandboxed
  iframe, versioned SDK). It cannot show supervisor data today: the iframe has
  no network and the host exposes only sessions/projects/storage/navigation/theme.
- Omnigent already has a native Canvas page (`/canvas`, feature `canvas`) that is
  a live board of session cards (state badge, title, workspace, branch, PR link).
  It is the closest thing to the "dashboard" and is the cheapest base to extend.
- Session `labels` are a free key/value store the supervisor can PATCH, and the
  web app receives them live (4 s server rescan over a websocket). Nothing renders
  arbitrary labels yet, but they are the right transport for per-lead status.
- Approve / relay / archive are all plain REST calls the supervisor can already
  make. The web UI has no action surface for custom content; actions from a
  custom view need a fork change (or the owner clicks through to the session).

## 1. Plugin system

Two different things are called "plugin"; only one is Omnigent's.

1a. Omnigent extensions (EXISTS, UI-capable, see section 9 for the data gap).
- Entry-point group `omnigent.extensions`: `omnigent/extensions/registry.py:30`.
- Manifest types: `omnigent/extensions/api.py:20-27` (permissions
  `navigation`, `projects.read/write`, `sessions.read`, `storage.user`),
  `:45-62` PageContribution / PrimaryNavigationContribution, `:65-76` manifest.
- Contributes: pages at `/extensions/{extension_id}/{route}` and a sidebar link
  between Inbox and Usage. `docs/extending/extensions.md:24-27`.
  Not supported: React components, FastAPI routers, runner tools, marketplace
  (`docs/extending/extensions.md:31-35`). Commands/activation events are
  reserved metadata only.
- Server wiring: `omnigent/server/app.py:3146-3156` (`GET /v1/extensions`,
  diagnostics), asset delivery `omnigent/server/routes/extension_assets.py:37-83`
  (content-addressed JS/CSS, `default-src 'none'; sandbox`).
- Web wiring: route `web/src/App.tsx:201`, host iframe
  `web/src/extensions/ExtensionViewHost.tsx:301-307`, RPC host
  `web/src/extensions/rpc/host.ts` (CSP `connect-src 'none'` at `:86`).
- Install = Python wheel with an entry point into the server env, restart server
  (`docs/extending/extensions.md:39-47`). Reference: `examples/extensions/hello-page/`.
  The SDK `@omnigent/extension-sdk` (`sdks/web-extension`) is a private workspace
  package, so bundles are built inside the fork's pnpm workspace
  (`docs/extending/browser_extensions.md:11-13`).
- History: manifest registry #5608 (merged), catalog #5609 (merged), canvas
  extension #6396 (merged, then removed by #6753 in favour of a native page;
  "the extension framework itself stays"). Open follow-ups: #10904 / PR #10912
  (team packs, explicit backend activation), #9545 (session review panel, below),
  #729 (pluggable UI framework, open feature request).
- Fit: page + nav entry yes; live status no (data gap); actions no. Class: EXISTS
  as a mechanism, FORK for data.

1b. `$.tool.register` plugins (eval-kernel, self-compact) are NOT Omnigent.
They are Claude Code plugins loaded through `CLAUDE_CODE_PLUGIN_DIRS` in
`~/.claude/settings.json:12` (oh-my-claude repo). `git grep` for `tool.register`,
`eval-kernel`, `self-compact` in the Omnigent tree returns nothing. They add MCP
tools to a Claude session and cannot add Omnigent web UI.

Other Omnigent plugin seams are unrelated to UI: harness plugins
(`omnigent/harness_plugins.py:50`, group `omnigent.community.harness`).

## 2. Artifacts / canvas / HTML rendering in chat

- No agent-posted artifact channel exists. There is no `set_canvas`-style tool;
  the proposal is open and stale: issue #1789 "Canvas: agent-authored artifact
  panel" and PR #1791 (open, last update 2026-08-06) would add a `canvases` table,
  `PUT /v1/canvas/{conversation_id}` and a `set_canvas` tool with a Workspace-rail
  tab. Class for that route: UPSTREAM (or a fork cherry-pick of #1791).
- What exists is workspace-file preview: an `.html` file in a session's workspace
  opens in the Files panel as a sandboxed iframe.
  - Renderer `web/src/shell/CodeViewer.tsx:844` -> `HtmlCommentViewer`
    (`web/src/shell/HtmlCommentViewer.tsx:75-90`, `srcDoc` per content change).
  - Sandbox `web/src/shell/codeViewerHelpers.ts:381`:
    `allow-scripts allow-popups allow-popups-to-escape-sandbox allow-forms allow-modals`,
    no `allow-same-origin`. No CSP is injected, so page JS runs but has an opaque
    origin (no cookies, no authenticated calls to the Omnigent API; a call to a
    third-party URL would need that URL to send CORS headers and pass mixed-content
    rules. Untested; do not rely on it).
- Refresh: weak. `web/src/hooks/useFileContent.ts:185-196` refetches once when the
  focused session goes running -> idle, otherwise `staleTime: 5_000` with the app
  default `refetchOnWindowFocus: false` (`web/src/main.tsx:51`). So a status.html
  in the chief-of-staff workspace refreshes at the end of each chief turn or on
  reopening the file, not on a timer. A `refetchInterval` for this query is a
  one-line FORK change.
- Chat itself renders markdown (incl. mermaid, `web/src/components/ai-elements/`)
  but not HTML or live blocks; a posted message is a snapshot.
- Fit: EXISTS as a static "report file" the chief rewrites. Live refresh needs
  the chief turn to end, or the one-line fork change. No actions inside it
  (opaque-origin iframe cannot call the API); links open in a new tab.

## 3. MCP apps (`ui://`)

- Not supported. `git grep 'ui://'` over `omnigent web/src` returns nothing. Issue
  #8389 "Support MCP Apps for interactive tool UIs in chat" is open (P2, triaged
  2026-09-28) and states the gaps: UI metadata dropped when converting tools,
  results flattened to strings, MCP proxy lacks resource reads, chat has no MCP
  Apps host. No open PR found (`gh pr list --search "MCP Apps"` returned nothing
  relevant).
- Class: UPSTREAM (large: server + runner + web). Not a near-term route.
- Fit if it existed: an MCP app would render in a tool-result card and could call
  tools back (actions), but it refreshes only when re-invoked.

## 4. Side panels / dashboards / "pinned dashboard"

- "Pinned" in Omnigent is a per-viewer sidebar pin: label `omnigent.pinned.<user>`
  (PATCH with a pin-only body needs only READ access,
  `omnigent/server/routes/sessions/routes_core.py:2186-2260`; web
  `web/src/shell/sidebarNav.ts:285-321`, Cmd/Ctrl+digit hotkeys). It pins a session
  row, it does not pin content. The owner's "pinned dashboard" is therefore a
  pinned session, not a panel.
- Canvas page (EXISTS behind a flag): `/canvas`, `web/src/pages/CanvasPage.tsx`,
  cards `web/src/canvas/SessionCard.tsx` (state badge "Needs response / Running /
  New messages / Failed / Idle", title, workspace, branch, open PR), route gated by
  `FeatureGatedPage feature="canvas"` (`web/src/App.tsx:175-177`), server flag
  `omnigent/server/feature_flags.py:25` via `OMNIGENT_FEATURES=canvas` (read once at
  app build, so enabling needs a server restart). Sessions come from the shared
  `useConversations` cache with live websocket updates; PR links come from the
  GitHub panel lookup (`web/src/canvas/pullRequests.ts`, refresh 5 min, 4
  concurrent); layout is localStorage only. Introduced #6753; follow-ups #7424 /
  #7431 (split chat panel, drafts).
  - Draft #10916 (stack #10913-#10916, open, "not ready to land") adds
    session-to-session "links" drawn as Canvas arrows. Related to supervisor/lead
    topology but links are an approval/permission feature, not status.
- Session header panels (Files, GitHub, terminal): fixed set. Issue #9545 "Optional
  session review panel for local review services" (open, P2) proposes an operator-
  configured URL framed in a session panel with `?session=<id>`; the service owns
  its own page and auth, loopback only. This is exactly "show my own live page in
  the UI". No PR found. Class: UPSTREAM (or FORK: it is a small web + config
  change).
- Fit: Canvas is the best existing base: already per-session live state, a view
  over all sessions, links to open each one. Missing: host, "waits on", last
  message line, any supervisor-supplied field. Class: FORK (small).

## 5. Comments (`list_comments` / `update_comment`)

- Per-session review comments anchored to a workspace file path and character range
  (`omnigent/server/routes/comments.py:50-80`: `path`, `start_index`, `end_index`,
  `anchor_content`, `body`). Tools in `omnigent/runner/tool_dispatch.py:385,4269`.
  `POST .../comments/send` formats them into a message to the agent.
- Direction is human -> agent, tied to file text. Not a status channel and not a
  list of sessions. Class: EXISTS, wrong shape. Fit: none.

## 6. Scheduled tasks (`sys_scheduled_task_*`)

- Each firing creates a real session and dispatches a stored prompt to an agent
  (`omnigent/server/scheduled/fire.py:167-171` builds the user-message event,
  `:1174` and `:1254` dispatch it). There is no script-only / no-model mode.
  Minimum RRULE gap is 1 hour (`docs/AUTOMATIONS.md`, sub-hour gaps rejected).
- So a scheduled task cannot drive a cheap status refresh: it burns a model turn
  and cannot run more often than hourly. Class: EXISTS, unsuitable.
- Related, not usable for this: #10499 (open) asks for run-with-input from an
  external event; #4413 (open) a cheap scripted precondition before an agentic run.
- Use instead: a plain local process (launchd/cron/the supervisor itself) doing
  REST calls. It needs no Omnigent scheduling at all.

## 7. Server HTTP routes, static pages, inbound events

- No generic custom-route or static-page hook. Extensions explicitly cannot add
  FastAPI routers (`docs/extending/extensions.md:33-35`). The server mounts the
  built SPA with history fallback (`omnigent/server/app.py:4015-4036`,
  `_SPAStaticFiles`); extension assets are the only third-party files served
  (`extension_assets.py:37`).
- No generic inbound webhook. The `routes_hooks.py` POSTs
  (`omnigent/server/routes/sessions/routes_hooks.py:156,618,...`) are internal
  harness callbacks, hidden from the API docs. GitHub App docs say Omnigent does
  not consume webhooks (`docs/GITHUB_APP_SETUP.md:85-91`).
- Routes a supervisor can already call (all `/v1`, owner token):
  - `GET /sessions` (limit<=1000, `include_archived`, `visibility`, `search_query`,
    `sort_by=updated_at`), `routes_core.py:1305-1330`; `GET /sessions/{id}`
    `:1184-1200`; `GET /sessions/{id}/items` (`routes_items.py:61,119`) for the
    last message.
  - `POST /sessions/{id}/events` (send a user message, or an approval event),
    `routes_events.py:659`.
  - `POST /sessions/{id}/elicitations/{eid}/resolve` (approve/deny a pending
    prompt), `routes_elicitations.py:74`; `GET .../elicitations/{eid}` `:143`.
  - `PATCH /sessions/{id}` (title, labels, `archived`, owner-only for archive),
    `routes_core.py:2186,2243-2260`.
  - `GET /sessions/{id}/stream` (SSE) `routes_events.py:2701`; websocket
    `/sessions/updates` `routes_core.py:1735`.
  - PR links: `POST/GET /sessions/{id}/resources/github...`
    (`routes_resources.py:2861-2950`), or the supervisor's own `gh` data.
- Class: reads and actions EXISTS; custom served page / new data endpoint is FORK
  (a small router plus feature-gate) or UPSTREAM.

## 8. Session metadata / labels the UI shows

- `PATCH /v1/sessions/{id}` with `labels` upserts and merges keys; `title` is also
  writable (`omnigent/server/schemas.py:2251-2275` request model;
  `routes_core.py:2386,2849-2850` `set_labels`). `sys_session_rename` (MCP tool)
  also sets the title. Reserved prefixes are rejected
  (`_reject_server_reserved_label_seed`, `routes_core.py:2272`); anything else is
  free-form. I found no length or charset cap on label values in `omnigent/`
  (`git grep` for label limits was empty); treat as unverified.
- Live delivery: the sidebar websocket re-reads watched rows every 4 s
  (`omnigent/server/routes/_sessions/common.py:649`, `_SESSION_UPDATES_RESCAN_INTERVAL_S`)
  and diffs the whole `SessionListItem` dump, labels included
  (`web/src/hooks/SessionUpdatesProvider.tsx:151-153`). So a label write reaches
  open browsers within ~4 s, with no polling code on our side.
- What the UI renders today: sidebar row = title (or optimistic/wrapper name,
  `web/src/shell/sidebarNav.ts:186-199`), agent icon, state badge (running /
  needs-response / unread / failed), pin, project folder (`omni_project` label or
  `project_id`). Other labels are carried but not displayed.
- Trick that needs no change: the supervisor rewrites each lead's title with a
  status prefix. Works today, but pollutes real titles and fights the
  auto-title feature (`/auto-title`, `routes_core.py:2095`). Not recommended.
- Fit: transport for per-lead status = EXISTS. Rendering of a label line in the
  sidebar row or Canvas card = FORK (about 10-20 lines in `SessionCard.tsx` /
  Sidebar row).

## 9. Anything else

- Extension host data gap (detail). Sessions RPC returns only
  id, title, status (`idle|running|waiting|failed`), `unread`, `titleProvisional`,
  workspace, `gitBranch`, `projectId`, timestamps, and only top-level
  non-archived sessions (`sdks/web-extension/src/sessions.ts`;
  `docs/extending/browser_extensions.md:56-71`). No labels, host, last message,
  PRs-by-supervisor, archived rows, or actions. `storage.user` is browser
  IndexedDB (32 KB/value), never reaches the server or the supervisor
  (`browser_extensions.md:84-89`). Adding any of it is a FORK change to
  `web/src/extensions/rpc`, `services/`, `sdks/web-extension` plus a server route.
- Docs: no `designs/` doc on extensions beyond `docs/extending/*`;
  `designs/PROJECTS_PRD.md`, `designs/harness-modular-registry-proposal.md` mention
  extensions in passing. `feature-map/` has no dashboard/extension entry.
- Upstream issues/PRs worth tracking: #8389 (MCP Apps), #1789 / #1791 (agent-authored
  canvas panel), #9545 (session review panel URL), #729 (pluggable UI), #10904 /
  #10912 (team extension packs), #10916 (session links on Canvas, draft), #7431
  (Canvas split chat, draft). #6615 (host-provided extension frames) is closed.
- Fork baseline: `mine` is upstream plus about 40 commits (sync automation, MCP
  approvals, pi/omp fixes); nothing in it touches extensions, Canvas or labels, so
  upstream changes in these areas merge cleanly through the existing sync.

## Auth model for a local supervisor

- `omnigent login` stores per-server records in `~/.omnigent/auth_tokens.json`
  keyed by server URL: `{token, user_id, expires_at, refresh_token}`
  (`omnigent/cli_auth.py:1-24, 302`). On this machine both
  `https://cc-experiments.taile39822.ts.net:6767` and `https://omnigent.zarz.net`
  have such a record (keys only inspected; no secret read).
- The access token is a short-lived session JWT (about 1 hour;
  `REFRESH_MIN_REMAINING_SECONDS=90`, `cli_auth.py:41`). `refresh_stored_token`
  (`cli_auth.py:433`) renews it under a file lock, so a supervisor should call
  `load_token(server, min_remaining_seconds=90)` then `refresh_stored_token` on
  expiry, or reuse `open_server_client(server_url, bearer_token=...)`
  (`cli_auth.py:775`), which also adds routing headers. Requests send
  `Authorization: Bearer <token>` (`cli_auth.py:719`).
- Writing as the owner is enough for every action above; archive and filing into a
  project are owner-only (`routes_core.py:2243-2260`).
- For an unattended supervisor, a dedicated machine identity is cleaner:
  `grant_type=client_credentials` on `POST /oauth/token`
  (`designs/CLIENT_CREDENTIALS.md`, `omnigent/server/routes/client_credentials.py`).
  It is opt-in, default-off, only in `oidc`/`accounts` auth modes, and issues a
  path-scoped delegated token for a fixed machine principal. It would need server
  config plus the principal being granted access to the leads, so it is a larger
  setup than reusing the owner's stored token; and a machine principal would not
  own the sessions, so archive (owner-only) would fail. Prefer the owner token.

## Ranked recommendation

1. Canvas + labels (FORK, smallest; recommended).
   - Supervisor writes per-lead status into labels on each lead session with
     `PATCH /v1/sessions/{id}` (for example `cos.status`, `cos.waits_on`,
     `cos.last`, `cos.host`, `cos.prs`; one JSON-valued label also works). The web
     app receives them live (4 s) with no new endpoint.
   - Fork change: in `web/src/canvas/SessionCard.tsx` render those labels as one or
     two extra lines under the existing title/branch/PR rows, and add a card
     colour from `cos.status`. About 20-40 lines plus a test. Archived leads: add
     `include_archived` to the Canvas list if archived rows must show (verify what
     `useConversations` returns). Needs `OMNIGENT_FEATURES=canvas` on the server
     (restart, owner's call).
   - Gets: always-current view, links to each session (card opens the session),
     state badge, PR link, no model cost. Actions: the card opens the lead's chat,
     where the existing approve / reply / archive UI already works. In-card
     actions are a further FORK step (call the same REST routes from the card).
2. Extension page with a new host data service (FORK, larger; framework exists).
   - Supervisor writes a JSON status file; add a small server route (for example
     `GET /v1/cos/status`, auth like `/v1/extensions`) and a new `status.read` host
     permission and RPC in `web/src/extensions/services` + `sdks/web-extension`;
     ship the page as an installed extension (own sidebar entry, own layout, can
     call `navigation.openSession`). Best if the view should live outside the
     product's Canvas or be rebased independently. Cost: touches server, web,
     SDK and needs wheel install plus server restart. Actions would need more host
     RPCs (`sessions.approve`, `sessions.archive`).
3. HTML status file in the chief's workspace (EXISTS now; refresh is the gap).
   - The chief of staff (or the supervisor, writing into its workspace) maintains
     `status.html`; the owner keeps it open in the Files panel preview. Zero
     Omnigent change, usable today. It refreshes only when a chief turn ends
     (`useFileContent.ts:185`), so pair it with a one-line fork change
     (`refetchInterval` on the `file-content` query for html) or make the
     supervisor end a turn on each change. Links open in new tabs; no in-page
     actions.

Not worth pursuing now: MCP Apps (#8389, large upstream work, no PR), scheduled
tasks (model turn per fire, hourly floor), comments (wrong shape), client-
credentials machine auth (owner token is simpler and keeps archive working),
agent-authored canvas (#1789/#1791, stale, would need a rebase to land).

Smallest fork change that gives a live status panel: render supervisor-written
session labels on the existing Canvas session cards (route 1). Open point to
settle before building: confirm label value length limits (none found in
source) and whether the running server already has `canvas` in
`OMNIGENT_FEATURES` (`GET /v1/info` `features`, needs the owner's token).
