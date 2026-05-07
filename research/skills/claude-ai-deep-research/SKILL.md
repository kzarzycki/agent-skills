---
name: claude-ai-deep-research
description: >
  Platform knowledge for Claude.ai Research at claude.ai. Standalone: spawns
  browser-researcher agent. Or loaded by browser-researcher at runtime via skill_path.
  Trigger on "claude.ai research", "use claude research", "run this on claude.ai",
  "delegate to claude ai", "ask claude.ai to research". Does NOT trigger on generic
  "deep research".
context: fork
model: opus
---

## Standalone Invocation

If invoked directly via /claude-ai-deep-research, spawn the browser-researcher agent:
```
Agent(
  subagent_type="browser-researcher",
  name="claude-ai-researcher",
  prompt="skill_path: <skill-path>/SKILL.md\nresearch_prompt: <from user>\noutput_path: <from user or .work/claude-ai-report.md>\ncaller: <your name>",
  run_in_background=true
)
```
Then relay messages between user and agent via SendMessage. If loaded by browser-researcher via Read, ignore this section.

## Platform Configuration

- backend: playwright-cli  (default — headless via persistent profile)
- url: https://claude.ai/new
- submit_method: click_send_button  (IMPORTANT: Enter = newline on claude.ai)
- plan_review: informational  (research auto-starts, plan shown for transparency)
- hard_timeout: 65  (session hard cap — shorter than other platforms)
- completion_signal: button Copy

## Playwright-CLI Backend (default)

All browser interaction is encapsulated in a stateful Python driver. The
agent calls it via `Bash`; no Chrome MCP tools are loaded. The driver keeps
a named playwright-cli session (`claude-ai-research`) backed by a
persistent Chromium profile at `~/.cache/playwright-claude-ai-profile`, so
one-time headed SSO login unlocks every subsequent headless run.

Driver path: `scripts/pw-driver.py` (next to this file).

Exit codes: `0` ok · `10` login required · `20` timeout · `30` extraction failure · `40` DOM mismatch.

### Phase → subcommand mapping

| Phase                   | Command                                                                         |
|-------------------------|---------------------------------------------------------------------------------|
| Login check             | `python3 {skill_dir}/scripts/pw-driver.py status`                               |
| One-time headed login   | `python3 {skill_dir}/scripts/pw-driver.py login` (user runs in their terminal)  |
| Submit + Research mode  | `python3 {skill_dir}/scripts/pw-driver.py start-research --prompt-file=<path>`  |
| Plan capture            | `python3 {skill_dir}/scripts/pw-driver.py wait-plan --timeout=120`              |
| Completion polling      | `python3 {skill_dir}/scripts/pw-driver.py wait-complete --timeout=3900`         |
| Report extraction       | `python3 {skill_dir}/scripts/pw-driver.py extract --output=<path>`              |
| Shutdown                | `python3 {skill_dir}/scripts/pw-driver.py close`                                |

### Agent workflow

1. **Prepare prompt file**: strip newlines → single paragraph. Write the cleaned
   prompt to a temp file (e.g. `.work/claude-ai-prompt.txt`). The driver expects
   a file path, not inline text, to avoid shell-escaping pitfalls on long prompts.
2. **Login check**: run `status`. Exit 0 = logged in, proceed. Exit 10 = send
   `LOGIN_REQUIRED` to caller with instructions: ask the user to run
   `python3 ~/.claude/skills/claude-ai-deep-research/scripts/pw-driver.py login`
   in their terminal and reply `LOGIN_DONE` when finished. Re-run `status`.
3. **Start research**: run `start-research --prompt-file=<path>`. This opens
   claude.ai/new, activates Research mode, dismisses connectors dialog,
   types the prompt, clicks Send message. Leaves the session open.
   On exit 40 (DOM mismatch): send `ERROR:` — claude.ai UI likely changed.
4. **Plan capture**: run `wait-plan --timeout=120`. stdout = plan text. Send
   `PLAN_READY: <plan>` to caller. Since plan review is informational, also
   send `RESEARCH_STARTED` immediately and continue to step 5 unless the
   caller sends `REVISE:` within 30 seconds. (Stop/restart protocol is not
   yet wired into the driver — if a revise is needed in this pass, send
   `ERROR:` and let the caller restart the whole flow.)
5. **Wait for completion**: run `wait-complete --timeout=3900`. The driver
   streams `RESEARCH_PROGRESS: Nm elapsed` lines to stdout every ~5 min;
   relay each line to the caller as a `RESEARCH_PROGRESS:` SendMessage.
   When the driver prints `RESEARCH_COMPLETE: Nm elapsed`, the report is
   ready. Exit 20 = hard timeout — send `ERROR:` to caller.

   **Important**: use a single long-running Bash call with a generous
   timeout (3960s) for this step. Don't poll in a loop from the agent —
   the driver does the polling internally.
6. **Extract report**: run `extract --output=<caller_output_path>`. Exit 0 +
   stdout showing size in bytes → success. Exit 30 → send `ERROR:
   Extraction failed` to caller.
7. **Verify**: `wc -c <output_path>` — confirm >1000 bytes.
8. **Send `RESEARCH_COMPLETE: Report saved to <path> (<size> bytes, <lines> lines)`**.
9. **Close** the session only when the caller signals `DONE` or `EXIT`.
   Leaving the session open allows follow-up queries to reuse the tab.

### Failure modes

- **Exit 10 (login required)** — trigger the headed-login protocol above.
- **Exit 40 (DOM mismatch)** — an aria-named element was not found. claude.ai
  likely changed its UI. Send `ERROR:` with stderr so the user can update
  the driver's JS helpers.
- **Exit 20 (timeout)** — hard cap reached. Report to caller and close.
- **Exit 30 (extraction)** — the report selector didn't find enough content.
  Can be retried once (re-run `extract`); if it fails again, send `ERROR:`.

## Platform Quirks
- **Enter = newline**: Unlike other platforms, pressing Enter in claude.ai adds a newline. The driver clicks "Send message" button.
- **Connectors dialog**: Appears on EVERY research start. The driver dismisses it automatically with "Disable all tools" → "Confirm".
- **Artifact panel**: Research reports render in a document/artifact panel. The driver clicks "Open artifact" before extraction.
- **Plan auto-executes**: Research starts immediately after prompt submission (`plan_review: informational`). No approval gate needed.
