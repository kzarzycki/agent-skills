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
- `overlays/skills/setup-engineering-workflow-for-apm/` (canonical source,
  reproduced at `skills/setup-engineering-workflow-for-apm/`)

`skills/setup-engineering-workflow-for-apm/` is generated from the owned
overlay. All imported skill paths are generated from `upstream.yml`,
`vendir.yml`, `vendir.lock.yml`, the patch series, and `provenance.yml`.

Edit owned skills and overlays at their canonical source. Change imported
skills through vendoring policy or patches, then run `mise run
vendor-engineering`. Never hand-edit a generated imported path or overlay
destination.

Before every commit that changes this package, run
`mise run vendor-engineering-check`. Also run
`mise run test-engineering-package` and validate both JSON manifests when
package metadata changes.
