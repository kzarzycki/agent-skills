# Chief of staff console: one live status, fewer model rounds

## The result

- **Most chief-of-staff (CoS) tokens go to waking up for nothing.** In the current CoS session, 74 of 119 turns were started by a lead's notice, not by you. Each wake re-reads the whole transcript (about 120k tokens on average), so a notice that changes nothing still costs about $0.03 per model call, and a typical notice turn makes three calls.
- **Recommendation: move the routine work out of the Opus session, in three layers.**
  1. The supervisor (the Python process that already watches every lead) writes one status file and a one-line status label on each lead, and settles routine events with fixed rules: record a park, nudge a stall once, revive a failure once, archive a finished lead.
  2. What the rules can't settle goes to a small model (Haiku, or Luna on Codex) for one routing decision: nothing to do, the CoS must act, or only you can decide. Measured: about 870 tokens and $0.00007 per event, against about $0.08 for an Opus notice turn.
  3. The Opus CoS wakes only for real decisions, and each wake arrives with the lead's status and report already attached, so it skips the `status` call and the report read.
- **You see the same status in the web UI** as a short line under each lead in the sidebar, kept live by Omnigent's own sidebar updates. That needs a small change on the fork (about 40 lines of code); the spike is built and tested.
- **A Claude Code mod is a thin layer on top, not the brain.** It drops the notices the supervisor marks as FYI before they become a model turn (you still see them in chat), attaches the live status to your own messages, and shows a status line and a `/leads` pane in the terminal. The rules live in one place, the supervisor, so a Codex CoS gets the same behaviour without the mod.
- **Expected saving: about 25 to 50% of the CoS session's cost** (estimate, from the current session's turn log; method under Savings). The small model adds well under a cent a day.

What is proven, with spikes on branches (details under What the platforms can do):

- A mod's `prompt.submit` hook drops a notice with zero model turns, in a real interactive session fed through Omnigent's exact tmux paste.
- A mod's in-session `$.model.complete({ model: "haiku" })` call routes a notice in under a second, and a headless `claude -p --model haiku` call does the same from the supervisor.
- A supervisor can write a session label, and the sidebar list carries it.
- Omnigent's file API reads a lead's report on another host with no session started there.
- The fork change renders the label on sidebar rows, their hover cards and Canvas cards; 235 web tests pass.

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
| Stop a prompt before the model sees it | `prompt.submit` hook answering `{ drop }` | Yes: `num_turns: 0`, `total_cost_usd: 0`, 50 ms, headless; and interactive, through Omnigent's tmux paste |
| Add text the model reads beside a prompt | `prompt.submit` with `next({ ...e, context })` | Yes, in engine tests |
| Call a small model with no transcript | `$.model.complete({ model: "haiku" })`, uses the session's own login | Yes: a real quiet notice routed in 0.8 s |
| Status line, toast, pane, slash command | `$.ui.status`, `$.ui.toast`, `$.ui.open` + `ui.render`, `$.command.register` | Yes, in a real terminal session |
| Timers, files, host commands | `$.clock.every`, `$.fs.read`, `$.process.run` | `$.clock.every` and `$.fs.read` yes |
| Fail open when a hook breaks | `.catch(($, e, next) => next(e))` | Yes: a broken triage call let the notice through |

Two limits shape the design:

- **Claude puts a dropped prompt back in the input box.** Omnigent's delivery (`_paste_and_submit` in `omnigent/harnesses/claude_native/bridge.py`) re-sends Enter every second while its pasted draft is still in the box, for up to 20 s. So the mod clears the box 300 ms after a drop (`$.prompt.fill({ text: "", mode: "replace" })`). Replayed with Omnigent's exact paste in a local tmux pane: the box is empty before Omnigent's first retry. This depends on Claude Code's input behaviour, which can change, so it stays a tested assumption.
- **A mod draws only in the terminal.** The web UI chat is built from Claude's transcript file (`forward_claude_transcript_to_session`), which keeps user and assistant rows and drops system rows and meta user rows. So nothing the mod draws reaches you in the browser. The browser view has to come from Omnigent.
- The mod API is early access and "may change between releases without notice" (its own types file). Every hook here fails open.

### Omnigent's web UI

Omnigent turns a web message into a tmux paste into Claude's terminal, and marks the turn delivered once the paste is accepted (`omnigent/inner/claude_native_executor.py`, `run_turn`). Running and idle come from Claude's own `UserPromptSubmit` and `Stop` hooks. A prompt the mod drops never reaches those hooks, so the CoS session simply stays idle.

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

The supervisor is the only writer. It already polls every lead, so on each poll it writes:

- **`status.json`** (schema `cos-status/1`) next to its registry: one row per lead with id, title, host, state (`running`, `idle`, `blocked`, `failed`, `archived`), what it waits on, its last ending (`DONE`, `USER NEEDED`, `PARKED`), the first line of its last message, nudges and revives spent, and a link. A `written_at` time lets every reader tell a stale file. Written atomically (temp file, then rename).
- **A `status.line` label on each lead**: the same row in one short line, such as `waits on verifier · PR #252 · 3m`. This is what the web UI shows.
- **`events.jsonl`**: one line per event and how it was settled (rule, small model or CoS), so a wrong call can be found and the rules tuned.

