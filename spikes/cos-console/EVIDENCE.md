# Spike evidence

What each live check ran and showed, copied from the runs. The engine tests (`claude plugin test mod`) are mocked; everything below ran against a real Claude Code (2.1.304) or the real Omnigent server.

## Mod, headless (`claude -p --plugin-dir mod --model haiku --output-format json`)

Run from a scratch directory holding `tmp/loop/cos-status.json` (written by `status_snapshot.py` from the live board) and a copy of `board.md`.

- PARKED notice → dropped by the rules, no model:
  `"num_turns":0, "total_cost_usd":0, "duration_ms":50, "result":"Prompt dropped by a hook: cos-console: absorb parked: waits on host capacity"`
- Quiet notice, last message "Test kills the no-union mutation (merge exits 1). Running gates." → small model absorbed it:
  `num_turns 0, total_cost_usd 0, duration_ms 807, result: Prompt dropped by a hook: cos-console: absorb quiet: haiku: {"route":"absorb","why":"Lead is mid-work running gates; nothing for chief to act on yet"}`
  The `$.model.complete` call's own usage is not counted in the `-p` result's `modelUsage`.
- Quiet notice, last message "I'll continue with the next step after this." → small model escalated; the main model then ran a turn (`num_turns 4`).
- `/leads` → answered by the mod, no model: `num_turns 0, duration_ms 82`, the table of 5 live leads.

## Mod, interactive, through Omnigent's delivery

`claude --plugin-dir mod` in a private tmux pane; the notice delivered as `bridge.py` `_paste_and_submit` does: `load-buffer`, `paste-buffer -p`, a pause, then `send-keys Enter`.

- On start, the status line read `cos-console: cos: STALE 400s` (the status file was 400 s old).
- Without the clear: the transcript showed `Prompt dropped by a hook: …` and the input box still held the pasted notice. Omnigent would re-send Enter (first retry 1 s, doubling to 8 s, for up to 20 s).
- With `$.clock.after(300, () => $.prompt.fill({ text: '', mode: 'replace' }))`: same drop line, empty input box 3 s later.
- `/leads` opened the pane: the stale warning, the 5 leads, and `handled: parked→absorb`.
- The clear was then made conditional (`$.prompt.read()`, clear only while the box still holds the dropped notice) and replayed twice in the same session:
  - Drop alone: the drop line, then the box empty (the next paste landed in an empty box).
  - Drop, then `send-keys -l "hello from the owner"` 100 ms after Enter: the box ended as the restored notice with `hello from the owner` appended to it, and the clear left it alone. So the conditional clear preserved the owner's text in this replay (text arriving between its read and its fill would still be erased), but the text then sits behind a notice: Omnigent's retry, or the owner's Enter, would submit both, and the mod would drop both as `parked`.
  - Result: dropping in the mod is unsafe whenever anything can reach the box during the restore. The design defaults to filtering in the supervisor (`--fyi skip`) for this reason.

## Small model from the supervisor's side

`claude -p --model haiku --tools "" --setting-sources "" --strict-mcp-config --system-prompt "You are a terse event router." --output-format json "<routing prompt>"`:
`{"route":"absorb","why":"Lead is mid-work running gates; no action needed yet."}`, usage `input 2, cache read 749, cache write 0, output 119`, cost $0.00007, API 1.56 s, wall 3.8 s.

## Omnigent server

- `GET /v1/info` → `features.canvas: false`.
- `PATCH /v1/sessions/<own session>` with `{"labels": {"cos.status": "{…}"}}` → the label came back on the session and on its row in `GET /v1/sessions?limit=50&sort_by=updated_at`. Cleared afterwards with an empty value.
- File API from host macbook-work: `GET /v1/sessions/<lead on cc-experiments>/resources/environments/default/filesystem/home/agent/dev/chief-of-staff/board.md?base=host` → `file_content`, 17,904 bytes. A directory on host kris (`…/voice_note/tmp/loop?base=host` through a lead there) → listing of 12 entries. A report not yet written → 404.

## Fork spike (`kzarzycki/omnigent` `spike/cos-status-line`, `ba5d0f533`)

`npx vitest run src/shell/Sidebar.test.tsx src/canvas src/shell/sidebarNav.test.ts` → 7 files, 235 tests passed. `tsc --noEmit -p .` exit 0; `oxlint --deny-warnings` on the changed files exit 0. Not tested: staleness in the browser (the line is shown as written).
