---
name: gemini-deep-research
description: >
  Platform knowledge for Gemini Deep Research at gemini.google.com. Standalone: spawns
  browser-researcher agent. Or loaded by browser-researcher at runtime via skill_path.
  Trigger on "gemini deep research", "use gemini to research", "run deep research on
  gemini", "google deep research", or when explicitly requesting Gemini's native deep
  research capability.
context: fork
model: opus
---

# Gemini Deep Research — Platform Knowledge

## Standalone Invocation

If invoked directly via /gemini-deep-research, spawn the browser-researcher agent:
```
Agent(
  subagent_type="browser-researcher",
  name="gemini-researcher",
  prompt="skill_path: <skill-path>/SKILL.md\nresearch_prompt: <from user>\noutput_path: <from user or .work/gemini-report.md>\ncaller: <your name>",
  run_in_background=true
)
```
Then relay messages between user and agent via SendMessage. If loaded by browser-researcher via Read, ignore this section.

## Platform Configuration

- url: https://gemini.google.com/app
- backend: playwright-cli
- submit_method: enter_key
- plan_review: gated
- hard_timeout: 90
- completion_signal: "I've completed your research"

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
| Plan revision | `python3 scripts/pw-driver.py revise-plan --text-file=<path>` (or `--text=<str>`) |
| Research monitoring | `python3 scripts/pw-driver.py wait-complete --timeout=5400` |
| Report extraction | `python3 scripts/pw-driver.py extract --output=<path>` |
| Session close | `python3 scripts/pw-driver.py close` |

Exit codes: 0 success · 10 login required · 20 timeout · 30 extraction failure · 40 DOM mismatch.

## DOM Reference (verified March 2026)

- Report container: `div.markdown.markdown-main-panel` (select largest by text length)
- Prompt input: textbox "Enter a prompt for Gemini"
- Deep Research toggle: button "Deselect Deep research" (X on chip)
- Model picker: button "Open mode picker"
- Completion text: "I've completed your research. Feel free to ask me follow-up questions or request changes."

These selectors may change as Google updates Gemini's UI.

## Platform Quirks

- **Clarifying forms**: Gemini may show refinement questions (checkboxes, dropdowns) before research. Handle autonomously based on the research prompt context. Only escalate genuinely ambiguous questions.
- **Pro model selection**: Always select Pro for best results. If already selected, dismiss picker.
- **Report panel**: Opens on the right side after completion. If not visible, look for the report link card in chat and click it.
- **Research activation**: 4-step sequence — Tools button → Deep Research item → model picker → Pro model.
