# kzarzycki-agent-skills

A marketplace of Claude Code plugins. Each local plugin is a top-level directory with a `.claude-plugin/plugin.json`; every plugin, local or upstream-sourced, is registered in `.claude-plugin/marketplace.json`.

## Layout

- **Local plugins** — `workflow`, `research`, `engineering`, `content`, `playwright`, `experimental`, `utilities`. Each holds `skills/`, and where relevant `agents/`, `commands/`, `contracts/`, `workflows/`.
- **Upstream plugins** — tracked from GitHub with no local copy, registered in `marketplace.json` via a `source` ref: `google-workspace`, `mattpocock-skills`, `dagu`, `project-templates`.
- **Imported engineering skills** — generated leaves declared by `engineering/vendir.yml` and reproduced from `engineering/vendir.lock.yml`, `engineering/patches/`, and `engineering/provenance.yml`. Change those inputs and run `mise run vendor-engineering`; do not edit imported leaves directly. Follow `engineering/CLAUDE.md` for package-specific rules when present.
- `_attic/` — archived obsolete code, kept out of the live plugins so it stops competing in skill listings. Not loaded. See `_attic/README.md`.
- `omp-workflow/` — a separate sibling runtime. The `workflow` plugin is the reference; never let omp-workflow's conventions or state leak in.
- `evals/`, `docs/` — pipeline evals and design notes.

## Conventions

- A plugin's own `CLAUDE.md` (e.g. `workflow/CLAUDE.md`) is authoritative for that plugin — read it before working there.
- Marketplace descriptions stay plugin-level; individual skills self-describe once a plugin is installed.
- Durable, human-gated work (Spec → Tech Design, with format + reviewer gates) runs through the `workflow` plugin into `.workflow/<yyyy-mm-dd>-<slug>/`. There is no repo-wide workspace to initialize.
