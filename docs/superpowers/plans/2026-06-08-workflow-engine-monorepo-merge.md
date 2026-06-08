# Workflow Engine Monorepo Merge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move `/home/agent/dev/workflows` into `/home/agent/dev/agent-skills/workflow/` as part of the existing public `workflow` plugin.

**Architecture:** Preserve the existing workflow plugin as the installable marketplace unit. Add the programmatic workflow engine as a sub-capability under `workflow/`, keeping its skills, agents, workflow command files, core runtime, tests, and repeatable E2E together. Update marketplace docs and plugin metadata so users discover one `workflow` plugin, not a second overlapping plugin.

**Tech Stack:** JavaScript ES modules, Node scripts, Bun test runner, Claude Code plugin layout, Markdown skills/agents/docs.

---

## File Structure

Create or overwrite these target paths from the standalone repo:

- `workflow/skills/workflow/SKILL.md` — workflow engine skill contract.
- `workflow/skills/discuss/SKILL.md` — Discuss skill contract.
- `workflow/skills/tech-options/SKILL.md` — Tech Options skill contract.
- `workflow/agents/interviewer.md` — Discuss interviewer agent.
- `workflow/agents/tech-options-analyst.md` — Tech Options analyst agent.
- `workflow/agents/intent-reviewer.md` — Decision Spec intent reviewer.
- `workflow/agents/testability-reviewer.md` — Decision Spec testability reviewer.
- `workflow/agents/reuse-coverage-reviewer.md` — Tech Options reuse/coverage reviewer.
- `workflow/agents/fit-risk-reviewer.md` — Tech Options fit/risk reviewer.
- `workflow/workflows/*.js` — programmatic command surface and implementation helpers.
- `workflow/workflows/workflow-core/**` — durable state machine, runtime helpers, and tests.
- `workflow/e2e/scenarios/omp-programmatic-mvp.md` — scenario contract.
- `workflow/e2e/tic-tac-toe-workflow-e2e.js` — repeatable simulated-human E2E runner.
- `workflow/e2e/runs/.gitkeep` — keep run directory while ignoring generated runs.

Modify these existing target files:

- `workflow/.claude-plugin/plugin.json` — bump version and mention programmatic workflows.
- `.claude-plugin/marketplace.json` — update existing `workflow` plugin description/tags.
- `README.md` — update workflow plugin summary/highlights and commands.
- `.gitignore` — ignore `workflow/e2e/runs/*` while preserving `workflow/e2e/runs/.gitkeep`.

Do not stage or edit existing untracked `workflow/.in_use/` runtime files.

---

### Task 1: Copy workflow engine assets into the workflow plugin

**Files:**
- Create/overwrite: `workflow/skills/workflow/SKILL.md`
- Create/overwrite: `workflow/skills/discuss/SKILL.md`
- Create/overwrite: `workflow/skills/tech-options/SKILL.md`
- Create: `workflow/agents/*.md`
- Create: `workflow/workflows/*.js`
- Create: `workflow/workflows/workflow-core/**`
- Create: `workflow/e2e/**`

- [ ] **Step 1: Confirm source and target roots**

Run from `/home/agent/dev/agent-skills`:

```bash
pwd
node -e "const fs=require('fs'); for (const p of ['/home/agent/dev/workflows/skills','/home/agent/dev/workflows/agents','/home/agent/dev/workflows/workflows','/home/agent/dev/workflows/e2e','/home/agent/dev/agent-skills/workflow']) { if (!fs.existsSync(p)) throw new Error('missing '+p); console.log('ok', p); }"
```

Expected:

```text
/home/agent/dev/agent-skills
ok /home/agent/dev/workflows/skills
ok /home/agent/dev/workflows/agents
ok /home/agent/dev/workflows/workflows
ok /home/agent/dev/workflows/e2e
ok /home/agent/dev/agent-skills/workflow
```

- [ ] **Step 2: Copy assets with a deterministic Node script**

Run from `/home/agent/dev/agent-skills`:

