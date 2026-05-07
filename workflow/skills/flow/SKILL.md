---
name: flow
description: Persistent workspace and agent coordination for multi-step work. Activates when .work/ exists, when users discuss work items or planning, or via /flow commands.
---

# Flow — Persistent Workspace Orchestration

Lightweight persistence and structured agent delegation for Claude Code.

## Philosophy

- Main CC thread is the orchestrator. It discusses, shapes, decides, and delegates.
- Heavy lifting (research, planning, execution, verification) goes to subagents.
- `.work/` persists what needs to survive compaction and session boundaries.
- Work streams are independent — any order, parallel, or interleaved. No single "active item."
- Natural conversation is primary. Commands are shortcuts.

## .work/ Workspace

```
.work/
  brief.md              # Project context, constraints, key decisions
  log.md                # Append-only work log (YYYY-MM-DD: description)
  ideas.md              # Quick capture for tangents and future work
  standards/            # User-maintained conventions (read-only for Claude)
  MMDD-<work-stream>/   # Date-prefixed dir per work stream (e.g., 0323-deep-research/)
    ITEM.md             # Manifest: goal, status, context files, progress
    research.md         # Research findings
    plan.md             # Execution plan
    *.md                # Any intermediate agent outputs
```

`brief.md` is the project-level context shared across all work streams. `standards/` contains conventions agents must follow but never modify. Each `<work-stream>/` directory is self-contained — agents working on it read ITEM.md as their manifest.

For iterative/creative work, save versions in `<work-stream>/iterations/` (v01.md, v02.md, etc.).

## Directory Hygiene

### Date-prefix convention
Name work stream dirs as `MMDD-<name>/` (e.g., `0323-deep-research/`). When `.work/` grows to 10+ dirs, the date prefix is the fastest way to find recent work and see chronological progression.

### Root-level files are sacred
Only these belong at `.work/` root: `brief.md`, `log.md`, `ideas.md`, `standards/`. Everything else — research outputs, reviews, designs, speaker notes — goes into a dated work stream dir. When in doubt, create a dir.

### Agent output routing
The coordinator must tell each subagent which work stream dir to write into — give explicit paths like `.work/MMDD-<stream>/filename.md`. Agents can create subdirs *within* the stream dir if they need structure (e.g., `.work/0324-research/deep-reads/`), but must never create new top-level `.work/` dirs on their own. If 5 agents produce output for the same work stream, all 5 write into the same MMDD-dir.

### Avoid single-file dirs
If a work stream will produce only one file, write it into an existing related stream dir rather than creating a new directory. Group related outputs: 5 speaker note drafts → one `MMDD-speaker-notes/` dir with `slide-5.md` through `slide-9.md`, not 5 separate dirs.

### Cleanup heuristic
When orphaned files accumulate at `.work/` root:
1. Check each file's header for date and purpose
2. Group by activity (research, review, style, etc.)
3. Move into existing or new MMDD-prefixed dirs
4. Collapse single-file dirs by merging into a parent dir

### ITEM.md Format

```markdown
# <Work Stream Name>
Created: YYYY-MM-DD

## Context Files
- .work/brief.md
- .work/<name>/research.md
- .work/standards/coding.md

## Goal
<What and why — 2-3 sentences>

## Status: not_started | researching | planning | in_progress | blocked | done

## Progress
- [ ] Research completed
- [ ] Plan created
- [ ] Step 1: ...
- [ ] Step 2: ...

## Log
- YYYY-MM-DD: Created
```

Lifecycle: Create → Research → Plan → Execute → Verify → Done. Any step is skippable or revisitable.

## Working with Agents

**File-driven output:** Agents write all outputs to `.work/<stream>/` and return only the file path + a 1-2 line summary. The coordinator reads files selectively (grep, head, offset+limit) — never pass large content through context.

**Effort scaling:**
- Simple lookup: 1 agent, 3-10 tool calls
- Comparisons or multi-part questions: 2-4 parallel agents
- Deep research or large deliverables: up to 10 agents with divided responsibilities

**Parallel vs sequential:** Independent sub-parts → parallel agents, always. Dependent steps (research → plan) → sequential. Long-running work not needed immediately → background agents.

**Delegation heuristic:** If the task touches >3 files, will produce >100 lines of changes, or requires comparing multiple options → delegate. Discussion, status checks, quick capture, single-file edits → handle directly.

**When spawning an agent:**
1. Ensure the work stream dir exists (`MMDD-<stream>/`). Create it if needed — agents should not.
2. Read the work stream's ITEM.md for its Context Files list
3. Read ALL listed context files
4. Read the relevant methodology from `references/` (research.md, planning.md, execution.md, or verification.md)
5. Inline everything into the agent prompt — context doesn't cross agent boundaries
6. Give the agent an explicit output path: `.work/MMDD-<stream>/filename.md`
7. Use `subagent_type: "general-purpose"`, description: `"<stage>: <stream name>"`

**On agent return:**
1. Verify output landed in the correct `.work/MMDD-<stream>/` dir
2. Update ITEM.md (status, progress checkboxes, log entry)
3. Append to `.work/log.md`

## Work Stream Lifecycle

**Creating:** Confirm scope with user. Create `.work/MMDD-<name>/ITEM.md` (use today's date as MMDD prefix). Log it. Guard: if trivial (< 30 min), suggest quick task instead.

**Research:** Check for existing research first. Spawn research agent with methodology + context. Write to `<stream>/research.md`.

**Planning:** Check for existing research — offer to research first if missing. Spawn planning agent. Write to `<stream>/plan.md`. Present for approval.

**Execution:** Confirm plan. Spawn execution agent. Update progress in ITEM.md.

**Verification:** Spawn verification agent with acceptance criteria from plan.md. Report pass/fail per criterion.

**Completion:** Update status to "done". Log it. If unchecked progress steps remain, mention them first.

**Quick capture:** Append tangents/ideas to `.work/ideas.md` with date. Continue without interruption.

**Quick task:** For small work without full lifecycle — do it directly, log to `.work/log.md` as "Quick — [description]".

## Session Recovery

On session start, if `.work/` exists:
1. Read `brief.md` for project context
2. Scan `.work/*/ITEM.md` for all work streams and their statuses
3. Read last 5 entries from `log.md`
4. Briefly announce: "Found Flow workspace: [project]. [N] work streams: [list with statuses]."
5. Let the user say what they want to work on

Optional: a SessionStart hook (`scripts/flow-bootstrap.sh`) can inject this automatically. Not installed by default.

## Commands

- `/flow:init` — Set up `.work/` workspace for a project
- `/flow:research [topic]` — Research a topic (item-specific or standalone)
- `/flow:status` — Show all work streams, progress, recent activity
- `/flow:quick [task]` — Small task with minimal tracking

## Anti-patterns

- No elaborate scaffolding or PM boilerplate
- Don't create work streams for casual mentions — confirm intent first
- Don't auto-delegate when user is thinking out loud
- Don't re-research what's already researched or re-plan what's planned
- Always check for existing research before planning
- Read `.work/standards/` before planning or executing — include in agent context, never modify
