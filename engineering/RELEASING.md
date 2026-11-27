# Releasing the packages

An entry may end with an `adopt:` part: what a consumer changes, with the file and the exact edit. The cut folds those into an `### Adopt in projects` list in the version's section, and `cut-release --dry-run` prints the folded section without writing. No such list means no consumer needs a lead.

A release moves each package's entries in `changelog.d/` under a version heading in its `CHANGELOG.md` (see
[changelog.d/README.md](changelog.d/README.md)), sets its version, and tags it. One release cuts every package
with pending entries in one PR and one commit, and each package keeps its own tag, `<package>-vX.Y.Z`, since
consumers pin each package separately (#1861).

## Two release lines

Each package has two, with no one asking for a release (#2678):

- **`next`**, `<package>-vX.Y.Z-next`, after every tested merge. When a push run of the CI workflow on main goes
  green and a merge-queue batch tested its tree (`nightly.py moved push` names the batch), `release.yml`'s `gate`
  lets `cut` fold every package's `changelog.d/` as below. No entries is `nothing to release` (a green run, no PR);
  while a `release/` PR is open no second one opens. A commit that reached main with no tested batch releases
  nothing, and the step summary says why. The tag step pushes the `-next` tag on the release PR's squash commit.
- **`stable`**, `<package>-vX.Y.Z`, promoted by a green nightly. When a scheduled run of the CI workflow on main
  is green and ran the full suite (a run that skipped because main had not moved promotes nothing), `promote` tags,
  for each package, the newest `-next` commit that run covered (its commit or an ancestor) as `<package>-vX.Y.Z`,
  on that same commit: no rebuild, no second fold, so stable ships the tree the nightly tested. Older `next`
  versions in between are skipped. A red nightly promotes nothing; a rerun of it that turns green does. Stable
  tags start the tag check and the consumer-sync PR; `-next` tags start neither. Consumers pin stable
  (`^<package>-v(\d+\.\d+\.\d+)$` never matches a `-next` tag).

A project picks its line with one `extends` entry in its Renovate config, and the preset holds the regex for the pack
pin in `apm.yml` (`- git: owner/repo/<package>` followed by `ref: <package>-vX.Y.Z[-next]`), so a change to the tag
format reaches every project through the preset (#2766):

- `github>kzarzycki/agent-skills//renovate/stable` follows `<package>-vX.Y.Z` only: the commits a green nightly
  tested in full. A pin on a `-next` tag is not matched, so the project moves to a stable tag by hand once.
- `github>kzarzycki/agent-skills//renovate/next` follows `<package>-vX.Y.Z-next` as well: Renovate orders
  `0.35.13-next` above `0.35.12`, below `0.35.13`, and proposes the newest, so a project on it gets each tested merge.
  A `-next` tag has had the merge's test selection (the queue batch's), not the full nightly suite.

A release by a lead on request is replaced by these two lines. `workflow_dispatch` stays for a minor bump
(`-f magnitude=minor`) or a rerun of a cut.

## What a cut does

`gh workflow run release.yml` (add `-f magnitude=minor` for a minor release; the default is patch) runs the same cut
as a merge does, with no agent:

1. It runs `uv run python -m tools.capability_pack.cli cut-release --magnitude <patch|minor>`, which folds every
   package's entries in issue order under `## X.Y.Z - <date>` (or extends that heading when it is already there),
   deletes them, and sets X.Y.Z in `apm.yml`, `.claude-plugin/plugin.json` and the package's `ref: ^X.Y.Z` pins in
   its README and `tests/consumer/apm.yml`. X.Y.Z is the package's last tag moved by the magnitude, or `apm.yml`'s
   version when an update already moved it further. A package with no entries is left alone; no entries anywhere
   ends the run with `nothing to release`.
2. It commits that tree on a `release/<run id>` branch and opens the PR with `loop:queued` and the `land` status,
   so the Mergify queue takes it. The PR's `qualify` runs `cli release-verify`, which reruns the fold on the PR's
   branch point and fails unless the PR's tree is identical: a hand edit beyond the fold fails the gate. Since
   nothing in it is a hand edit, a release PR is risk low and needs no verifier (`bot.release` in
   `docs/agents/gatekeeper.md`).
3. When the squash commit reaches main, it creates every released package's `-next` tag on that commit, runs
   `release-check <package> <tag>` for each, and pushes them all in one push. `release-check` passes a commit that
   releases several packages when every manifest the commit changes is tagged on it, and refuses one that changes
   a manifest it doesn't tag. Each stable `engineering-v*` tag (not `-next`) starts the tag check, which re-qualifies the release and
   opens the consumer-sync PR. It skips `test` and `test-slow` when a green nightly already ran the tagged commit,
   since the nightly's `mise run check` runs those two (#2264); the release check, the vendor check and the package
   gate run on every tag.

The workflow pushes with the `RELEASE_TOKEN` secret, a token that can push branches and tags and open PRs here: a
PR or tag pushed with the workflow's own token starts no workflow, so neither the PR's `qualify` nor the tag check
would run. A person can run the same fold by hand: `cli cut-release` (`--dry-run` prints the releases and writes
nothing), commit its tree on a `release/` branch and open the PR.

## Check the gatekeeper against real github.com, before the tag

This pre-tag smoke run is off: no private organization repository hosts its workflow yet, so `release-check` prints `smoke run: off (RELEASE_SMOKE_REPOSITORY unset)` and passes without it (#1855). Setting the two variables below turns it back on, and then it is a required step. The in-repo job
`Gatekeeper on real GitHub` runs on every PR that changes the engineering-loop scripts. The one
place a private organization repository's `github.token` shows (GraphQL `FORBIDDEN`) is the
smoke run: run the `workflow_dispatch` workflow below in a private organization repository with
the release's squash commit on main as its `ref` (the full 40-character sha), and wait for it to pass.
That is the commit that gets tagged, and its tree is exactly what ships; the release PR's head can
differ from it when main moved. With the variables set, `release-check engineering <tag>`, run on that commit, refuses to
pass until a passing run for `git rev-parse HEAD` exists. The repository comes from
the releaser's own environment, never from this repository: `RELEASE_SMOKE_REPOSITORY`
(`owner/name`) and `RELEASE_SMOKE_WORKFLOW` (the workflow file). Put the run's URL, which
`release-check` prints, in the release PR's evidence. The tag check in CI passes `--skip-smoke` and prints that it skipped: its token can't dispatch a workflow in another organization's private repository, so the run before the tag is the gate (a private repository's name stays out of
public text).

The workflow passes only when `check merge` printed its verdict line (`PR #<n>: risk: ...; merge: ...`) and no `gh:` line:
a refusal before any read (a `pr` into a non-default base, a repository without the loop's files) has no `gh:` line and
would otherwise pass. The in-repo job reads its output the same way.

```yaml
name: Gatekeeper smoke
run-name: Gatekeeper smoke ${{ inputs.ref }}  # release-check matches the head sha here
on:
  workflow_dispatch:
    inputs:
      ref: {description: "agent-skills commit to check", required: true}
      pr: {description: "an open PR of this repository", required: true}
permissions: {contents: read, issues: write, pull-requests: write, checks: read, actions: read, statuses: write}
jobs:
  smoke:
    runs-on: ubuntu-latest
    strategy: {fail-fast: false, matrix: {rest_only: ["0", "1"]}}
    steps:
      - uses: actions/checkout@<pinned sha>  # this repository, at the PR's base: check merge refuses any other commit
        with: {ref: "${{ github.event.repository.default_branch }}", persist-credentials: false}
      - uses: actions/checkout@<pinned sha>
        with: {repository: kzarzycki/agent-skills, ref: "${{ inputs.ref }}", path: gatekeeper, persist-credentials: false}
      - uses: jdx/mise-action@<pinned sha>
        with: {install_args: uv}
      - run: mv gatekeeper "$RUNNER_TEMP/gatekeeper"  # outside the checkout, so the base's drift check leaves it be
      - env: {GH_TOKEN: "${{ github.token }}", GATEKEEPER_REST_ONLY: "${{ matrix.rest_only }}", PR: "${{ inputs.pr }}"}
        run: |
          set +e  # a verdict that is not go exits 1 or 3; a gh error or no verdict line fails
          out=$(uv run "$RUNNER_TEMP/gatekeeper/gatekeeper/skills/gatekeeper/scripts/approvals.py" check merge "$PR" 2>&1)
          printf '%s\n' "$out"
          ! printf '%s\n' "$out" | grep -q '^gh: ' && printf '%s\n' "$out" | grep -q "^PR #$PR: risk: .*; merge: "
```

The release workflow runs this smoke run itself before it tags an engineering release once the releaser sets the
`RELEASE_SMOKE_REPOSITORY` secret; until then it prints `smoke run: off` and tags without it, as `release-check`
does. With it set, three more secrets are required: `RELEASE_SMOKE_WORKFLOW` as above, `RELEASE_SMOKE_PR` (the `pr`
input) and `RELEASE_SMOKE_TOKEN` (a token that can dispatch and read that workflow). It dispatches the workflow with
the squash commit as its `ref`, waits for it to pass, and tags nothing when it fails or one of them is missing.

By hand, before the tag, on the commit that gets tagged (the squash commit on main, which is the smoke `ref`), run
`uv run python -m tools.capability_pack.cli release-check engineering engineering-vX.Y.Z`.
Then tag every package the commit releases and push the tags in one push, so each `release-check` finds the
others: `git tag -a <package>-vX.Y.Z -m <package>-vX.Y.Z <merge sha>` for each, then
`git push origin <tag> <tag> ...`.
