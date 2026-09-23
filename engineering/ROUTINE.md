# Engineering maintenance routine

Unattended, on a schedule: bring upstream `mattpocock/skills` changes into the
tuned package, release them as `engineering-vX.Y.Z`, and land everything without
a human. The tuning contract is in [CLAUDE.md](CLAUDE.md); read it first.

Setup: `git fetch origin --tags`, `mise install`, `uv sync --frozen`. The
credentials must be able to push branches and tags to `kzarzycki/agent-skills`,
merge its PRs and open issues. A tag pushed with GitHub Actions' own
`GITHUB_TOKEN` starts no workflow, so push with a user or App credential.

## 1. Finish earlier work

In order, and start nothing new while any of these is open:

- **Unreleased version on main:** if `engineering/apm.yml` on `origin/main` is newer
  than the newest `engineering-v*` tag, tag the commit that set it (step 7.3).
- **Failed tag check:** if the newest tag's `Engineering tag check` run failed
  (`gh run list --workflow engineering-tag-check.yml`), you're blocked.
- **Open consumer sync:** if the `automation/engineering-consumer-sync` PR (the tag
  check's bump of this repository's own APM ref) is open, bring it up to date with
  main, wait for its checks, mark it ready and squash-merge it. Its checklist commands
  already ran in its CI.
- **Open routine PR:** if a PR from an `engineering-upstream/*` branch is open, carry it
  on from step 4 (fix it if its checks fail), then land it. To see its deltas again,
  diff the old and new lock commits (`vendir.lock.yml` on main and on the branch) in a
  clone of upstream, under each skill's source path.

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
  - Record each decision in `upstream-intake.yml`: the full commit the stop message
    names, and a one-line note on what you took or why not.
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

Create the branch `engineering-upstream/<new upstream short sha>` and commit
everything, new files included. From here on, every fix is a commit, and every fix to
an overlay is followed by a rerun of `mise run vendor-engineering`.

If nothing under `engineering/skills/` changed against `origin/main` (every delta was
declined, or upstream only touched files outside the package):

- restore `engineering/apm.yml`, `engineering/.claude-plugin/plugin.json` and
  `engineering/tests/consumer/apm.yml` from `origin/main`;
- land the lock, provenance and ledger in step 7 without a version, CHANGELOG entry
  or tag.

## 4. Gates

These all exit 0 on the committed branch: `mise run vendor-engineering-check`,
`mise run test`, `mise run test-engineering-package`, and
`git diff --check origin/main...HEAD`.

## 5. Independent verification

A reviewer with a fresh context that did not write the ports (a subagent or a
separate session) gets:

- the deltas;
- `git diff origin/main...HEAD -- engineering/`;
- CLAUDE.md.

It checks each delta: its intent is carried, or the decline is sound. No load-bearing
rule is lost from any changed skill, and the ledger rows match. It answers PASS or
NEEDS REVISION, with file:line findings.

For each fix: commit it, rerun the intake, rerun the gates, then have the reviewer
review again. If it still isn't PASS after two revisions, you're blocked.

## 6. Release notes

Write these after the last rerun, so they describe the final range:

- **Version:** the tool already set it, one bump past the newest `engineering-v*` tag
  (minor when a skill was added).
- **CHANGELOG:** give that version a `CHANGELOG.md` entry, or extend its entry if one
  exists. Include:
  - the upstream range;
  - each ported or declined delta, in one line;
  - any newly tuned skill.

## 7. Land and tag

1. Push the branch and open a PR. The body holds:
   - the upstream range;
   - each delta's commit subjects and the decision taken;
   - the reviewer's verdict;
   - the gate exit codes.
2. When the required `qualify` check passes, run `gh pr merge --squash --delete-branch`.
   If main moved, update the branch and wait again. Never use `--admin`, and never
   push to main.
3. For a release, tag the merge commit and push the tag:
   `git tag -a engineering-vX.Y.Z -m engineering-vX.Y.Z <merge sha> && git push origin engineering-vX.Y.Z`.
   The tag check re-qualifies the release and opens the consumer-sync PR, which step 1
   of the next run merges.

## Blocked

Open or update one issue labelled `engineering-routine:blocked`, creating the label
if it's missing. Include:

- what stopped the run;
- the command output;
- the upstream range.

Merge and tag nothing. The next run starts again at step 1.