```bash
node - <<'NODE'
const fs = require('fs');
const path = require('path');

const source = '/home/agent/dev/workflows';
const target = '/home/agent/dev/agent-skills/workflow';
const copies = [
  ['skills/workflow', 'skills/workflow'],
  ['skills/discuss', 'skills/discuss'],
  ['skills/tech-options', 'skills/tech-options'],
  ['agents', 'agents'],
  ['workflows', 'workflows'],
  ['e2e/scenarios', 'e2e/scenarios'],
  ['e2e/tic-tac-toe-workflow-e2e.js', 'e2e/tic-tac-toe-workflow-e2e.js'],
];

for (const [srcRel, destRel] of copies) {
  const src = path.join(source, srcRel);
  const dest = path.join(target, destRel);
  fs.rmSync(dest, { recursive: true, force: true });
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  fs.cpSync(src, dest, { recursive: true, force: false, dereference: false });
  console.log(`${destRel} <- ${srcRel}`);
}
fs.mkdirSync(path.join(target, 'e2e/runs'), { recursive: true });
fs.writeFileSync(path.join(target, 'e2e/runs/.gitkeep'), '');
NODE
```

Expected output includes:

```text
skills/workflow <- skills/workflow
skills/discuss <- skills/discuss
skills/tech-options <- skills/tech-options
agents <- agents
workflows <- workflows
e2e/scenarios <- e2e/scenarios
e2e/tic-tac-toe-workflow-e2e.js <- e2e/tic-tac-toe-workflow-e2e.js
```

- [ ] **Step 3: Check copied files exist**

Run from `/home/agent/dev/agent-skills`:

```bash
node -e "const fs=require('fs'); const paths=['workflow/skills/workflow/SKILL.md','workflow/skills/discuss/SKILL.md','workflow/skills/tech-options/SKILL.md','workflow/agents/interviewer.md','workflow/workflows/workflow-advance.js','workflow/workflows/workflow-core/index.js','workflow/workflows/workflow-core/test/workflow-drivers.test.js','workflow/e2e/tic-tac-toe-workflow-e2e.js','workflow/e2e/runs/.gitkeep']; for (const p of paths) { if (!fs.existsSync(p)) throw new Error('missing '+p); console.log('present', p); }"
```

Expected: every listed path prints `present <path>`.

- [ ] **Step 4: Commit copied runtime assets only**

Run from `/home/agent/dev/agent-skills`:

```bash
git status --short
git add workflow/skills/workflow workflow/skills/discuss workflow/skills/tech-options workflow/agents workflow/workflows workflow/e2e/scenarios workflow/e2e/tic-tac-toe-workflow-e2e.js workflow/e2e/runs/.gitkeep
git status --short
git commit -m "feat(workflow): add programmatic workflow engine assets"
```

Expected:

- `workflow/.in_use/` may still appear as untracked before and after `git add`.
- The commit includes only `workflow/skills/...`, `workflow/agents/...`, `workflow/workflows/...`, and `workflow/e2e/...` files.

---

### Task 2: Add target package wiring for tests and E2E

**Files:**
- Create: `package.json` if absent, or modify existing root `package.json` if present.
- Modify: `.gitignore`

- [ ] **Step 1: Check whether target root has a package manifest**

Run from `/home/agent/dev/agent-skills`:

```bash
node -e "const fs=require('fs'); console.log(fs.existsSync('package.json') ? 'package.json exists' : 'package.json missing')"
```

Expected before this migration: `package.json missing`.

- [ ] **Step 2: Create or update `package.json` with focused scripts**

If `package.json` is missing, create exactly:

```json
{
  "name": "agent-skills",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "test:workflow-engine": "bun test ./workflow/workflows/workflow-core/test/*.test.js",
    "e2e:workflow-tic-tac-toe": "node ./workflow/e2e/tic-tac-toe-workflow-e2e.js"
  }
}
```

If `package.json` exists, preserve existing fields and add these scripts under `scripts`:

```json
{
  "test:workflow-engine": "bun test ./workflow/workflows/workflow-core/test/*.test.js",
  "e2e:workflow-tic-tac-toe": "node ./workflow/e2e/tic-tac-toe-workflow-e2e.js"
}
```

- [ ] **Step 3: Update the E2E runner paths after relocation**

Modify `workflow/e2e/tic-tac-toe-workflow-e2e.js` imports and base dir.

