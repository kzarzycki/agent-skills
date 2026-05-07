---
description: Promote accumulated learning proposals from recent sessions into permanent rules (CLAUDE.md, skill files, MEMORY.md). Status — experimental.
---

# Promote Learnings

> **Status: experimental.** Run at the end of a working session, or periodically (e.g. weekly), when `## Proposed Updates` sections have accumulated in `.agents/memory/daily/`.

Review accumulated learning proposals from recent session daily logs and apply approved ones into the right durable location.

## Steps

1. **Find proposals**: Search `.agents/memory/daily/` for the last 14 days of files containing `## Proposed Updates` sections. If no `.agents/memory/` exists in the current project tree, check `~/.claude/projects/` auto-memory for relevant entries instead.

2. **Present proposals**: Group by target:
   - `[global][claude.md]` → `~/.claude/CLAUDE.md`
   - `[project][claude.md]` → `./CLAUDE.md` (in the current project root)
   - `[project][skill]` → relevant skill file
   - `[global][memory]` or `[project][memory]` → MEMORY.md

3. **For each proposal**: Present the proposal with its date and context. Ask the user: **Apply / Skip / Edit**
   - Apply: add to the target file, deduplicating against existing content
   - Skip: mark as reviewed (add `[skipped]` prefix in the daily log)
   - Edit: let user modify before applying

4. **After all proposals**: Run `/memory curate` to also review the memory side.

5. **Summary**: Show what was applied, where, and what was skipped.

## Rules

- Never apply without explicit user approval per item
- When adding to CLAUDE.md, keep entries concise (1-2 lines max)
- Deduplicate: if a similar rule already exists, propose updating it rather than adding a duplicate
- For global CLAUDE.md: only truly universal rules that apply across ALL project types
- For project CLAUDE.md: domain-specific conventions, patterns, gotchas

## Triggers

`/promote-learnings`, `/promote`, "end of session review", "wrap up", "promote learnings", "review my learnings", "apply session learnings", "consolidate session rules".