The labels live on the Omnigent server, which every host reaches. So a successor CoS on any host reads every lead's state from the API, and the board's hand-written Live leads table goes away: the board keeps your standing decisions, what needs you and the owner asks, which change rarely. That also answers your doubt about git as the database: lead state moves to the server; git keeps only the slow-changing part.

### Routing an event

Each event goes through three steps, cheapest first.

| Event | Settled by | What happens |
|---|---|---|
| `archived` | Rule | Drop the row; no post |
| `PARKED` | Rule | Record what it waits on; FYI post |
| `STILL WORKING` naming its wait (worker, verifier, CI) | Rule | Record the wait; FYI post |
| Exact repeat of the last notice for that lead | Rule | Nothing |
| Quiet, first time without progress | Small model | "Mid-work" → FYI. "Stalled" → the supervisor relays the CoS skill's nudge itself and records it |
| Quiet again after a nudge | Rule | Act: to the CoS |
| Failed, first time | Rule | Revive in place, record it |
| Failed again | Rule | Act: to the CoS with the error line |
| `DONE` | Rule | Act: to the CoS with the result. The supervisor also tells each lead registered as waiting on this one |
| Report path as the last message | Rule | Read the report's first line through the file API, then treat it as its `DONE`, `BLOCKED` or `STILL WORKING` |
| `USER NEEDED` | Small model | Covered by a standing decision → act, with that decision quoted; not covered or not reversible → act, marked "for the owner" |
| Blocked on an approval prompt | Rule | For the owner: the tool call, and the lead's link. Only you approve |
| Blocked on a question | Rule | Act: the question and its options, so the CoS answers with one `relay` |

Rules for the small model:

- It only routes. It never sends, approves or decides for you, because its input includes a lead's own words, and a lead's words must not steer what gets done.
- It sees one event and the standing decisions, never a transcript.
- Unsure or unparseable means "act". A mistake costs one Opus turn, never a missed decision.
- Model by tier: small (Haiku for Claude, Luna for Codex). Never Fable or Astra.

How it is called:

- **From the supervisor**, as `claude -p --model haiku --tools "" --setting-sources "" --system-prompt …`. Measured: 870 tokens, $0.00007, 3.8 s wall time.
- **From the mod**, `$.model.complete` does the same in 0.8 s with the session's login. Recommended: the supervisor, so the decision is made once, logged once, and works for a Codex CoS too.

### What reaches the Opus CoS

The supervisor posts two kinds of line:

- `Supervisor [act]: …`: wakes the CoS. It carries the lead's status row and the first lines of its report, read through the file API on any host, so the CoS can usually answer in one model call.
- `Supervisor [fyi]: …`: posted only so you see it in chat. The mod drops it before it becomes a turn. Without the mod (a Codex CoS), the supervisor doesn't post FYI lines at all (`--fyi skip`), and you read them in the sidebar.

When you write to the CoS, the mod attaches a short block: every lead's status line and the FYI events since its last turn. So "how's it going?" needs no tool call.

### The mod

`cos-console`, enabled only in the CoS home's project settings, so leads and other sessions never load it. Open question: confirm a marketplace plugin enabled in a project's `.claude/settings.json` loads in a session Omnigent launches there.

- `prompt.submit`: drop `[fyi]` lines and clear the box; pass `[act]` lines through; attach the status digest to your messages.
- Status line: `cos: leads 5: 3 running, 2 idle` or `cos: STALE 400s` when the file is old.
- `/leads`: a pane with the full table and the last few events, for a terminal user.
- No routing logic of its own beyond the `[fyi]` marker, so the rules have one home.

The spike mod also carries a rules table and its own Haiku triage, to prove the mechanisms. The recommended build moves both into the supervisor.

### The web UI

Recommended: the fork change from the spike, `kzarzycki/omnigent` branch `spike/cos-status-line` (commit `ba5d0f533`):

- A session's `status.line` label shows as a muted second line under its sidebar title, in its hover card, and on its Canvas card.
- The label is generic: any orchestrator can set it, which makes it a reasonable upstream proposal later (draft in the report, not filed).
- Acting stays where it is: a click opens the lead's chat, where approve, reply and archive already work.

Stopgap with no Omnigent change: the supervisor also writes `status.html` into the CoS workspace, which you can open in the Files panel. It refreshes only when a CoS turn ends.

Not recommended now:

- An extension page: it needs a new server route and host service, and adds nothing the sidebar line doesn't give you.
- Canvas: it needs a server restart. Turn it on later if a board view is wanted; the spike already renders the line there.

### Options considered

