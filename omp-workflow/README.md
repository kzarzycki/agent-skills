# omp-workflow

Durable state-machine workflow driver for the OMP runtime. Module-style scripts (`workflows/*.js`) plus the engine core (`workflow-core/`) own `_state/state.json` per work item and advance it deterministically: `workflow-start` scaffolds, `workflow-advance` runs one autonomous step, `workflow-event` applies human decisions, `workflow-resume`/`workflow-status` report.

NOT runnable under the Claude Code Workflow tool — these scripts use ES module imports, which the sandboxed Workflow runner does not support. That is why this lives outside the `workflow/` plugin: the plugin contains only Claude Code orchestration (skills, agents, contracts, sandbox-style Workflow scripts).

Shared machine truth stays in the plugin: `../workflow/contracts/` (work-item layout, artifact section contracts, mdsmith format gate). This runtime reads those contracts; it does not own them.

Tests:

```
npm run test:workflow-engine
# or
node --test omp-workflow/workflow-core/test/*.test.js
```
