# Agentic Workflow

A collection of skills for AI coding agents (Claude Code, etc.).

## Skills

| Skill | Install | Description |
|-------|---------|-------------|
| **flow** | `npx skills add kzarzycki/agent-skills@flow -g -y` | Persistent workflow orchestration. Survives context resets, delegates to subagents, tracks work items. |

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
