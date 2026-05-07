---
name: chatgpt-deep-research
description: >
  Platform knowledge for ChatGPT Deep Research at chatgpt.com. Standalone: spawns
  browser-researcher agent. Or loaded by browser-researcher at runtime via skill_path.
  Trigger on "chatgpt deep research", "run this through ChatGPT", "ask ChatGPT to
  research", "delegate to ChatGPT deep research", "use ChatGPT for this research".
  Does NOT trigger on generic "deep research".
context: fork
model: opus
---

# ChatGPT Deep Research — Platform Knowledge

## Standalone Invocation

If invoked directly via /chatgpt-deep-research, spawn the browser-researcher agent:
```
Agent(
  subagent_type="browser-researcher",
  name="chatgpt-researcher",
  prompt="skill_path: <skill-path>/SKILL.md\nresearch_prompt: <from user>\noutput_path: <from user or .work/chatgpt-report.md>\ncaller: <your name>",
  run_in_background=true
)
```
Then relay messages between user and agent via SendMessage. If loaded by browser-researcher via Read, ignore this section.

## Platform Configuration

- url: https://chatgpt.com/deep-research
- backend: playwright-cli
- submit_method: click_send_button
- plan_review: informational  # research auto-starts; approve-plan is a no-op
- hard_timeout: 90
- completion_signal: text "Research completed in" inside nested `root` iframe (sandboxed)

## Playwright-CLI Backend

All browser interaction is driven by `scripts/pw-driver.py` via Bash.
The agent calls subcommands; the driver handles Chrome lifecycle, CDP attach,
and all DOM interaction internally.

| Phase | Subcommand |
|-------|-----------|
| Login check | `python3 scripts/pw-driver.py status` (exit 10 = login required) |
| One-time login | `python3 scripts/pw-driver.py login` (user runs interactively) |
| Research activation + submit | `python3 scripts/pw-driver.py start-research --prompt-file=<path>` |
| Plan capture | `python3 scripts/pw-driver.py wait-plan --timeout=120` |
| Plan approval | `python3 scripts/pw-driver.py approve-plan` |
| Research monitoring | `python3 scripts/pw-driver.py wait-complete --timeout=5400` |
| Report extraction | `python3 scripts/pw-driver.py extract --output=<path>` |
| Session close | `python3 scripts/pw-driver.py close` |

Exit codes: 0 success · 10 login required · 20 timeout · 30 extraction failure · 40 DOM mismatch.

## DOM Reference (verified March 2026)

### Key elements
- button "Deep research" — version dropdown chip in input bar
- textbox with placeholder "Get a detailed report" — main input
- button "Copy response" — copy assistant message to clipboard

### Completion indicators
- Stats: "Research completed in Xm · Y citations · Z searches"
- Report card with title and icons appears
- Response action buttons (Copy, Thumbs up/down, Share, Refresh) appear

## Platform Quirks

- **Obfuscated CSS**: ChatGPT uses obfuscated class names — driver uses accessible names, not CSS selectors.
- **Deep Research already active**: Navigating to `/deep-research` pre-selects the mode. Driver verifies but doesn't need to toggle.
- **Max plan iterations**: 5 iterations before asking caller to approve or abort.
- **Follow-up mode**: After research completes, follow-ups go through standard ChatGPT chat (NOT Deep Research) to save quota.
- **Report container**: `[data-message-author-role="assistant"]` — select last element for the research response.
