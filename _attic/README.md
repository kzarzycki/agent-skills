# Attic

Archived, obsolete code kept out of the live plugins so it stops appearing in skill
listings and competing with current paths. Not loaded; not maintained.

- `workflow/flow` — superseded by the `workflow:workflow` engine + `phase-loop.js`. Used the
  old `.work/` layout and a module split that no longer exists.
- `workflow/product-discovery` — a second discovery pipeline that overlapped the Spec phase
  (different rework cap, reviewer model, and artifact contract). Removed to keep the workflow
  plugin unambiguous: one Spec pipeline. Its clean-slate writing discipline now lives in
  `workflow/skills/spec` and `workflow/skills/tech-design`.
- `workflow/autopilot` — a second, autonomous brainstorm→PR pipeline on the old `.work/`
  layout, parallel to the gated `workflow:workflow` engine (`.workflow/`). Archived to leave
  one pipeline; the plan→build→PR half it covered is future work on the engine, not a
  separate entry point.
- `workflow/commands/init.md`, `workflow/commands/quick.md` — Flow `.work/`-workspace
  commands (bootstrap + quick-mode). Orphaned once autopilot/flow left. `/status` and
  `/research` survived, migrated to the engine's `.workflow/` layout + `research-brief`.