| Where the routing runs | For | Against |
|---|---|---|
| A. Supervisor only | One home for the rules, tested in Python. Works for Claude and Codex. Stops the wake before any post | Without the mod or the sidebar change, you'd stop seeing routine events in chat |
| B. Mod only | Every event still lands in chat; the drop is free | Claude only. Logic in an early-access API. A second copy of rules the supervisor half-knows. The drop relies on clearing the input box in time |
| **C. Supervisor decides, mod drops FYI lines (recommended)** | Rules in one place. You still see everything, in chat and in the sidebar. A Codex CoS works without the mod | Two small pieces to keep in step, joined only by the `[fyi]`/`[act]` marker |

| Where you see the status | For | Against |
|---|---|---|
| **Sidebar line from a label (recommended)** | Always on screen next to the CoS chat. Live in about 4 s with no polling. About 40 lines of code on the fork | A fork change to carry until upstream takes it |
| Canvas cards | A whole-board view | Needs your restart. A separate page, not next to the chat |
| Extension page | Its own layout and nav entry | New server route and host service. Wheel install and restart |
| HTML in the Files panel | No change at all | Not live |

## Failure modes

| Failure | How it shows | What catches it |
|---|---|---|
| Supervisor dies | Labels and `status.json` stop changing | `written_at` turns the mod's status line to `STALE`. The supervisor also writes a heartbeat label on the CoS session, which shows in its own sidebar row. Systemd `Restart=always`. A restart re-finds terminal events from the registry, as it does today |
| A turn end is lost (Omnigent kzarzycki/omnigent#4) | A lead reads `running` for good | The quiet rule still fires on silence; unchanged from today |
| The small model absorbs something that needed action | A lead waits | Only explicit cases are absorbed by rules. The model's absorb is limited to "mid-work". A second quiet notice without progress always escalates. Every absorb is in `events.jsonl` and visible in the sidebar line |
| Cost runaway | Many triage calls or many Opus wakes | One triage call per event, at most N an hour (then "act" without a model). The supervisor counts Opus wakes an hour and posts one warning past a threshold |
| The mod breaks after a Claude Code update | A dropped line comes back, or a hook throws | Every hook fails open: the notice reaches Opus as it does today. Its engine tests (`claude plugin test`) become part of the repo's checks |
| Omnigent changes its submit retry | A dropped notice is re-sent until it times out | The tmux replay test, kept as a check. If it fails, use `--fyi skip` and rely on the sidebar |
| Labels have a size limit | A write fails | None found in source. The line is kept under 200 characters, and a failed write logs once and goes on |
| Stale or wrong line in the sidebar | You act on old state | The line ends with its age (`· 3m`) |

## Savings

These are estimates, from session `aa0cba18` (cost spread evenly per model call; per-turn usage is not in the API):

| Change | Model calls saved (of 417) | Share of session cost |
|---|---|---|
| Duplicate notices dropped | about 15 | about 4% |
| "No change" notice turns become FYI | 48 | 11.5% |
| Pre-digested `[act]` posts (no `status` call, no report read) | up to 57 | up to 14% |
| No hand-written leads table (42 rewrite-and-push turns) | about 40 to 60 | 10 to 15% |
| Overlap between the rows above | | minus a few points |

- Range: about 25% (only the sure parts) to about 50% (everything above lands).
- The small model adds about $0.00007 per routed event: well under a cent a day at today's volume.
- Fewer turns also slow the transcript's growth, which makes every later call cheaper. That effect is real but not measured here.
- The 2026-10-27 token retro already scheduled on the board is the natural before-and-after check.

## Phases

1. **Status and labels** (agent-skills). The supervisor writes `status.json`, `events.jsonl` and `status.line` labels. Nothing changes for the CoS yet. A `report <session>` subcommand reads a lead's report through the file API on any host.
2. **Routing** (agent-skills). The rules table, small-model triage, `[act]` and `[fyi]` lines, the supervisor's own nudge, revive and archive (after #249 lands), and waking waiting leads. The CoS skill changes with it: Live leads are generated, and an `[act]` line arrives digested.
3. **Sidebar line** (fork). Land the spike on `mine` and roll out to the hosts. A draft upstream proposal goes to you to file or not.
4. **Mod** (agent-skills). `cos-console`, enabled in the CoS home only: drop FYI lines, attach the digest, status line and `/leads`.
5. **Measure.** Compare a day of CoS cost and turns before and after, in the 2026-10-27 retro.

Phases 1 and 2 give most of the saving, and work for a Claude or a Codex CoS. Phase 3 is what makes the saving visible to you. Phase 4 is optional: it keeps routine events in your chat for free.

## Open questions

- Does a marketplace plugin enabled in a project's `.claude/settings.json` load in a Claude session that Omnigent launches in that project? Settle it with one launched session in phase 4.
- Do you want routine (FYI) events in the chat at all once the sidebar line exists? If not, phase 4 shrinks to the digest and the status line.
- Canvas on this server needs `OMNIGENT_FEATURES=canvas` and a restart. Is a board view worth that, or is the sidebar enough?
- Should the supervisor send the stall nudge itself (it's a fixed text in the CoS skill today), or only propose it to the CoS? The design says it sends it, because it's reversible and fixed.
