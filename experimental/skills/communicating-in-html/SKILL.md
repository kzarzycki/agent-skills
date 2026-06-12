---
name: communicating-in-html
description: >
  Optional enrichment layer. When loaded, the agent communicates with the user
  in self-contained HTML instead of Markdown wherever a rendered page beats a
  chat dump — reports, interviews/intake, and option/mockup choices. Orthogonal
  and zero-coupling: other skills keep working in plain Markdown when this isn't
  loaded. Fires when you are about to deliver a report / summary / analysis /
  dashboard / scorecard, interview the user for more than ~3 fields, or offer
  options / mockups to choose from — and the content has comparison, layout,
  interaction, color/charts, or would exceed ~100 lines of Markdown. Output is
  one offline-safe .html file; forms and option pages hand answers back via a
  copy-paste token. Trigger on "report", "write it up nicely", "dashboard",
  "summarize visually", "interview me", "intake form", "gather requirements",
  "show me options", "mockups to choose from", "as HTML", "nicer than chat".
---

# Communicating in HTML

An orthogonal enrichment layer — like a writing style, not a task. When this
skill is loaded, prefer **HTML over Markdown** for outputs the user will read,
share, decide from, or fill in. It couples to nothing: it triggers on the
*activity*, so whatever else you're doing (discovery, review, planning) simply
renders in HTML when it would land harder that way. Unloaded, nothing changes.

## When HTML beats Markdown (the whole point)

**Use HTML when the content has any of:** comparison (things side by side) ·
spatial layout / timeline / flow · interaction (the user picks, fills, adjusts,
annotates) · reference material they'll return to or share · meaningful color /
diagrams / charts · a one-off editor · or it would exceed ~100 lines of Markdown.

**Stay in Markdown / plain chat when:** it's a short reply or a genuine
few-sentence answer · code-only or terminal output · a disposable summary ·
or a file that needs clean version-control diffs.

Rule of thumb: *if the user will **do** something with it, make it HTML; if
they'll read a line and move on, keep it Markdown.* HTML costs ~2-4× the tokens
— spend it where layout, sharing, or interaction earns it. Full rationale and
the carve-outs: `references/when-html.md`.

## Universal requirements (every artifact)

1. **One self-contained file** — CSS/JS inlined (`assets/design-system.css`),
   no build, no external fonts, CDN only if interactivity demands it.
2. **Works offline** — opens by double-click, no required network calls.
3. **Mobile responsive** — viewport meta, readable at 360px.
4. **Genuinely laid out** — real columns/timelines, not stacked Markdown in a `<div>`.
5. **Self-explanatory in 5 seconds** — title + one framing sentence up top.
6. **Exportable when interactive** — the user can get their data back (copy-paste-back token).
7. **Progressive disclosure** — headline first, detail on demand. Tooltips on terse labels,
   `<details>` folds for full text, click-for-source on data cells/diagram nodes. Reading
   depth is the user's choice; nothing optional bloats the first screenful. **Controls are
   exempt:** primary actions (approve/submit/choose) stay visible at all times — never fold
   the thing the user came to click. Condense controls into a bar; fold their detail.
8. **Verified before handover when interactive** — any page with JS gets a jsdom smoke run:
   load with `runScripts:'dangerously'` + a `fetch` stub, assert zero load errors, fire one
   DOM event per interactive feature and check its effect. A load-time crash kills everything
   scheduled after it while hoisted click handlers keep "working" — the page looks alive and
   is half-dead. `node --check` and HTTP 200 are not verification.

## The three activities → load the playbook when one fires

| You're about to… | Do | Playbook |
|---|---|---|
| Deliver a report / summary / analysis / dashboard / scorecard | Build a self-contained HTML report (KPI cards, tables, inline-SVG charts, callouts) | `references/reporting.md` |
| Gather >~3 pieces of structured info (intake, brief, requirements) | Build an HTML form; answers come back via copy-paste token | `references/interviewing.md` |
| Offer options / mockups / directions to choose from | Render choices to compare — native AskUserQuestion HTML previews, or a gallery | `references/offering-options.md` |

Read the relevant playbook only when that activity fires (progressive disclosure).
All three share `assets/` (design system, copy-back bridge, starter templates).
Platform gotchas (files download not render, previews don't show on Claude Code,
mobile scroll traps): `references/gotchas.md` — read before promising the user
any in-client rendering.

