# Engineering package

`engineering/` is an independently versioned capability pack for coding
agents. APM is its project installation contract. The current target adapters
are Claude Code and Codex; keep package names and documentation usable by
future coding-agent adapters.

## Source ownership

- Owned skills, edited in place: `skills/audit-third-party-software/`,
  `skills/context-extractor/`, `skills/operating-omnigent/`.
- Owned overlays, canonical under `overlays/skills/<name>/` and reproduced into
  `skills/<name>/`: `setup-engineering-workflow-for-apm` and every tuned
  imported skill (listed under `owned_overlays` in `upstream.yml`).
- Everything else under `skills/` is generated from `upstream.yml`,
  `vendir.yml`, `vendir.lock.yml`, the substitutions and `provenance.yml`.

Never hand-edit a generated path. Change an overlay at its source, an untuned
imported skill through a substitution or by tuning it, then run
`mise run vendor-engineering`.

## Tuned skills and upstream intake

Tuned skills are rewritten for current models: only what a strong model would
not do unprompted, no pressure language, delegation left to judgment. vendir
still syncs mattpocock/skills at the lock and `provenance.yml` keeps the raw
upstream hashes, so an upstream change under a tuned skill stays visible even
though its text no longer ships.

When the lock moves and upstream changed under a tuned skill, `mise run
vendor-engineering` exits 5 and the scheduled refresh blocks with
`port_required`. Each pending skill's delta (upstream commit subjects, then the
diff) lands in `artifacts/engineering-deltas/deltas/<skill>.diff`, or in the
refresh run's artifact. For each delta, port its intent into the overlay in the
tuned style, or decline it when it restates what the model already does or
contradicts a tuning decision. Then add a row to `upstream-intake.yml` keyed to the commit the lock moves to
(the one the local stop message names) and rerun. Port locally: the scheduled
refresh rejects overlay edits.
Before the PR, a fresh reviewer checks every delta against the overlay diff and
its ledger row.

A new upstream skill ships as imported until someone tunes it: copy it to
`overlays/skills/<name>/`, rewrite it, and add its `owned_overlays` entry.

## Checks

Before every commit that changes this package, run
`mise run vendor-engineering-check`. Also run
`mise run test-engineering-package` and validate both JSON manifests when
package metadata changes.
