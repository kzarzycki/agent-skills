# Changelog

## Unreleased

New entries are files in [changelog.d/](changelog.d/), one per issue, until a release moves
them here.

## 0.1.1 - 2026-11-26

- The three hook commands skip a missing script with one stderr line and exit 0, and pass the script's own exit code through. A package move that deletes a script no longer makes a stale hook entry refuse every Bash call; `README.md` says how to clear the entries an upgrade from engineering 0.35.10 or earlier left (#2773).

## 0.1.0 - 2026-11-26

- engineering-hooks: the pack's Claude Code hooks (`hooks/hooks-claude.json` and the guards it runs) move out of `engineering` into this package, whose `apm.yml` says `target: claude`, and `engineering` depends on it, so `engineering` installs on apm 0.36 and later into a project that targets both Claude and Codex (apm 0.36 sends every hook file to every target and refused with "Target 'codex' would newly activate: hooks/hooks-claude.json"). The hooks reach `.claude/` only and every skill still reaches both agents; apm 0.30.0 and 0.33.0 install it the same way, so the minimum apm stays 0.30.0. The deployed hook path moves from `.claude/hooks/engineering/hooks/` to `.claude/hooks/engineering-hooks/hooks/` on the next install (#2683).
