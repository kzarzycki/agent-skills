---
paths:
  - "**"
---

# kzarzycki-agent-skills

A marketplace of Claude Code plugins. Each local plugin is a top-level directory with a `.claude-plugin/plugin.json`; every plugin, local or upstream-sourced, is registered in `.claude-plugin/marketplace.json`.

## Layout

- **Local plugins** — `workflow`, `research`, `engineering`, `content`, `playwright`, `experimental`, `utilities`. Each holds `skills/`, and where relevant `agents/`, `commands/`, `contracts/`, `workflows/`. `cos-console` is a mod (a hooks module, no skills): see its README.
- **Upstream plugins** — tracked from GitHub with no local copy, registered in `marketplace.json` via a `source` ref: `google-workspace`, `dagu`, `goal-creator`, `project-templates`.
- **Imported engineering skills** — generated leaves under `engineering/skills/`, declared by `engineering/vendir.yml` and reproduced from the lock, the overlays in `engineering/overlays/skills/` and `engineering/provenance.yml`. Edit a tuned skill at its overlay and run `mise run vendor-engineering`; never edit a generated leaf. `engineering/CLAUDE.md` has the package rules.
- `_attic/` — archived obsolete code, kept out of the live plugins so it stops competing in skill listings. Not loaded. See `_attic/README.md`.
- `omp-workflow/` — a separate sibling runtime. The `workflow` plugin is the reference; never let omp-workflow's conventions or state leak in.
- `evals/`, `docs/` — pipeline evals and design notes.

## Conventions

- A plugin's own `CLAUDE.md` (e.g. `workflow/CLAUDE.md`) is authoritative for that plugin — read it before working there.
- Marketplace descriptions stay plugin-level; individual skills self-describe once a plugin is installed.
- This repo is public. Issues, PRs, commits and docs name no private or internal project, product or customer, nor its tickets or links: describe the case generically ("a project whose main uses a merge queue"). How the loop works is not secret; whose project it ran on is.
- Every file in a skill folder, apart from `agents/`, tests and credits, is named in `SKILL.md` or in a file it points to, with when to read it: harnesses load only `SKILL.md`, so an unnamed file is never read. `tests/test_skill_references.py` enforces this.
- A skill whose scripts need a tool declares it in its `SKILL.md` frontmatter as `metadata.requires`, a quoted, space-separated list of `tool>=version` or bare `tool` entries (`requires: "gh>=2.99.0"`), where `tool` is both the command and its mise tool name. It names every tool the scripts run, not only the one a version gate checks. It is data for a host installer, which provides each tool, and its doctor, which reports one a host lacks. No harness lists it to the model, so a requirement costs nothing until the skill is read. `tests/test_skill_requires.py` checks the format.
- Skills teach **methods** (how a tool behaves, a pattern that holds anywhere); **policies** (when to ask, branch/worktree layout, gates, effort rules) belong to the consuming project's own instructions. A skill may say "put the project's rule here", never state the rule. The exception is `engineering-loop`: its policies (when to ask, gates, landing) are the method it ships, so it states them; the project's values (owner, gate command, worktree layout, approvals) still live in the project's `docs/agents/` files.
- Durable, human-gated work (Spec → Tech Design, with format + reviewer gates) runs through the `workflow` plugin into `.workflow/<yyyy-mm-dd>-<slug>/`. There is no repo-wide workspace to initialize.
