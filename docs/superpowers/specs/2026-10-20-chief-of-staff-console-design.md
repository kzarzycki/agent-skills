# Chief of staff console: one live status, fewer model rounds

## The result

- **Most chief-of-staff (CoS) tokens go to waking up for nothing.** In the current CoS session, 74 of 119 turns were started by a lead's notice, not by you. Each wake re-reads the whole transcript (about 120k tokens on average), so a notice that changes nothing still costs about $0.03 per model call, and a typical notice turn makes three calls.
- **Recommendation: move the routine work out of the Opus session, in three layers.**
  1. The supervisor (the Python process that already watches every lead) writes one state file and a one-line status label on each lead, and settles routine events with fixed rules: record a park, nudge a stall once, revive a failure once, archive a finished lead.
  2. What the rules can't settle goes to a small model (Haiku, or Luna on Codex) for one routing decision: nothing to do, the CoS must act, or only you can decide. Measured: about 870 tokens and $0.00007 per event, against about $0.08 for an Opus notice turn.
  3. The Opus CoS wakes only for real decisions, and each wake arrives with the lead's status and report already attached, so it skips the `status` call and the report read.
- **You see the same status in the web UI** as a short line under each lead in the sidebar, kept live by Omnigent's own sidebar updates. That needs a small change on the fork (about 40 lines of code); the spike is built and tested; it still needs the browser-side stale mark.
- **Routine events are filtered in the supervisor, not in the chat.** The supervisor simply doesn't post them (`--fyi skip`), so nothing has to be dropped from the CoS's input box. You see them in the sidebar line instead.
- **A Claude Code mod is optional, a convenience, not the brain.** It attaches the live status to your own messages and shows a status line and a `/leads` pane in the terminal. The spike shows a mod can also drop a notice before it becomes a turn, but that is unsafe through Omnigent's delivery (see Two limits), so the recommended mod drops nothing.
- **Expected saving: about 20 to 40% of the CoS session's cost; 25% is the target, not a floor** (estimate from the current session's turn log; method and assumptions under Savings). The small model adds well under a cent a day.

What the spikes show (commands and outputs in `spikes/cos-console/EVIDENCE.md` on branch `explore/cos-mod`; the engine tests there are mocked, the rest ran live):

- Live: a mod's `prompt.submit` hook drops a notice with zero model turns, headless and in an interactive session fed through Omnigent's tmux paste. The same replay shows why the build should not rely on it.
- Live: a mod's `$.model.complete({ model: "haiku" })` routes a notice in under a second; a headless `claude -p --model haiku` call does the same from the supervisor for $0.00007.
- Live: a supervisor can write a session label, and the session list carries it.
- Live: Omnigent's file API reads a file on another host with no session started there.
- Fork tests: the change renders the label on sidebar rows, their hover cards and Canvas cards; 235 web tests pass. It does not yet age the line in the browser (see The web UI).

## What happens today

