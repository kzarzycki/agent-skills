# Engineering capability pack

Project-scoped engineering workflows for coding agents. The package combines
reviewed upstream skills with repository-owned skills and ships the same
skill inventory to Claude Code and Codex.

## Install with APM

APM is the project installer. Add one dependency to the consuming repository:

```yaml
dependencies:
  apm:
    - git: kzarzycki/agent-skills/engineering
      ref: ^0.3.0
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

The independently versioned release tag is `engineering-v0.3.1`. APM resolves
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
`upstream.yml`, `vendir.yml`, the locked source in `vendir.lock.yml`, the
substitution rules and ordered patches applied in that order, and
`provenance.yml`. Refresh them with:

```sh
mise run vendor-engineering
```

The owned sibling directories are:

- `skills/audit-third-party-software/`
- `skills/context-extractor/`
- `skills/operating-omnigent/`
- `overlays/skills/setup-engineering-workflow-for-apm/`

### Substitutions before patches

`upstream.yml` carries `substitutions`: literal find/replace rules applied
across the imported inventory before the ordered patches run. Use one for a
rename that upstream rewording would otherwise keep breaking; a context diff
fails on any edit near its anchor, a literal rule does not. A rule that matches
nothing fails the refresh, so a literal disappearing upstream stays visible.
Owned skills and the overlay are out of scope. Keep `patches/` for changes that
alter meaning rather than a name.

The setup overlay is canonical and is reproduced into
`skills/setup-engineering-workflow-for-apm/`; the destination is generated.
Do not edit generated imported files directly. Before committing package
changes, reproduce the locked import and run its checks:

```sh
mise run vendor-engineering-check
mise run test-engineering-package
```

## Autonomous upstream intake

`Engineering upstream refresh` selects the highest canonical stable upstream
tag and accepts it only when its peeled commit is a forward move from the lock.
Because the current lock is two commits beyond upstream `v1.2.3`, provenance
records `v1.2.3` as the stable version baseline until the first tagged refresh.
Every run uploads `result.json` and `summary.md`. Qualification and smoke modes
are nonpublishing. A blocked run updates one issue identified by
`engineering-upstream-refresh:blocked`.

Publishing uses only the GitHub App credentials in the protected
`engineering-updater-publish` environment. Configure `UPDATER_APP_ID` and
`UPDATER_APP_PRIVATE_KEY` for an App installed only on this repository with
metadata read, contents write, and pull requests write. Missing credentials
produce a blocked result; the workflow never falls back to `GITHUB_TOKEN` or a
PAT for branch or PR writes.

Rollout order:

1. Leave `ENGINEERING_UPDATER_SCHEDULE_ENABLED` unset or `false`.
2. Run `smoke-fixture`, then the default `qualify` dispatch and retain their
   artifacts.
3. Protect `main`, disable Actions review approval, install the scoped App, and
   run `publish-smoke` with confirmation `PUBLISH-SMOKE`.
4. Verify its draft triggers normal CI and cannot merge or push `main`; close
   the canary manually.
5. Run `publish`, then set the schedule variable to `true`.

Rollback starts by setting that variable to `false`, then removing the publish
environment secrets and revoking the App installation. Qualification and
evidence reporting remain usable.

After a human creates an `engineering-vX.Y.Z` tag and its checks pass, the tag
workflow proposes an exact root APM ref, runs refresh/frozen convergence, and
checks Codex inventory. The consumer PR retains the final local checklist;
automation never tags, merges, approves, or changes a maintainer workstation.
