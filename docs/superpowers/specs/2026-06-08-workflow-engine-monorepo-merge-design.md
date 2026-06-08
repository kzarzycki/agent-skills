# Workflow Engine Monorepo Merge Design

## Goal

Move the standalone `workflows` repo into the public `agent-skills` monorepo as part of the existing `workflow` plugin, without creating a second overlapping marketplace plugin.

## Current context

- Source repo: `/home/agent/dev/workflows` contains programmatic OMP workflow commands, `workflow-core`, skills, agents, plugin manifests, tests, and E2E scenarios.
- Target repo: `/home/agent/dev/agent-skills` is the public plugin marketplace with independent plugins under `workflow/`, `research/`, `engineering/`, and `content/`.
- Existing target plugin `workflow` already covers orchestration, flow, autopilot, orchestrator mode, session search, and learning consolidation.
- New engine belongs under `workflow` because it is another workflow orchestration surface, not a separate product category.

## Decision

Merge the standalone workflow engine into `agent-skills/workflow/` as a sub-capability of the existing `workflow` plugin.

Rejected alternatives:

- New marketplace plugin such as `programmatic-workflows`: cleaner boundary, but creates user confusion and install overlap with `workflow`.
- Archive-style folder copied without plugin wiring: preserves code, but does not make it a usable public plugin capability.

## Target layout

- `workflow/skills/workflow/`, `workflow/skills/discuss/`, `workflow/skills/tech-options/` receive the source skills.
- `workflow/agents/*.md` receives the source role contracts: interviewer, tech-options analyst, and fixed reviewers.
- `workflow/workflows/*.js` and `workflow/workflows/workflow-core/` receive OMP/programmatic commands and durable core runtime.
- `workflow/e2e/` receives repeatable scenarios and the tic-tac-toe simulated-human E2E runner.
- Root marketplace docs and `workflow/.claude-plugin/plugin.json` are updated to mention the programmatic workflow engine.
- Source repo learning notes such as `AGENTS.md` are not copied as-is; relevant guidance is folded into the monorepo docs only where useful.

## Architecture and data flow

The merged capability keeps two surfaces with one conceptual model:

1. Claude Code skill surface: skills route workflow/discuss/tech-options behavior through agents.
2. OMP programmatic surface: `workflow-start`, `workflow-event`, `workflow-advance`, `workflow-status`, and `workflow-resume` drive durable state in `.workflow/<workId>/_state/state.json`.

Both surfaces must keep the existing invariant: workflow phases use agents, and agents use skills. Agents may use plugin-local skills (`workflow`, `discuss`, `tech-options`) or external skills such as Matt Pocock `/grill-me`.

The OMP core remains a state/programmatic engine. It should not inline phase prose logic that belongs in skills or agents.

## Migration steps

1. Copy source assets into `agent-skills/workflow/` using the target layout above.
2. Preserve executable/runtime paths expected by source tests: imports under `workflow/workflows/...` should continue to resolve relative to their new location.
3. Add or update target package/test wiring only as needed to run the moved workflow-core tests and tic-tac-toe E2E.
4. Update marketplace/plugin metadata and README copy so users discover the new programmatic engine under the existing `workflow` plugin.
5. Run focused verification from the target repo.

## Error handling and gotchas

- Preserve strict state schema behavior: unknown keys and invalid phase/state pairs stay invalid.
- Preserve revision checks and lock-file persistence in `state-store.js`.
- Preserve root artifact policy: only `01-DECISION-SPEC.md` and `02-TECH-OPTIONS.md` should be human-facing; runtime files stay under underscore dirs.
- Avoid adding cross-plugin dependencies. If external skills such as `/grill-me` are referenced, document them as optional/external behavior.
- Do not stage existing untracked `workflow/.in_use/` runtime files in the target repo.

## Testing and QA

Required focused checks after migration:

- Run the moved workflow-core suite from the target repo.
- Run the moved tic-tac-toe simulated-human E2E from the target repo.
- Verify plugin manifests and README mention the merged capability.
- Verify no unintended runtime files are staged.

## Acceptance criteria

- The public monorepo contains the workflow engine under `workflow/`, not as a separate plugin.
- Skills, agents, programmatic commands, workflow-core tests, and E2E scenario are present in target locations.
- Existing workflow plugin metadata/docs describe the new capability.
- Focused tests and tic-tac-toe E2E pass from `/home/agent/dev/agent-skills`.
- Only intended files are staged/committed; existing `workflow/.in_use/` remains untouched.
