# Engineering package

`engineering/` is an independently versioned capability pack for coding
agents. APM is its project installation contract. The current target adapters
are Claude Code and Codex; keep package names and documentation usable by
future coding-agent adapters.

## Source ownership

The repository owns these skill directories:

- `skills/audit-third-party-software/`
- `skills/context-extractor/`
- `skills/operating-omnigent/`

`skills/setup-engineering-workflow-for-apm/` is imported from Matt Pocock's
engineering collection and modified by the patches listed in
`patches/series`. All other imported skill paths are generated from
`vendir.yml`, `vendir.lock.yml`, the patch series, and `provenance.yml`.

Edit owned skills directly. Change imported skills through vendoring policy or
patches, then run `mise run vendor-engineering`. Never hand-edit a generated
imported path.

Before every commit that changes this package, run
`mise run vendor-engineering-check`. Also run
`mise run test-engineering-package` and validate both JSON manifests when
package metadata changes.