## Delivery + getting answers back

- Write `kebab-case.html` next to the work (or in `.work/` if it exists), then
  **surface it** (e.g. `SendUserFile` on Claude Code web/mobile) **and print the
  absolute path**.
- **Viewing.** Surfaced files arrive as a *download* on both Claude Code web and
  desktop — neither renders HTML inline. Tell the user how to view it: open the
  download (it's self-contained, renders offline via `file://`), or for zero
  friction run the session locally / `--teleport` it and `open <file>.html`.
  (AskUserQuestion HTML previews only render in SDK hosts that set
  `previewFormat: "html"` — Claude Code's clients show option text only, so use a
  gallery file for visual choices. See `references/offering-options.md`.)
- A static file can't POST back. For forms/option pages, inline `assets/copy-back.js`:
  the page serializes input into a fenced `ANSWERS<<< … >>>ANSWERS` token the user
  pastes into chat; you parse it and continue.
- **Live answer channel (no copy-paste).** When the user must *decide* on an artifact
  (approve / request rework) and you can serve HTTP, skip the paste round-trip:
  see "Live decision pages" below. The token stays as the automatic fallback.
- **Always leave a 3-5 bullet TL;DR in chat too** — the file is the artifact, the
  chat keeps the headline.
- **Fallback:** no browser / can't render → degrade to batched `AskUserQuestion`
  rounds. Offer HTML; never trap the user in it.

## Live decision pages (approve / rework without copy-paste)

Two stdlib-python assets turn any markdown artifact into a served page whose buttons reach
the agent directly. Reusable by any caller (the workflow engine's phase gates are one);
everything is deterministic — zero LLM tokens per render.

1. **Render**: `python3 assets/render-decision-page.py --artifact <md> --out <dir>/page.html
   --gate <id> [--verdicts '<json>'] [--banner '<what changed since last version>']`.
   The page gets: every H2 section annotatable (✎ → targeted comment), an always-visible
   condensed decision bar (live status · annotation count · Approve · Request rework), and
   a copy-back token fallback that fires automatically when POST fails (e.g. `file://`).
2. **Serve**: `nohup python3 assets/gate-server.py --dir <root> --port <port>
   --state _gate/state.json --answers _gate/answers >/tmp/gate-server-<name>.log 2>&1 &`
   Probe the port first (curl; taken → increment). Hand out `http://<reachable IP>:<port>/…`
   — prefer a VPN/tailnet IP from `hostname -I`; the user is often not on localhost.
3. **State file** (`_gate/state.json`): `{"state":…,"version":N,"updated":<epoch s>,"message":…}`.
   States the page understands: `idle` (listening) · `working` (page shows spinner + message —
   update the message as you progress) · `needs-console` (page tells the user to return to chat).
   Bump `version` only when the page should reload (you re-rendered it); the page polls
   `/gate/state` and auto-reloads on any bump.
4. **Watch for answers** (the agent side): arm a background watcher that exits when an answer
   file lands, which re-invokes you:
   `for i in $(seq 1 540); do f=$(ls <root>/_gate/answers/*.json 2>/dev/null|head -1); [ -n "$f" ] && { echo "ANSWER:"; cat "$f"; exit 0; }; sleep 1; done; echo EXPIRED`
   It expires (~9 min) — re-arm whenever it fires or expires while the decision is open.
5. **Process an answer**: move it to `_gate/answers/processed/`, set state `working`, act on
   `{gate, decision, feedback?, annotations?:[{target,comment}]}` (each annotation is an
   instruction targeted at that section), then re-render with `--banner` saying what changed,
   bump `version`, set `idle`, re-arm. A pasted `ANSWERS<<<…>>>ANSWERS` token is the same
   answer arriving by chat — process identically.

The page degrades gracefully at every layer: no server → token; no browser → the markdown
artifact path plus chat. Channel security is LAN/tailnet-grade (anyone who can reach the
port can POST) — don't expose it past trusted networks.

## Anti-patterns

- Building a page for a one-sentence answer (channel check first).
- Multi-file output or CDN charts when inline SVG would do — it won't travel offline.
- Pasting a giant Markdown version *and* the HTML — pick HTML, keep chat to the TL;DR.
- Forms/option pages with no copy-back token, or no `AskUserQuestion` fallback.
- Forcing HTML when the user is in a plain terminal.
