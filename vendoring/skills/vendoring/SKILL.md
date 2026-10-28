---
name: vendoring
description: Pull skills from an upstream repo into a capability pack by a vendir lock, keep your own overlays over them, prove the result reproduces from the lock, and release it with a package-scoped tag. Use when updating or checking a vendored pack (mise run vendor-engineering, vendor-engineering-check), porting an upstream change into a tuned skill, or running the pack's maintenance routine.
metadata:
  requires: "uv vendir apm gh"
---

# Vendoring

A capability pack (here `engineering/`) ships skills it does not write. vendir copies
them from an upstream repo at the commit in the pack's lock, and the pack replaces or
patches each one it tunes. Nothing generated is edited by hand: the tool rebuilds the
generated skills from the pack's inputs, so a check can prove the committed files are
exactly what the lock and the overlays produce.

## A pack's inputs

Paths are relative to the pack's folder.

- `vendir.yml` and `vendir.lock.yml`: which upstream folders land under `skills/`, and the
  commit they come from.
- `upstream.yml`: the upstream repo and tracked ref, the skills the pack writes itself
  (`owned_skills`), each tuned skill's overlay (`owned_overlays`, a folder under
  `overlays/skills/` that replaces the upstream text whole), substitutions for an untuned
  skill, and exclusions.
- `provenance.yml`: written by the tool. The upstream commit and the hash of every
  imported and overlaid file, so an upstream change under a tuned skill stays visible
  though its text no longer ships.
- `upstream-intake.yml`: one row per upstream change to a tuned skill, ported or declined,
  against the commit the lock moves to.

## The tool

`scripts/capability_pack/` is a Python package (3.14, with PyYAML). Run it from the
repository root with this skill's `scripts/` folder on `PYTHONPATH`; the mise tasks set it:

```sh
PYTHONPATH=<this skill>/scripts uv run python -m capability_pack.cli check engineering
```

| Command | Does |
|---|---|
| `check <pack>` | rebuilds the pack from its lock in a staging copy and fails on any difference; `mise run vendor-engineering-check` |
| `update <pack>` | moves the lock to upstream's tracked ref, rebuilds, bumps the version when a shipped skill changed; `mise run vendor-engineering` |
| `release-check <pack> <tag>` | the tag is `<pack>-vX.Y.Z` with the version both manifests declare, and the tagged commit changes no other package's manifest |
| `prepare-consumer`, `assert-codex-inventory`, `reconcile-draft-pr` | the consumer-sync workflow's steps: bump this repo's own APM ref to a released tag and open its draft PR |

Exit codes:

- `0`: qualified (for `update`, with or without changes to commit).
- `2`: a configuration error in the pack's inputs.
- `3`: breaking drift: upstream removed or renamed a skill, changed its licence, or
  collides with an owned skill.
- `4`: qualification failed (a patch, a test, a command).
- `5`: upstream changed a tuned skill. Each delta is saved to
  `artifacts/<pack>-deltas/deltas/<skill>.diff` beside the pack; port or decline it,
  record the decision in `upstream-intake.yml` and rerun.

<!-- ponytail: the tool still names the engineering pack's upstream and its policy in places; a second pack generalises them -->

## Maintenance routine

[ROUTINE.md](ROUTINE.md) is the engineering pack's full intake-to-release procedure, meant
for an agent host on a schedule: finish earlier work, intake, branch, gates, an
independent review of every port, release or not, land and tag. A manual intake follows it
too.