Replace the import path:

```js
} from '../workflows/workflow-core/index.js';
```

with:

```js
} from '../workflows/workflow-core/index.js';
```

The relative path is already correct after relocation because the file now lives at `workflow/e2e/tic-tac-toe-workflow-e2e.js` and imports from `workflow/workflows/workflow-core/index.js`. No code change is expected here; this step is an explicit verification.

Verify with:

```bash
node -e "const fs=require('fs'); const text=fs.readFileSync('workflow/e2e/tic-tac-toe-workflow-e2e.js','utf8'); if (!text.includes(\"from '../workflows/workflow-core/index.js'\")) throw new Error('bad import path'); console.log('import path ok');"
```

Expected: `import path ok`.

- [ ] **Step 4: Update `.gitignore` for moved E2E runs**

Ensure `.gitignore` contains these lines:

```gitignore
workflow/e2e/runs/*
!workflow/e2e/runs/.gitkeep
```

Keep existing ignore rules. The final `.gitignore` should include at least:

```gitignore
.DS_Store
node_modules/
workflow/e2e/runs/*
!workflow/e2e/runs/.gitkeep
```

- [ ] **Step 5: Commit package and ignore wiring**

Run from `/home/agent/dev/agent-skills`:

```bash
git add package.json .gitignore workflow/e2e/tic-tac-toe-workflow-e2e.js
git status --short
git commit -m "chore(workflow): wire programmatic workflow tests"
```

Expected: commit contains package/ignore wiring and no `workflow/.in_use/` files.

---

### Task 3: Update marketplace and plugin documentation

**Files:**
- Modify: `workflow/.claude-plugin/plugin.json`
- Modify: `.claude-plugin/marketplace.json`
- Modify: `README.md`

- [ ] **Step 1: Update `workflow/.claude-plugin/plugin.json`**

Set version to `0.3.0` and replace description with:

```json
"Persistent workspace, agent orchestration, session search, learning consolidation, and programmatic workflow engine for Claude Code. Bundles flow (.work/ workspaces with subagent delegation), autopilot, orchestrator, find-conversation, /promote-learnings, and durable Discuss -> Tech Options workflows with human gates and fixed model reviewers."
```

Expected relevant file shape:

```json
{
  "name": "workflow",
  "version": "0.3.0",
  "description": "Persistent workspace, agent orchestration, session search, learning consolidation, and programmatic workflow engine for Claude Code. Bundles flow (.work/ workspaces with subagent delegation), autopilot, orchestrator, find-conversation, /promote-learnings, and durable Discuss -> Tech Options workflows with human gates and fixed model reviewers.",
  "author": {
    "name": "Krzysztof Zarzycki"
  }
}
```

- [ ] **Step 2: Update root marketplace workflow entry**

In `.claude-plugin/marketplace.json`, update only the plugin object with `"name": "workflow"`.

Set `description` to:

```json
"Persistent workspace, agent orchestration, session search, learning consolidation, and programmatic workflow engine. Includes flow (.work/ workspaces), autopilot, orchestrator, find-conversation, /promote-learnings, and durable Discuss -> Tech Options workflows with human gates and fixed reviewers."
```

Set `tags` to include:

```json
["flow", "orchestration", "memory", "sessions", "workflow-engine", "review-gates"]
```

- [ ] **Step 3: Update `README.md` plugin table row**

Replace the workflow row with:

```markdown
| **workflow** | `flow` (.work/ workspace + subagent delegation), `autopilot` (brainstorm→PR pipeline), `orchestrator` (restrict main thread to read-only), `find-conversation` (search past CC sessions), and the programmatic workflow engine for durable Discuss → Tech Options flows with human gates. Plus the experimental `/promote-learnings` command. |
```

- [ ] **Step 4: Update `README.md` workflow highlights**

Under `### workflow`, replace the existing paragraph with:

```markdown
`/flow:init` bootstraps a `.work/` workspace per project — a Date-prefixed dir per work stream, append-only `log.md`, idea capture, ITEM.md manifest with research/plan/execute/verify lifecycle. `/orchestrator on` restricts the main thread to read-only and forces writes through subagents. The programmatic workflow engine adds durable Discuss → Tech Options workflows: `workflow-start`, `workflow-event`, `workflow-advance`, `workflow-status`, and `workflow-resume` drive `.workflow/<workId>/_state/state.json`, keep human artifacts limited to `01-DECISION-SPEC.md` and `02-TECH-OPTIONS.md`, and run fixed reviewer gates before planning handoff.
```

