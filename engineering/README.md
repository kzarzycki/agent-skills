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
      ref: ^0.8.2
```

Then run:

```sh
apm install
apm compile --validate
apm audit --ci --no-policy
```

The Claude adapter writes skills to `.claude/skills/`. The Codex adapter writes
the same inventory to `.agents/skills/`. Those paths are generated; edit the
package sources: tuned skills under `engineering/overlays/skills/`, owned skills
under `engineering/skills/`.

## Turn on the engineering loop

The `engineering-loop` skill runs every change as intent, spec, build, gates,
proof, an independent verifier and landing. A project turns it on with one line
in its `AGENTS.md`, for example "Every change that lands as a PR runs the
`engineering-loop` skill", and states its own facts in files it owns:

- `mise run check`: the gate, which CI runs too;
- `mise run gate <build|merge> [pr]`: the proof gate, `scripts/gate.py check`
  plus the project's own checks, run by the loop, a pre-push hook and CI;
- `docs/agents/loop.md`: the owner, how to prove a change, acceptance
  references, the skill for each stage it changes, where a person must approve
  too, the worktree command, the ledger path;
- `docs/agents/issue-tracker.md`: the line `Tracker: GitHub (engineering-loop's
  github.md)`, its components, what must never reach the tracker;
- `docs/agents/coding-standards.md`: the domain's facts.

Each developer picks how agents run with one line in their personal
instructions, `Orchestration backend: <native|omnigent|herdr-link>`; no line
means native subagents. The verifier comes from the other model family when its
CLI is installed; otherwise the PR body says `verifier: same family`.

The independently versioned release tag is `engineering-v0.8.2`. APM resolves
the consumer constraint against package-prefixed tags and records the selected
tag and commit in `apm.lock.yaml`.

## Changing a skill for one repo

Take the first rung that holds:

1. **Fill a fact** in the repo's `docs/agents/` files.
2. **Extend:** a project skill under `.apm/skills/` with a different name that
   says "follow `<skill>` with these differences". It keeps receiving pack fixes.
3. **Fork: not supported yet.** A same-name copy in `.apm/skills/` replaces
   the pack's skill, but on APM 0.30.0 no setup passes `mise run agent-sync`
   reliably. Without a `skills:` subset, `apm audit --ci` reports the copy as
   drift. With a subset that leaves the skill out, the copy is removed and
   restored on alternate syncs, so every other sync fails audit. A subset is
   also an allow-list, so skills the pack adds later would not be installed
   until listed. Declarative overrides are proposed upstream in
   [microsoft/apm#2413](https://github.com/microsoft/apm/issues/2413); until
   then, extend instead or change the pack.
4. **Change the pack** upstream, here.

## Install from the Claude marketplace

The native Claude plugin remains available as
`engineering@kzarzycki-agent-skills`. Its marketplace source is
`./engineering`.

The former floating `mattpocock-skills` marketplace entry was removed. The
engineering package now supplies reviewed, pinned upstream material through its
own release instead of installing the upstream `main` branch directly.

## Package maintenance

Three kinds of source ship under `engineering/skills/`:

- Owned skills, edited in place: `audit-third-party-software`,
  `context-extractor`, `engineering-loop`, `operating-omnigent`.
- Owned overlays under `overlays/skills/<name>/`, reproduced into
  `skills/<name>/`: every imported skill tuned for current models (listed
  under `owned_overlays` in `upstream.yml`).
- Imported skills not yet tuned, generated from the locked upstream source with
  the `substitutions` in `upstream.yml` applied.

Refresh with:

```sh
mise run vendor-engineering
```

### Tuned skills and upstream intake

A tuned skill keeps only what a strong model would not do unprompted (the
contract is in `CLAUDE.md`), so its text drifts too far from upstream for a
textual patch to survive. The intake still syncs upstream and records its raw
hashes in `provenance.yml`. When upstream changes a tuned skill,
`mise run vendor-engineering` stops with exit 5 and saves each delta, commit
subjects then diff, to `artifacts/engineering-deltas/deltas/<skill>.diff`. The
maintenance routine ports the intent or declines it and records the decision in
`upstream-intake.yml`. A row counts only for the commit the lock moves to, so the
next upstream change to a tuned skill stops the intake again. An upstream
deletion of a tuned skill fails the intake outright.

To retire a skill, remove its `vendir.yml` entry and, for a tuned one, its
overlay directory and `owned_overlays` entry, then run the refresh: it prunes
the generated leaf and proposes a minor version.

### Upstream beta skills

`claude-handoff` and `loop-me` come from upstream's
`in-progress` bucket rather than `engineering`. Upstream excludes that bucket
from its own plugin and reserves the right to change or delete those skills
without warning, so treat them as beta.

### Substitutions

`upstream.yml` carries `substitutions`: literal find/replace rules applied
across the imported inventory. Use one for a rename that upstream rewording
would otherwise keep breaking. A rule that matches nothing fails the intake,
so a literal disappearing upstream stays visible.

Do not edit generated files directly. Before committing package changes,
reproduce the locked import and run its checks:

```sh
mise run vendor-engineering-check
mise run test-engineering-package
```

## Maintenance routine

[ROUTINE.md](ROUTINE.md) keeps the package current when an agent host runs it on a
schedule. No schedule is configured yet. Each run:

- It pulls upstream `main`, ports or declines each change to a tuned skill, and
  tunes any new upstream skill.
- A reviewer with a fresh context checks every port before anything lands.
- It merges its own PR once the required `qualify` check passes and, when a shipped
  skill changed, tags `engineering-vX.Y.Z`. The tag check re-qualifies the release, and the
  consumer-sync workflow opens a PR bumping this repository's own APM ref, which
  the next run merges.
- It stops and opens an `engineering-routine:blocked` issue instead of landing
  when upstream removes a skill, the upstream licence changes, the gates fail, or
  the reviewer still objects after two revisions. Later runs stop until a person
  closes that issue.

To schedule it, point an agent host at this repository with the prompt "Run the
maintenance routine in `engineering/ROUTINE.md`." The host needs:

- `mise`, with network access to the tools it installs (Python, Node, uv, `vendir`,
  `apm`) and to PyPI;
- `git` and `gh` credentials that can push branches and tags, merge PRs and open
  issues here.

A tag pushed with GitHub Actions' own `GITHUB_TOKEN` starts no workflow, so the tag
check needs a user or App credential. A claude.ai cloud session's GitHub proxy may
allow pushes only to the session's working branch, which would refuse the tag push.
One manual run that pushes a throwaway tag settles it.

Consumer sync uses the GitHub App credentials in the
`engineering-updater-publish` environment (`UPDATER_APP_ID`,
`UPDATER_APP_PRIVATE_KEY`). The App is installed only on this repository, with
metadata read, contents write and pull requests write.
