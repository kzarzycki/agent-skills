Initialize a Flow workspace for this project. Creates `.work/` directory and adds Flow instructions to CLAUDE.md.

Follow these steps:

1. Check if `.work/` already exists in the project root:
   - If yes: read brief.md and scan `*/ITEM.md`, then ask "Found existing workspace for [project]. Continue with it, or start fresh?"
   - If starting fresh: confirm before deleting

2. Ask conversationally (2-3 questions max):
   - "What are you working on?" (project purpose, goals)
   - Follow up once for constraints, key decisions, or tech stack if not obvious

3. Create the .work/ directory structure:
   ```
   .work/
     brief.md
     log.md
     ideas.md
     standards/
   ```

4. Write brief.md with: project name, description, key constraints, tech decisions from the conversation.

5. Write log.md:
   ```markdown
   # Work Log
   - YYYY-MM-DD: Project initialized.
   ```

6. Write ideas.md:
   ```markdown
   # Ideas
   Quick capture for things to revisit later.
   ```

7. **CLAUDE.md** — Append a Flow section to `CLAUDE.md` in the project root (create if it doesn't exist). If CLAUDE.md already has a Flow section, skip. Content to append:

   ```markdown

   ## Flow Workflow

   This project uses Flow for persistent workflow orchestration.

   On every session start, check `.work/` for project context and active work streams.

   Key behaviors:
   - Scan .work/*/ITEM.md for work streams and their statuses
   - Read a work stream's ITEM.md before doing work on it
   - Follow lifecycle: Research → Plan → Execute → Verify (any step skippable)
   - Delegate research, planning, execution, verification to subagents (read methodology from Flow skill's references/)
   - Log all significant work to .work/log.md
   - Capture ideas and tangents in .work/ideas.md
   ```

8. Ask about git:
   - "Track .work/ in git (for team sharing) or add to .gitignore (solo/private)?"
   - If gitignore: add `.work/` to .gitignore

9. If the conversation revealed a first work stream, offer to create it:
   - "Sounds like '[name]' could be your first work stream. Create it?"

10. Confirm: "Flow workspace created. `.work/` ready, CLAUDE.md updated."

**Optional — SessionStart hook:** If the user wants automatic context injection on session start, offer to install `scripts/flow-bootstrap.sh` as a SessionStart hook. This requires creating `.claude/hooks/flow-bootstrap.sh` and registering it in `.claude/settings.json`. Most users don't need this — reading `.work/` directly on first interaction works fine.