- [ ] **Step 5: Commit docs and metadata**

Run from `/home/agent/dev/agent-skills`:

```bash
git add workflow/.claude-plugin/plugin.json .claude-plugin/marketplace.json README.md
git status --short
git commit -m "docs(workflow): document programmatic workflow engine"
```

Expected: commit contains only metadata/docs files.

---

### Task 4: Run focused verification from the monorepo

**Files:**
- No source changes expected.
- Runtime output expected under ignored `workflow/e2e/runs/`.

- [ ] **Step 1: Run moved workflow-core tests**

Run from `/home/agent/dev/agent-skills`:

```bash
bun test ./workflow/workflows/workflow-core/test/*.test.js
```

Expected:

```text
44 pass
1 skip
0 fail
```

- [ ] **Step 2: Run repeatable tic-tac-toe E2E**

Run from `/home/agent/dev/agent-skills`:

```bash
npm run e2e:workflow-tic-tac-toe
```

Expected output includes:

```text
PASS tic-tac-toe workflow e2e
final: planning/planning_pending r9
approved phases: discuss, tech_options
```

- [ ] **Step 3: Verify generated E2E artifacts are ignored**

Run from `/home/agent/dev/agent-skills`:

```bash
git status --short
```

Expected:

- No generated `workflow/e2e/runs/tic-tac-toe-workflow/...` files are shown.
- Existing `?? workflow/.in_use/` may still be shown and must remain unstaged.

- [ ] **Step 4: Commit verification-only fixes if needed**

If Task 4 reveals path or ignore-rule bugs, make the minimal fix and commit:

```bash
git add package.json .gitignore workflow/e2e/tic-tac-toe-workflow-e2e.js workflow/workflows/workflow-core workflow/workflows/*.js
git status --short
git commit -m "fix(workflow): make moved workflow engine verification pass"
```

Expected: skip this commit if Task 4 passes without changes.

---

### Task 5: Final repository hygiene

**Files:**
- No changes expected unless prior tasks missed docs or ignore rules.

- [ ] **Step 1: Confirm commit history includes the design and implementation commits**

Run from `/home/agent/dev/agent-skills`:

```bash
git log --oneline -5
```

Expected: recent history includes:

```text
docs: design workflow engine monorepo merge
feat(workflow): add programmatic workflow engine assets
chore(workflow): wire programmatic workflow tests
docs(workflow): document programmatic workflow engine
```

Ordering may differ if a verification fix commit was needed.

- [ ] **Step 2: Confirm only known untracked runtime files remain**

Run from `/home/agent/dev/agent-skills`:

```bash
git status --short
```

Expected:

```text
?? workflow/.in_use/
```

If the status is clean instead, that is also acceptable. Any other path must be explained and either committed intentionally or removed if generated.

- [ ] **Step 3: Report final result**

Final report must include:

```text
Merged into: /home/agent/dev/agent-skills/workflow
Verification:
- bun test ./workflow/workflows/workflow-core/test/*.test.js: PASS
- npm run e2e:workflow-tic-tac-toe: PASS
Commits:
- <commit hashes and subjects>
Untracked intentionally left alone:
- workflow/.in_use/ (if still present)
```

---

## Self-Review Notes

Spec coverage:

- Target layout covered by Task 1.
- Package/test wiring covered by Task 2.
- Marketplace and README discoverability covered by Task 3.
- Focused tests and tic-tac-toe E2E covered by Task 4.
- Staging/runtime-file hygiene covered by Task 5.

Placeholder scan:

- No `TBD`, `TODO`, `implement later`, or unspecified test steps.
- All commands include expected outputs.

Type/path consistency:

- Source root is consistently `/home/agent/dev/workflows`.
- Target root is consistently `/home/agent/dev/agent-skills`.
- Runtime imports preserve `workflow/e2e` -> `workflow/workflows/workflow-core` relative path.
