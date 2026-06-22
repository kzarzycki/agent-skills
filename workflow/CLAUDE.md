# Workflow Framework

## What this is

An orchestration workflow framework that implements a **software factory** — local for now (this repo, one user's machine), but that is the ambition being built. It guides the user through the stages of his job's typical workflows; the engineering pipeline (Spec → Tech Design → Plan → Implement → ship) is the first instantiation, not the definition. End-goal: full autonomy between gates — idea→PR with the human only at ideation, artifact review, and ship approval.

It is NOT yet another spec-driven framework or set of engineering skills. It is a meta-layer ON TOP of existing skill libraries (Superpowers, Matt Pocock's skills, Addy Osmani's skills): it leverages them, never reimplements them, and the skill set in use is swappable. Where a library skill doesn't quite fit, the framework overlays it — adapting it at the seam — rather than forking it.

What it provides:

- Programmatic quality gates: independent reviewers, feedback loop with autonomous fixes, schematized inputs/outputs with programmatic validation.
- Human stages: ideation/spec'ing, review and refinement of outcomes, approval of shippables.
- Orchestrator discipline: every stage is delegated (teammates, dynamic workflows, subagents — including subagents spawning subagents), even stages requiring human interaction. The orchestrator's context stays clean.

**Loop engineering** is a goal in itself, at both levels:

- Inner loop: each phase converges autonomously — author → format gate → independent reviewers → fix — capped, so artifacts reach the user gate already vetted.
- Outer loop: the framework improves itself — evals measure the pipeline, variants are compared, skills swapped, repeat.

The **eval framework** (active work item) is the outer loop's instrument: see that the pipeline works, measure improvements, compare variants.

## Toolkit

What we are equipped with to implement the workflow:

1. **Teams of agents (teammates, experimental):** even interactive work like interviewing is delegated to a teammate and only relayed through the main agent.
2. **Dynamic workflows** (Workflow tool), including saved ones — for reference or direct use. They implement the fixed, unsupervised, autonomous parts of the workflow.
3. **Subagents spawning subagents:** arbitrary subagent trees.

Core orchestration concepts (list to be extended):

- **Generator–reviewer feedback loops:** continue the same agent with feedback; continue the same reviewer so it doesn't repeat earlier findings.
- **Fan-out / fan-in:** parallel independent agents, results aggregated by one.
- **Synthesize once, pass by reference:** context travels through files or workflow returns, not re-read or re-generated per agent — saves tokens.
- **Token efficiency** as a design value throughout — inspiration: Cloudflare's AI code review write-up ([https://blog.cloudflare.com/ai-code-review/](https://blog.cloudflare.com/ai-code-review/)), adapted to our environment.

## Architecture rules (binding)

- **4-layer ownership, one owner per fact:** `contracts/*.json` + `contracts/mdsmith.yml` = machine truth (sections, format rules) · `skills/<phase>/SKILL.md` = the phase contract · `agents/*.md` = thin execution wrappers with `skills:` preloads · reviewer agents = normative checklists.
- **Swap mandate:** phase skills own only the gate contract (artifact, schema, reviewers, verdicts, rework loop); the engineering craft (interviewing, research, planning, TDD) comes from a swappable underlying skill. Known gap: spec and tech-design currently embed the craft themselves — do not copy that pattern; migration pending.
- **Stateless engine for v1:** chat history is the state, work-item files are the record. External state management will come in future versions.
- **`omp-workflow/`** (top-level sibling) is a separate runtime with its own module-style scripts, meant as the programmatic implementation of this workflow — but it lags behind. This plugin is the reference; never let omp-workflow's conventions or state leak in here.

## Operational reference

- Work item: `.workflow/<yyyy-mm-dd>-<slug>/` — numbered root human artifacts (`01-DECISION-SPEC.mdx`, `02-TECH-DESIGN.md`), runtime extras in `_phases/<phase>/`, review evidence in `_reviews/<phase>/<reviewer>.md`. No routine history files; current truth in the artifact, history in its Approval record.
- Verdicts: exactly `pass` | `needs-rework` | `needs-user`. Aggregation: any `needs-user` wins, else any `needs-rework`, else `pass`. Rework cap: 2 per phase, then escalate to the user. `needs-user` = a product question only the user can answer.
- Format gate: `mdsmith check -c <plugin>/contracts/mdsmith.yml <artifact>` (binary in `~/.local/bin`). MDS020 structure violations = hard, fix before the user sees the artifact. MDS023/MDS036/MDS056 language budget = rework input, not a blocker.
- Workflow-tool scripts (`workflows/*.js`): sandbox style — `export const meta` is the first statement, no imports/fs/Node APIs/`Date.now`, top-level `return` is fine. The named-workflow registry is built at session start; for a script added mid-session pass `scriptPath`. Agent types must be plugin-qualified (`workflow:tech-designer`).
- Artifact shape: structure over prose — tables and lists with bold lead-ins, ~300 words for nuanced sections, short sentences. Sections come from the contract JSON; line 1 is an H1, sections are H2 in contract order, no frontmatter.


