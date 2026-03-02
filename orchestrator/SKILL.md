---
name: orchestrator
description: "Orchestrator mode — restrict main Claude Code thread to read-only, forcing delegation of all file writes to subagents via Task(). Use when toggling orchestrator mode (on/off/status), setting up orchestrator in a project, or when orchestrator hook blocks a tool call."
---

# Orchestrator Mode

Read-only main thread. All file writes delegated to subagents.

$ARGUMENTS — "on", "off", "status", "toggle", or "setup"

## Usage

If $ARGUMENTS is "setup": follow [setup instructions](references/setup.md).

Otherwise: run the toggle script from the project root:

```bash
bash .claude/skills/orchestrator/scripts/orchestrator-toggle.sh $ARGUMENTS
```

Report result to user. Change takes effect immediately.

## What Gets Blocked (main thread only)

- Edit, Write, MultiEdit tools
- Bash: >, >>, tee, sed -i, touch, mkdir, cp, mv, chmod, install
- Plan mode file writes are exempted

## What Stays Allowed

- Read, Grep, Glob, Task (delegation)
- Bash: git, gh, ls, cat, grep, curl, test runners
- All tools from subagents (they bypass the hook)

For hook internals and customization: see [internals.md](references/internals.md).
