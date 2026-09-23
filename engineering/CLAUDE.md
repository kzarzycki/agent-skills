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

## Tuning contract

A tuned skill carries only what a strong current model would not do unprompted.

- Keep: output formats and templates, gates and stop conditions, safety rules
  (what never gets published, sent or deleted, and what waits for the user),
  exact commands and paths, cross-references to other skills, frontmatter
  (`name`, `description`, `disable-model-invocation`, credits).
- Cut: generic engineering advice, pressure language (CRITICAL, MUST, NEVER in
  capitals), step-by-step choreography for things the model sequences well,
  verification scaffolding, repetition.
- Delegation (subagents, parallel work) is the model's judgment, not a
  requirement.
- Stay harness-neutral (no tool names of one agent) and tracker-neutral
  (`docs/agents/issue-tracker.md` configures the tracker).
- Give every "never" or "must" its reason in the same sentence.

## Upstream intake

vendir still syncs mattpocock/skills at the lock and `provenance.yml` keeps the
raw upstream hashes, so an upstream change under a tuned skill stays visible
though its text no longer ships. When one changes, `mise run vendor-engineering`
exits 5 and saves each delta to `artifacts/engineering-deltas/deltas/<skill>.diff`.
Port or decline it and record the decision in `upstream-intake.yml` against the
commit the lock moves to. [ROUTINE.md](ROUTINE.md) is the full procedure, meant to
run on a schedule; a manual intake follows it too.

## Checks

Before every commit that changes this package, run
`mise run vendor-engineering-check`. Also run
`mise run test-engineering-package` and validate both JSON manifests when
package metadata changes.
