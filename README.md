# Agentic Workflow

A collection of skills for AI coding agents (Claude Code, etc.).

## Skills

| Skill | Install | Description |
|-------|---------|-------------|
| **flow** | `npx skills add kzarzycki/agent-skills@flow -g -y` | Persistent workflow orchestration. Survives context resets, delegates to subagents, tracks work items. |
| **orchestrator** | `npx skills add kzarzycki/agent-skills@orchestrator -g -y` | Orchestrator mode — restrict main thread to read-only, forcing delegation of all file writes to subagents via Task(). |

After installing a skill globally, it's available in every project. For project-level install (so teammates get it on clone), see below.

## Installing a Skill

### Global (recommended for personal use)

```bash
npx skills add kzarzycki/agent-skills@<skill> -g -y
```

### Project-Level (for team repos)

```bash
SKILL=flow && \
  mkdir -p .claude/skills/$SKILL && \
  git clone --depth 1 https://github.com/kzarzycki/agent-skills.git /tmp/agent-skills-dl && \
  cp -r /tmp/agent-skills-dl/$SKILL/* .claude/skills/$SKILL/ && \
  rm -rf /tmp/agent-skills-dl
```

For projects with multiple Claude skills, see `Makefile.example` — it provides `make install-claude-deps` with a skill registry.

---

## Flow

Persistent workflow orchestration. Survives context resets, delegates to subagents, tracks independent work items.

After installing, run `/flow:init` inside Claude Code to set up the workspace. This creates:

| What | Where | Purpose |
|------|-------|---------|
| Project state | `.work/` | brief, items, log, ideas — survives context resets |
| Behavioral rules | `CLAUDE.md` | Instructions so the agent always follows Flow methodology |
| Session hook | `.claude/hooks/flow-bootstrap.sh` | Injects .work/ state on every session start |
| Hook registration | `.claude/settings.json` | Registers the SessionStart hook |

### Commands

| Command | Purpose |
|---------|---------|
| `/flow:init` | Initialize Flow workspace in a project |
| `/flow:research [topic]` | Research a topic (delegates to subagent) |
| `/flow:status` | Show all items, progress, suggested next action |
| `/flow:quick [task]` | Quick task without full item ceremony |

Also works from natural conversation — "research X", "plan this", "where are we?", etc.

---

## Orchestrator

Orchestrator mode restricts the main Claude Code thread to read-only operations, forcing all file writes to be delegated to subagents via `Task()`. This enforces a clean separation between planning (main thread) and execution (subagents).

After installing, run `/orchestrator setup` to install the PreToolUse hook and toggle script into your project.

### Commands

| Command | Purpose |
|---------|---------|
| `/orchestrator on` | Activate orchestrator mode |
| `/orchestrator off` | Deactivate orchestrator mode |
| `/orchestrator status` | Check if orchestrator mode is on or off |
| `/orchestrator toggle` | Toggle orchestrator mode |
| `/orchestrator setup` | Install hook and toggle script into current project |

### Always-Active Protections

Even without orchestrator mode enabled, the hook provides:

- **`.env` file blocking** — prevents access to `.env` files (allows `.env.sample`)
- **Dangerous `rm` blocking** — prevents `rm -rf` and similar destructive commands
