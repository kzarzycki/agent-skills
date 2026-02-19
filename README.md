# Flow

Persistent workflow orchestration for Claude Code. Survives context resets, delegates to subagents, tracks independent work items.

## Install

### Option A: Global (personal use across all projects)

```bash
npx skills add kzarzycki/agentic-workflow@flow -g -y
```

### Option B: Project-level (team use, travels with repo)

Add to your Makefile (see `Makefile.example`):

```makefile
FLOW_REPO := kzarzycki/agentic-workflow
FLOW_SKILL_DIR := .claude/skills/flow
FLOW_TMP := /tmp/flow-skill-$(shell date +%s)

install-flow: $(FLOW_SKILL_DIR)/SKILL.md

$(FLOW_SKILL_DIR)/SKILL.md:
	@mkdir -p $(FLOW_SKILL_DIR)
	@git clone --depth 1 https://github.com/$(FLOW_REPO).git $(FLOW_TMP)
	@cp -r $(FLOW_TMP)/flow/* $(FLOW_SKILL_DIR)/
	@rm -rf $(FLOW_TMP)
```

Then:

```bash
make install-flow
```

Teammates run `make install-flow` after cloning. The skill lands in `.claude/skills/flow/` and Claude Code discovers it automatically.

### Option C: One-liner (no Makefile)

```bash
git clone --depth 1 https://github.com/kzarzycki/agentic-workflow.git /tmp/flow-dl && \
  mkdir -p .claude/skills/flow && \
  cp -r /tmp/flow-dl/flow/* .claude/skills/flow/ && \
  rm -rf /tmp/flow-dl
```

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
