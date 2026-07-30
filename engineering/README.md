# Engineering capability pack

Project-scoped engineering workflows for coding agents. The package combines
reviewed upstream skills with three repository-owned skills and ships the same
skill inventory to Claude Code and Codex.

## Install with APM

APM is the project installer. Add one dependency to the consuming repository:

```yaml
dependencies:
  apm:
    - git: kzarzycki/agent-skills/engineering
      ref: ^0.2.0
```

Then run:

```sh
apm install
apm compile --validate
apm audit --ci --no-policy
```

The Claude adapter writes skills to `.claude/skills/`. The Codex adapter writes
the same inventory to `.agents/skills/`. Those paths are generated; edit the
package sources under `engineering/skills/`.

The independently versioned release tag is `engineering-v0.2.0`. APM resolves
the consumer constraint against package-prefixed tags and records the selected
tag and commit in `apm.lock.yaml`.

## Install from the Claude marketplace

The native Claude plugin remains available as
`engineering@kzarzycki-agent-skills`. Its marketplace source is
`./engineering`.

The former floating `mattpocock-skills` marketplace entry was removed. The
engineering package now supplies reviewed, pinned upstream material through its
own release instead of installing the upstream `main` branch directly.

## Package maintenance

Imported skill directories under `engineering/skills/` are generated from
`vendir.yml`, the locked source in `vendir.lock.yml`, the ordered patches under
`patches/`, and `provenance.yml`. Refresh them with:

```sh
mise run vendor-engineering
```

The owned sibling directories are:

- `skills/audit-third-party-software/`
- `skills/context-extractor/`
- `skills/operating-omnigent/`

`skills/setup-engineering-workflow-for-apm/` is imported and patched locally.
Do not edit generated imported files directly. Before committing package
changes, reproduce the locked import and run its checks:

```sh
mise run vendor-engineering-check
mise run test-engineering-package
```
