# Releasing the engineering package

A release is a PR that moves the entries in `changelog.d/` under a version heading in `CHANGELOG.md` (see
[changelog.d/README.md](changelog.d/README.md)), then a tag. Whoever cuts it, a person or the routine in
[ROUTINE.md](ROUTINE.md), follows this page.

## Check the gatekeeper against real github.com, before the tag

This pre-tag smoke run is a required step. The in-repo job
`Gatekeeper on real GitHub` runs on every PR that changes the engineering-loop scripts. The one
place a private organization repository's `github.token` shows (GraphQL `FORBIDDEN`) is the
smoke run: run the `workflow_dispatch` workflow below in a private organization repository with
the release's squash commit on main as its `ref` (the full 40-character sha), and wait for it to pass.
That is the commit that gets tagged, and its tree is exactly what ships; the release PR's head can
differ from it when main moved. `release-check engineering <tag>`, run on that commit, refuses to
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

Before the tag, on the commit that gets tagged (the squash commit on main, which is the smoke `ref`), run
`uv run python -m tools.capability_pack.cli release-check engineering engineering-vX.Y.Z`.

Then tag the merge commit and push the tag:
`git tag -a engineering-vX.Y.Z -m engineering-vX.Y.Z <merge sha> && git push origin engineering-vX.Y.Z`.
The tag check re-qualifies the release and opens the consumer-sync PR, which step 1
of the next run merges.
