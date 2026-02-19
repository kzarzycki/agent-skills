# Flow

Persistent workflow orchestration for Claude Code. Survives context resets, delegates to subagents, tracks independent work items.

## Install

### Option A: Global (personal use across all projects)

```bash
npx skills add kzarzycki/agentic-workflow@flow -g -y
```

### Option B: Project-level (team use, travels with repo)

Copy `Makefile.example` into your project (or merge into existing Makefile). Add skills to the registry:

```makefile
CLAUDE_SKILLS := \
	kzarzycki/agentic-workflow@flow
#	other-org/other-repo@skill-name
```

Then:

```bash
make install-claude-deps
```

Teammates run `make install-claude-deps` after cloning. Skills land in `.claude/skills/` and Claude Code discovers them automatically. Idempotent — only downloads what's missing. `make update-claude-deps` re-downloads all to latest.

## Setup in a project

After installing the skill (any option above), run in Claude Code:

```
/flow:init
```

This creates:
- `.work/` — project state (brief, items, log, ideas)
- `CLAUDE.md` — instructions so CC always uses Flow
- `.claude/hooks/flow-bootstrap.sh` — injects project state on every session start
- `.claude/settings.json` — registers the hook

After init, every new CC session automatically recovers your project context.

## Usage

### Commands

| Command | Purpose |
|---------|---------|
| `/flow:init` | Initialize Flow in a project |
| `/flow:research [topic]` | Research a topic (delegates to agent) |
| `/flow:status` | Show all items, progress, suggestions |
| `/flow:quick [task]` | Quick task without full ceremony |

### Natural conversation

Flow also activates from natural language — no commands needed:

- "Let's work on authentication" -> creates or switches to item
- "Research auth options" -> spawns research agent
- "Plan this" -> creates execution plan
- "Go ahead and build it" -> spawns executor agent
- "Verify it works" -> runs verification
- "Where are we?" -> shows status
- "Remind me to add logging later" -> captures in ideas

### Work items

Items are independent scopes of work. Each follows: **Research -> Plan -> Execute -> Verify -> Done** (any step skippable).

Items live in `.work/items/<name>/` with:
- `ITEM.md` — goal, status, progress, context references
- `research.md` — findings from research agent
- `plan.md` — execution plan from planning agent

### Tempo

- **Structured** (default) — larger chunks, verify via acceptance criteria
- **Creative** — small iterations, frequent feedback, saved versions

## How it works

Flow enhances Claude Code rather than replacing it. Main CC acts as orchestrator:

- **Handles directly:** discussion, status, item management, quick tasks
- **Delegates to agents:** research, planning, execution, verification

Each agent gets a fresh 200k context with: methodology guide + project brief + item context + standards. Agents return structured results that Flow routes to the right files.

`.work/` persists everything across sessions. The SessionStart hook injects state on every session start, so CC always knows where you left off.
