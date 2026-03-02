# Orchestrator Internals

Technical details for debugging and customization.

## Sentinel Files

- `.claude/orchestrator-mode` — presence = orchestrator mode active
- `.claude/orchestrator-session` — stores session ID of the main orchestrator session

## Session Detection

The hook uses `is_main_orchestrator_session()` which reads the session ID from `.claude/orchestrator-session`. If that file exists, it compares against the current `session_id` from hook input. Fallback: checks if `/subagents/` is absent from `transcript_path` (main thread heuristic).

## Always-Active Protections

These run regardless of orchestrator mode:

- **`.env` file access** — blocks Read/Edit/Write/Bash access to `.env` files (allows `.env.sample`). In orchestrator mode, subagents are exempted (they may need `.env` for data imports).
- **Dangerous `rm` commands** — blocks `rm -rf`, `rm -fr`, `rm --recursive --force`, and recursive rm targeting `/`, `~`, `$HOME`, `..`, `*`, `.`

## Bash Command Classification

In orchestrator mode, bash commands are classified as:

**Allow** — safe read-only prefixes:
`git`, `gh`, `ls`, `cat`, `head`, `tail`, `find`, `grep`, `rg`, `uv run pytest`, `uv run mypy`, `echo`, `wc`, `diff`, `which`, `pwd`, `curl`, `wget`, `jq`, `sort`, `uniq`, `cut`, `tr`, `awk`, `npm list`, `npm view`, `npm run build`, `npm run dev`, `sleep`, and others.

**Block** — write patterns:
`>` redirect, `>>` append, `tee`, `sed -i`, `touch`, `mkdir`, `cp`, `mv`, `chmod`, `install`, `npm install`, `pip install`.

**Warn** — unknown commands: allowed with stderr warning.

Safe prefixes are checked first, then write patterns. A safe command with a redirect (e.g. `git log > file`) is allowed because safe prefix check comes first.

## Plan Mode Exemption

Writes to `~/.claude/plans/` are always allowed even in orchestrator mode (plan mode needs to edit plan files).

## Logging

Every tool call is appended to `logs/pre_tool_use.json` (created automatically).

## Customization

To add safe prefixes: edit `BASH_SAFE_PREFIXES` list in `pre_tool_use.py`.
To add write patterns: edit `BASH_WRITE_PATTERNS` list in `pre_tool_use.py`.