The CoS skill (`engineering/skills/chief-of-staff/SKILL.md`) runs one lead per ask, each a top-level Omnigent session. The supervisor (`omnigent_agent.py supervise --registry <file> --notify <CoS session>`, issue #239) posts `Supervisor: <line>` into the CoS chat when a lead ends a turn with `DONE`, `USER NEEDED` or `PARKED`, goes quiet for 300 s, blocks on a prompt, fails or is archived. Every post is a full Opus turn.

What one routine event costs today:

1. The notice wakes the CoS, which re-reads its transcript.
2. It runs `status <session>` or reads the lead's report file. A report on another host needs a session started on that host.
3. It rewrites `board.md` (the whole state, in kzarzycki/chief-of-staff) and commits and pushes it.
4. It replies one line, often "no change".

Other extra rounds the CoS pays today:

- A lead's question (`AskUserQuestion`) has to be read from a prompt notice, then answered with `relay`.
- Registry lines are edited by hand before `reap`, so the supervisor doesn't post `archived` back (#249, in flight with lead `e03b9a41`).
- Lead state lives in a hand-written table in a git file, so every state change is a rewrite and a push.

Measured in the current CoS session `aa0cba18` (Omnigent API, read-only; per-turn token counts are not in the API, so cost is spread by model-call count):

| | Turns | Model calls | Share of cost |
|---|---|---|---|
| Your messages | 40 | 190 | 46% |
| Lead notices (subscription and supervisor) | 74 | 219 | 53% |
| ...of which "no change" or no tools | 27 | 48 | 11.5% |
| ...of which 3 tool calls or fewer | 66 | 167 | 40% |

Session total: $10.70 over 10.8 h, 417 model calls, 49.8M cache-read tokens. Of the 39 supervisor notices, 25 were `turn ended, quiet <n>s` and 6 repeated the previous notice for the same lead word for word. Across the 73 notice turns: 42 board rewrites with a push, 38 `status` calls, 19 report reads. The full analysis and the commands to re-run it are in `spikes/cos-console/research/research-cos-tokens.md` on branch `explore/cos-mod`; the Omnigent source survey behind the next section is `research-omnigent-ui.md` beside it.

## What the platforms can do

### Claude Code mods

A mod is a Claude Code plugin with a TypeScript hooks module. What matters here:

| Capability | API | Proven |
|---|---|---|
| Stop a prompt before the model sees it | `prompt.submit` hook answering `{ drop }` | Live: `num_turns: 0`, `total_cost_usd: 0`, 50 ms, headless; and interactive, through Omnigent's tmux paste |
| Add text the model reads beside a prompt | `prompt.submit` with `next({ ...e, context })` | Engine tests only (mocked) |
| Call a small model with no transcript | `$.model.complete({ model: "haiku" })`, uses the session's own login | Live: a real quiet notice routed in 0.8 s |
| Status line, toast, pane, slash command | `$.ui.status`, `$.ui.toast`, `$.ui.open` + `ui.render`, `$.command.register` | Live, in a terminal session |
| Timers, files, host commands | `$.clock.every`, `$.fs.read`, `$.process.run` | `$.clock.every` and `$.fs.read`, live |
| Fail open when a hook breaks | `.catch(($, e, next) => next(e))` | Declared and validated; no retained test of a broken hook |

Two limits shape the design:

- **Claude puts a dropped prompt back in the input box, and that makes dropping unsafe through Omnigent.** Omnigent's delivery (`_paste_and_submit` in `omnigent/harnesses/claude_native/bridge.py`) re-sends Enter while its pasted draft is still in the box: first after 1 s, then doubling up to 8 s, for up to 20 s. The spike clears the box 300 ms after a drop, and only while it still holds the dropped notice (`$.prompt.read()`, then `$.prompt.fill`). Replayed with Omnigent's paste in a local tmux pane, a lone drop clears in time. But text typed 100 ms after the Enter was appended to the restored notice: the clear rightly left it, and the next Enter would submit both, and the mod would drop both. Omnigent also doesn't wait for the mod's timer before releasing its next message. So the build doesn't drop in the mod at all.
- **A mod draws only in the terminal.** The web UI chat is built from Claude's transcript file (`forward_claude_transcript_to_session`), which keeps user and assistant rows and drops system rows and meta user rows. So nothing the mod draws reaches you in the browser. The browser view has to come from Omnigent.
- The mod API is early access and "may change between releases without notice" (its own types file). Every hook here fails open.

### Omnigent's web UI

Omnigent turns a web message into a tmux paste into Claude's terminal, and marks the turn delivered once the paste is accepted (`omnigent/inner/claude_native_executor.py`, `run_turn`). Running and idle come from Claude's own `UserPromptSubmit` and `Stop` hooks.

| Extension point | Today | Fits a live status view? |
|---|---|---|
| Session labels (`PATCH /v1/sessions/{id}` `labels`) | Exists. Proven: a `cos.status` label written to this session shows in `GET /v1/sessions`. The sidebar re-reads rows every 4 s over a websocket and compares labels by value. Labels are upsert-only: an empty value clears one. | As the transport, yes. Nothing renders a custom label yet. |
| Sidebar row and hover card | Fixed fields: title, state badge, location, branch | Needs a fork change; the spike adds a `status.line` label as a second row line |
| Canvas page (`/canvas`): a board of session cards | Exists behind `OMNIGENT_FEATURES=canvas`; off on this server (`GET /v1/info`), and turning it on needs a server restart | Needs the same small change, plus your restart |
| Extensions (sidebar page in a sandboxed iframe) | Exists, but the iframe has no network and its sessions API gives no labels, host or last message | Needs a server route and a new host service: larger fork change |
| HTML file in the Files panel | Exists, but it refreshes only when the session's turn ends | Usable as a stopgap; fewer CoS turns means fewer refreshes |
| MCP apps, agent-posted canvases | Not supported (upstream #8389 open; #1789/#1791 stale) | No |
| Scheduled tasks | Every firing is a model turn, hourly at most | No |
| File API (`.../resources/environments/default/filesystem/<path>?base=host`) | Exists. Proven: read a file on host cc-experiments and listed a lead's `tmp/loop/` on host kris, from macbook-work | Removes the "start a session there" round for reports |

## Design

### One status, two renderings

The supervisor is the only writer. It already polls every lead, so on each poll it writes three things, all next to its registry:

- **`state.json`** (schema `cos-state/1`, versioned): what a successor needs to carry on, and the source for everything else. Written atomically (temp file, then rename), with a `written_at` time.
  - Per lead: id, title, host, report path, the leads it waits on, state (`running`, `idle`, `blocked`, `failed`, `archived`), what it waits on, last ending (`DONE`, `USER NEEDED`, `PARKED`), the first line of its last message, `progress_at` (see Routing), nudges and revives spent.
  - The ids of events already settled, so a restart doesn't settle one twice.
  - Each automatic action as an intent written before it runs and marked done after (see Actions).
  - The attention queue: events waiting for the CoS or for you, and each post to the CoS as pending or delivered (see Cost bounds).
  - The rate windows: the time of the next allowed CoS post and the small-model calls spent this hour, so a restart or a successor doesn't start a fresh allowance.
- **Two labels on each lead**: `status.line`, the row in one short line such as `waits on verifier · PR #252`, which the web UI shows; and `status.at`, the time the supervisor last observed that lead, as Unix seconds. The browser computes the age from `status.at` with its own clock, so a dead supervisor shows as stale (see The web UI).
- **`events.jsonl`**: one line per event and how it was settled (rule, small model or CoS), so a wrong call can be found and the rules tuned.

A successor CoS on any host reads the predecessor's `state.json` and registry through Omnigent's file API (proven: it reads a file on another host with no session there). Until a takeover has been done that way, the board's Live leads table stays, and the CoS skill keeps writing it; once one has, the table is dropped and the board keeps only your standing decisions, what needs you and the owner asks, which change rarely. The existing handover rule stays: stop the old supervisor before starting the new one. Labels are display only; they are never read back as state.

### Routing an event

Each event goes through three steps, cheapest first.

| Event | Settled by | What happens |
|---|---|---|
| `archived` | Rule | Drop the row; no post |
| `PARKED` | Rule | Record what it waits on; no post |
| `STILL WORKING` naming its wait (worker, verifier, CI) | Rule | Record the wait; no post |
| Exact repeat of the last notice for that lead | Rule | Nothing, unless the lead's progress deadline has passed |
| Quiet, first time without progress | Small model | "Mid-work" → recorded, no post. "Stalled" → the supervisor relays the CoS skill's nudge itself and records it |
| Progress deadline passed (see below) | Rule | By wait state: unknown or mid-work → nudge once, then act if the next deadline passes too; a named wait (verifier, CI, worker) → act, for the CoS to inspect, no nudge; parked → no deadline |
| Quiet again after a nudge | Rule | Act: to the CoS |
| Failed, first time | Rule | Revive in place, record it |
| Failed again | Rule | Act: to the CoS with the error line |
| `DONE` | Rule | Act: to the CoS with the result. The supervisor also tells each lead registered as waiting on this one |
| Report path as the last message | Rule | Read the report's first line through the file API, then treat it as its `DONE`, `BLOCKED` or `STILL WORKING` |
| `USER NEEDED` | Small model | Covered by a standing decision → act, with that decision quoted; not covered or not reversible → act, marked "for the owner", and queued for you (see Cost bounds) |
| Blocked on an approval prompt | Rule | For the owner: the tool call and the lead's link, queued for you. Only you approve |
| Blocked on a question | Rule | Act: the question and its options, so the CoS answers with one `relay` |

Rules for the small model:

- It only routes. It never sends, approves or decides for you, because its input includes a lead's own words, and a lead's words must not steer what gets done.
- It sees one event and the standing decisions, never a transcript.
- Unsure, unparseable or timed out means "act". A wrong "act" costs one Opus turn. A wrong "mid-work" costs at most the deadline chain below: about 35 minutes before the CoS hears of it.
- Limits per call: 20 s timeout, the event cut to 4,000 characters, 200 output tokens. Past the limit, the event is routed "act".
- Model by tier: small (Haiku for Claude, Luna for Codex). Never Fable or Astra.

How it is called:

- **From the supervisor**, as `claude -p --model haiku --tools "" --setting-sources "" --strict-mcp-config --system-prompt …`. Measured: 870 tokens, $0.00007, 3.8 s wall time.
- **From the mod**, `$.model.complete` does the same in 0.8 s with the session's login. Recommended: the supervisor, so the decision is made once, logged once, and works for a Codex CoS too.

A lead's progress is `progress_at`: the latest of its last message changing and its children's activity (as today's quiet check counts `og.active`, so a lead whose verifier is working is progressing). It lives in `state.json`, so absorbing an event, or restarting the supervisor, doesn't reset it. Today's `follow` gives no event for a lead that reads running for good, or for a second quiet spell with the same ending (shown by a probe in the review); the deadline is what covers both.

The deadline, by the lead's wait state:

- **Parked**: none. A parked lead waits on host capacity, and the CoS skill already says it is not stalled and is resumed only after the CoS checks capacity, one lead at a time. The supervisor never resumes it.
- **Named wait** (verifier, CI, a worker, another lead): 20 minutes with no progress, counting the child's activity. Then act: the CoS inspects the wait. No nudge, since "carry on" doesn't help a lead that is waiting.
- **Unknown or mid-work**: 20 minutes with no progress, then the nudge (if not spent), then 10 more minutes, then act.

Each deadline is one event, identified by the lead and its `progress_at` value (and `nudged` for the second), raised once and settled once, so a poll after it has passed doesn't raise it again. New progress starts a new chain. Worst case from the last progress to the CoS hearing of it: 20 + 10 minutes, plus up to 5 minutes for the posting window, about 35 minutes.

### Actions

The supervisor's own actions are a nudge, a revive, an archive (after #249 lands) and telling a waiting lead. Each is fixed text, reversible, and one-shot per lead. Each runs as:

1. Write an intent to `state.json` (lead, action, event id) and count it against the lead's budget.
2. Send it.
3. Mark the intent done.

On restart, an intent not marked done is checked against the lead's history: if the text is there, it is marked done; if not, it is escalated to the CoS rather than sent again. So a crash can lose one action, which the CoS then sees, but never spends a budget twice.

A post to the CoS is the one action that is resent rather than escalated, because it may carry an owner event, which must not be lost:

1. Write the post to `state.json` as pending, with a batch id, and its events still in the queue.
2. Send it, with the id in its first line (`Supervisor [act] b-<id>: …`).
3. On success, mark it delivered and take its events off the queue.

On restart, a pending post is looked up in the CoS session's history by its id: found → delivered; not found → sent again. A duplicate is possible only if the history can't be read; then the post is sent again anyway, and the CoS skill says a post whose batch id it has already handled gets no reply.

### Cost bounds

- Small model: at most 30 calls an hour. Past that, events are routed "act" without a model. The count is written to `state.json` before each call.
- Opus wakes: at most one post to the CoS every 5 minutes. Events that arrive in between wait in the attention queue in `state.json` and go out as one combined post when the window opens. The next allowed post time is written to `state.json` before each post, so a restart or a takeover keeps the window. That bounds the CoS to 12 supervisor wakes an hour, whatever happens to the leads. It bounds wakes, not what the CoS does inside a turn.
- Owner events (approval prompts, `USER NEEDED` not covered by a decision) also wait in that queue, so a limit never drops them. The CoS's own `status.line` label shows how many are waiting (`needs you: 2`), so you see them in the sidebar even before the post goes out.

### What reaches the Opus CoS

The supervisor posts only what needs the CoS or you, marked `[act]` or `[owner]`. Each post carries the lead's status row and the first lines of its report, read through the file API on any host, so the CoS can usually answer in one model call. Routine events are not posted (`--fyi skip`, the default); they show in the sidebar line and in `events.jsonl`.

`--fyi post` keeps today's behaviour of posting every event, for when the supervisor's rules are being tuned. Each such post is an Opus turn, as today.

When you write to the CoS, the mod (if enabled) attaches a short block: every lead's status line and the events handled since its last turn. So "how's it going?" needs no tool call. A Codex CoS gets the same by reading `state.json`.

### The mod

`cos-console`, enabled only in the CoS home's project settings, so leads and other sessions never load it. Open question: confirm a marketplace plugin enabled in a project's `.claude/settings.json` loads in a session Omnigent launches there.

- `prompt.submit`: attach the status digest to your messages. It drops nothing.
- Status line: `cos: leads 5: 3 running, 2 idle` or `cos: STALE 400s` when the file is old.
- `/leads`: a pane with the full table and the last few events, for a terminal user.
- No routing logic, so the rules have one home.

The spike mod also carries a rules table, its own Haiku triage and the drop, to prove the mechanisms. The recommended build moves routing into the supervisor and leaves the drop out. Since you use the web UI, the mod's status line and pane are mostly for terminal users; its digest is the part that saves a round for you.

### The web UI

Recommended: the fork change from the spike, `kzarzycki/omnigent` branch `spike/cos-status-line` (commit `ba5d0f533`):

- A session's `status.line` label shows as a muted second line under its sidebar title, in its hover card, and on its Canvas card.
- Still to build: read `status.at`, show the age (`· 3m`) from the browser's own clock, ticking every 30 s, and mark the line stale past 10 minutes. The spike shows the line as written, so a line from a dead supervisor would look current. The story includes a test that the line turns stale with no further updates from the server.
- The label is generic: any orchestrator can set it, which makes it a reasonable upstream proposal later (draft in the report, not filed).
- Acting stays where it is: a click opens the lead's chat, where approve, reply and archive already work.

Stopgap with no Omnigent change: the supervisor also writes `status.html` into the CoS workspace, which you can open in the Files panel. It refreshes only when a CoS turn ends.

Not recommended now:

- An extension page: it needs a new server route and host service, and adds nothing the sidebar line doesn't give you.
- Canvas: it needs a server restart. Turn it on later if a board view is wanted; the spike already renders the line there.

### Options considered

| Where the routing runs | For | Against |
|---|---|---|
| **A. Supervisor only, no FYI posts (recommended)** | One home for the rules, tested in Python. Works for Claude and Codex. Stops the wake before any post. Nothing is dropped from the CoS's input | Routine events leave the chat; you see them in the sidebar line, so the fork change matters more |
| B. Mod only | Every event still lands in chat; the drop is free | Claude only. Logic in an early-access API. The drop can swallow your own text typed while the box is restored (replayed) |
| C. Supervisor decides, mod drops FYI lines | Rules in one place; you still see routine events in chat | Same drop hazard as B, plus two pieces kept in step by a marker |

| Where you see the status | For | Against |
|---|---|---|
| **Sidebar line from a label (recommended)** | Always on screen next to the CoS chat. Live in about 4 s with no polling. About 40 lines of code on the fork | A fork change to carry until upstream takes it |
| Canvas cards | A whole-board view | Needs your restart. A separate page, not next to the chat |
| Extension page | Its own layout and nav entry | New server route and host service. Wheel install and restart |
| HTML in the Files panel | No change at all | Not live |

## Failure modes

| Failure | How it shows | What catches it |
|---|---|---|
| Supervisor dies | Labels and `state.json` stop changing | The browser ages each line from `status.at` with its own clock and marks it stale past 10 minutes; the mod's status line reads `STALE` from `written_at`. Systemd `Restart=always`. A restart loads `state.json`: settled event ids, spent budgets, open intents, pending posts, the attention queue and the rate windows survive |
| A turn end is lost (kzarzycki/omnigent#4) | A lead reads `running` for good | The progress deadline fires on no progress, running or not. Today's quiet rule doesn't cover this |
| The small model absorbs something that needed action | A lead waits | Only explicit cases are absorbed by rules; the model's absorb is limited to "mid-work"; the deadline chain escalates it within about 35 minutes; every absorb is in `events.jsonl` |
| Crash between sending an action and recording it | A nudge or revive might be lost or sent twice; a post to the CoS might be lost or duplicated | Intent before, done after; an open lead action is checked against the lead's history and escalated rather than re-sent; a pending post is checked against the CoS history by batch id and re-sent if not found |
| The deadline resumes a lead that should wait | A parked lead restarts on an overloaded host | Parked leads have no deadline; named waits escalate to the CoS without a nudge |
| Cost runaway | Many triage calls or many Opus wakes | At most 30 small-model calls an hour; at most one CoS post per 5 minutes, the rest combined; owner events queued, never dropped |
| The mod breaks after a Claude Code update | A hook throws | It only adds a digest, and every hook fails open, so your message reaches Opus as it would without it |
| Labels have a size limit | A write fails | None found in source. The line is kept under 200 characters, and a failed write logs once and goes on |

## Savings

These are estimates, from session `aa0cba18` (cost spread evenly per model call; per-turn usage is not in the API):

Model calls are a proxy: one turn counts as its tool calls plus one, because per-turn token counts are not in the API.

| Change | Model calls saved (of 417) | Share of session cost |
|---|---|---|
| Duplicate notices not posted | about 15 | about 4% |
| "No change" notice turns not posted | 48 | 11.5% |
| Pre-digested `[act]` posts (no `status` call, no report read) | up to 57 | up to 14% |
| No hand-written leads table (42 rewrite-and-push turns) | about 40 to 60 | 10 to 15% |
| Sum, before overlap | at most 180 | at most 43% |

- The rows overlap (a "no change" turn often also rewrote the board), and the overlap was not computed per turn, so the honest range is about 20 to 40%. 25% is the target to check against, not a proven lower bound. The token research beside the spike gives 10 to 40% for the routing part alone, which agrees.
- 35 of the 74 notice turns came from Omnigent's own subscription notices, not the supervisor. They count toward the saving only once the CoS stops subscribing and relies on the supervisor alone, which the CoS skill's Taking over already asks for.
- The small model adds about $0.00007 per routed event: well under a cent a day at today's volume.
- Fewer turns also slow the transcript's growth, which makes every later call cheaper. That effect is real but not measured here.
- The 2026-10-27 token retro already scheduled on the board is the natural before-and-after check.

## Phases

1. **State and labels** (agent-skills). The supervisor writes `state.json`, `events.jsonl`, and the `status.line` and `status.at` labels, and tracks `progress_at` with the progress deadline. Nothing changes for the CoS yet. A `report <session>` subcommand reads a lead's report through the file API on any host.
2. **Routing** (agent-skills). The rules table, small-model triage, `[act]` and `[owner]` posts with `--fyi skip` as the default, the supervisor's own actions with intents, the cost bounds and the attention queue. The CoS skill changes with it: a takeover reads `state.json` through the file API, and an `[act]` post arrives digested. Live leads goes once a takeover has worked that way.
3. **Sidebar line** (fork). Land the spike on `mine` with the browser-side age and stale mark, and roll out to the hosts. A draft upstream proposal goes to you to file or not.
4. **Mod** (agent-skills, optional). `cos-console`, enabled in the CoS home only: the digest on your messages, the status line and `/leads`. No drop.
5. **Measure.** Compare a day of CoS cost and turns before and after, in the 2026-10-27 retro.

Phases 1 and 2 give the saving, and work for a Claude or a Codex CoS. Phase 3 is what lets you see routine events once they leave the chat, so it should land with phase 2.

## Open questions

- Does a marketplace plugin enabled in a project's `.claude/settings.json` load in a Claude session that Omnigent launches in that project? Settle it with one launched session in phase 4.
- The design takes routine events out of the chat (`--fyi skip`). If you want them in the chat, they cost an Opus turn each, as today, because dropping them in the mod is unsafe (see Two limits).
- Are the defaults right: a 20-minute progress deadline and 10 more after a nudge, 30 small-model calls an hour, one CoS post per 5 minutes? They are guesses from one session's volume, and phase 5 is where they get checked.
- Canvas on this server needs `OMNIGENT_FEATURES=canvas` and a restart. Is a board view worth that, or is the sidebar enough?
- Should the supervisor send the stall nudge itself (it's a fixed text in the CoS skill today), or only propose it to the CoS? The design says it sends it, because it's reversible and fixed.
