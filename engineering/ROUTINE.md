# Engineering maintenance routine

Unattended, on a schedule: bring upstream `mattpocock/skills` changes into the
tuned package, release them as `engineering-vX.Y.Z`, and land everything without
a human. The tuning contract is in [CLAUDE.md](CLAUDE.md); read it first.

Setup: `git fetch origin --tags`, then `uv sync --frozen`. The tools in `mise.toml`
must be on `PATH` at their pinned versions; run `mise install` only for those missing
(a host setup script may provide them). The credentials must be able to push
branches and tags to `kzarzycki/agent-skills`, merge its PRs and open issues. A tag pushed with GitHub Actions' own
`GITHUB_TOKEN` starts no workflow, so push with a user or App credential.

## 1. Finish earlier work

In order, and start nothing new while any of these is open:

- **Blocked:** an open `engineering-routine:blocked` issue means a person has to
  act. Stop; closing the issue resumes the routine.
- **Unreleased version on main:** if `engineering/apm.yml` on `origin/main` is newer
  than the newest `engineering-v*` tag, tag the main commit that set it as in step 7.3,
  and stop. Find it with
  `git log -1 --first-parent --format=%H -G'^version:' origin/main -- engineering/apm.yml`.
- **Tag check:** the newest tag's `Engineering tag check` run
  (`gh run list --workflow engineering-tag-check.yml`) still running means stop until
  the next run; failed, or missing for a tag older than an hour, means blocked.
- **Open consumer sync:** if the `automation/engineering-consumer-sync` PR (the tag
  check's bump of this repository's own APM ref) is open, bring it up to date with
  main, wait for its checks, mark it ready and squash-merge it. Its checklist commands
  already ran in its CI.
- **Open routine PR:** if a PR from an `engineering-upstream/*` branch is open, draft or
  not, check it out and carry it on from step 4.

## 2. Intake

From a fresh `origin/main`, run `mise run vendor-engineering` and branch on its
exit code:

