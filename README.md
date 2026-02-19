# Flow

Persistent workflow orchestration for Claude Code. Survives context resets, delegates to subagents, tracks independent work items.

## Quick Install

Run this single command to install Flow globally (works in any project):

```bash
npx skills add kzarzycki/agentic-workflow@flow -g -y
```

Then in any project, run `/flow:init` inside Claude Code to set up the workspace.

## Project-Level Install

To install Flow into a specific project (so teammates get it on clone):

```bash
mkdir -p .claude/skills/flow && \
  git clone --depth 1 https://github.com/kzarzycki/agentic-workflow.git /tmp/agentic-workflow-dl && \
  cp -r /tmp/agentic-workflow-dl/flow/* .claude/skills/flow/ && \
  rm -rf /tmp/agentic-workflow-dl
```

This puts the skill in `.claude/skills/flow/`. Claude Code discovers it automatically.

For projects with multiple Claude skills, see `Makefile.example` — it provides `make install-claude-deps` with a skill registry.

After installing, run `/flow:init` inside Claude Code to complete setup (creates `.work/`, hooks, CLAUDE.md).

## What /flow:init Does

Running `/flow:init` inside Claude Code sets up:

| What | Where | Purpose |
|------|-------|---------|
| Project state | `.work/` | brief, items, log, ideas — survives context resets |
| Behavioral rules | `CLAUDE.md` | Instructions so CC always follows Flow methodology |
| Session hook | `.claude/hooks/flow-bootstrap.sh` | Injects .work/ state on every session start |
| Hook registration | `.claude/settings.json` | Registers the SessionStart hook |

After init, every new CC session automatically recovers project context.

## Commands

| Command | Purpose |
|---------|---------|
| `/flow:init` | Initialize Flow workspace in a project |
| `/flow:research [topic]` | Research a topic (delegates to subagent) |
| `/flow:status` | Show all items, progress, suggested next action |
| `/flow:quick [task]` | Quick task without full item ceremony |

## Natural Conversation

Flow also activates from natural language — no commands needed:

- "Let's work on authentication" -> creates or switches to item
- "Research auth options" -> spawns research agent
- "Plan this" / "break this down" -> creates execution plan
- "Go ahead and build it" -> spawns executor agent
- "Verify it works" -> runs verification
- "Where are we?" -> shows status
- "Remind me to add logging later" -> captures in ideas
- "That's done" -> marks item complete

## Concepts

**Work items** — independent scopes of work in `.work/items/<name>/`. Each follows: Research -> Plan -> Execute -> Verify -> Done (any step skippable). Items contain `ITEM.md` (manifest), `research.md` (findings), `plan.md` (execution plan).

**Tempo** — structured (default: larger chunks, acceptance criteria) or creative (small iterations, frequent feedback, saved versions).

**Delegation** — main CC handles discussion, status, item management. Subagents handle research, planning, execution, verification — each gets a fresh 200k context with methodology + project brief + item context.

**Context recovery** — `.work/` persists everything. The SessionStart hook injects state before CC processes any message, so it always knows where you left off.