- **0 with a clean `git status`:** upstream has nothing new. Stop.
- **0 with changes:** go to step 3.
- **5:** upstream changed tuned skills.
  - For each `artifacts/engineering-deltas/deltas/<skill>.diff`, port the intent into
    `overlays/skills/<skill>/` in the tuned style.
  - Decline instead when the change only restates what the model already does, or
    contradicts a tuning decision.
  - Record each decision in `upstream-intake.yml`: the new commit (the second in the
    stop message's `old..new`), and a one-line note on what you took or why not.
  - Rerun until it exits 0.
- **An added skill in the summary** ships untuned. Tune it:
  - copy it to `overlays/skills/<name>/` and rewrite it;
  - add its `owned_overlays` entry;
  - rerun.
- **2 or 4, when your own edit caused it** (a malformed ledger row, package tests broken
  by a rewrite): fix it and rerun.
- **3** (upstream removed or renamed a skill, changed its licence, or collides with an
  owned skill), **or anything you can't fix:** blocked.

A rerun follows upstream `main`, so it may move the lock further. New deltas go
through this step again.

## 3. Branch

Create the branch `engineering-upstream/<new upstream short sha>` (the name stays if
the lock moves later), commit everything, new files included, push it, and open a draft
PR, so step 1 resumes an interrupted or blocked run. From here on, every change is a
commit that is pushed. A change to an overlay is followed by a rerun of
`mise run vendor-engineering`, and the rerun's output is committed too.

## 4. Gates

With a clean `git status`, these all exit 0: `mise run vendor-engineering-check`,
`mise run test`, `mise run test-engineering-package`, and
`git diff --check origin/main...HEAD`.

## 5. Independent verification

A reviewer with a fresh context that did not write the ports (a subagent or a
separate session) gets:

- the deltas for the whole range: in a clone of upstream, `git diff <old>..<new> --
  <source_path>` for each tuned skill, with `old` and `new` the `source_commit` in
  `engineering/provenance.yml` on main and on the branch, and `source_path` from its
  `source_mappings`;
- `git diff origin/main...HEAD -- engineering/`;
- CLAUDE.md.

It checks each delta: its intent is carried, or the decline is sound. No load-bearing
rule is lost from any changed skill, and the ledger rows match. It answers PASS or
NEEDS REVISION, with file:line findings.

For each fix: commit it, rerun the intake, rerun the gates, then have the reviewer
review again. If it still isn't PASS after two revisions, you're blocked.

## 6. Release or not

Decide after the last rerun, from `git diff --quiet origin/main...HEAD -- engineering/skills/`:

- **Skills changed:** a release. The tool already set the version, one bump past the
  newest `engineering-v*` tag (minor when a skill was added). Give that version a
  `CHANGELOG.md` entry, or extend its entry if one exists, with the upstream range,
  each ported or declined delta in one line, and any newly tuned skill, and move the
  `changelog.d/` entries under it ([changelog.d/README.md](changelog.d/README.md)).
- **Skills unchanged** (every delta declined, or upstream touched only files outside
  the package): no release. Restore `engineering/apm.yml`,
  `engineering/.claude-plugin/plugin.json` and `engineering/tests/consumer/apm.yml`
  from `origin/main`.

Commit, push and rerun the gates.

## 7. Land and tag

1. Write the PR body and mark the PR ready. The body holds:
   - the upstream range;
   - each delta's commit subjects and the decision taken;
   - the reviewer's verdict;
   - the gate exit codes.
2. When the required `qualify` check passes, run `gh pr merge --squash --delete-branch`.
   If it fails, fix, commit and go back to step 4; a third failure is blocked. If main
   moved, update the branch and wait again. Never use `--admin`, and never push to main.
3. For a release, the pre-tag smoke run is a required step: check the gatekeeper against real github.com first. The in-repo job
   `Gatekeeper on real GitHub` runs on every PR that changes the engineering-loop scripts. The one
   place a private organization repository's `github.token` shows (GraphQL `FORBIDDEN`) is the
   smoke run: run the `workflow_dispatch` workflow below in a private organization repository with
   the release head as its `ref`, and wait for it to pass. `release-check engineering <tag>`
   refuses to pass until a passing run for `git rev-parse HEAD` exists. The repository comes from
   the releaser's own environment, never from this repository: `RELEASE_SMOKE_REPOSITORY`
   (`owner/name`) and `RELEASE_SMOKE_WORKFLOW` (the workflow file). Put the run's URL, which
   `release-check` prints, in the release PR's evidence. The tag check in CI passes `--skip-smoke` and prints that it skipped: its token can't dispatch a workflow in another organization's private repository, so the run before the tag is the gate (a private repository's name stays out of
   public text).

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
             set +e  # a verdict that is not go exits 1 or 3; only a gh error fails
             out=$(uv run "$RUNNER_TEMP/gatekeeper/engineering/skills/engineering-loop/scripts/approvals.py" check merge "$PR" 2>&1)
             printf '%s\n' "$out"
             ! printf '%s\n' "$out" | grep -q '^gh: '
   ```

   Before the tag, on the commit that gets tagged (the squash commit on main, which is the smoke `ref`), run
   `uv run python -m tools.capability_pack.cli release-check engineering engineering-vX.Y.Z`.

   Then tag the merge commit and push the tag:
   `git tag -a engineering-vX.Y.Z -m engineering-vX.Y.Z <merge sha> && git push origin engineering-vX.Y.Z`.
   The tag check re-qualifies the release and opens the consumer-sync PR, which step 1
   of the next run merges.

## Blocked

Push the branch if there is one, then open or update one issue labelled
`engineering-routine:blocked`, creating the label if it's missing. Include:

- what stopped the run;
- the command output;
- the upstream range and the branch.

Merge and tag nothing. Every later run stops at step 1 until a person closes the issue.
