# Engineering maintenance routine

Unattended, on a schedule: bring upstream `mattpocock/skills` changes into the
tuned package, release them as `engineering-vX.Y.Z`, and land everything without
a human. The tuning contract is in [CLAUDE.md](CLAUDE.md); read it first.

Setup: `git fetch origin --tags`, `mise install`, `uv sync --frozen`. `git` and
`gh` must be able to push branches and tags to `kzarzycki/agent-skills` and merge
its PRs. A tag pushed with GitHub Actions' own `GITHUB_TOKEN` starts no workflow,
so push with a user or App credential.

## 1. Finish earlier work

- An open PR from an `engineering-upstream/*` branch: bring it through step 5
  (fix it if its checks fail), then land and tag it. Start nothing new this run.
- An open `automation/engineering-consumer-sync` PR (the tag check's bump of this
  repository's own APM ref): once its checks pass, mark it ready and squash-merge it.

## 2. Intake

From a fresh `origin/main`, run `mise run vendor-engineering` and branch on its
exit code:

- 0 with a clean `git status`: upstream has nothing new. Stop.
- 0 with changes: go to step 3.
- 5: upstream changed tuned skills. For each `artifacts/engineering-deltas/deltas/<skill>.diff`,
  port the intent into `overlays/skills/<skill>/` in the tuned style, or decline
  it when it restates what the model already does or contradicts a tuning
  decision. Add a row to `upstream-intake.yml` for the commit the stop message
  names, with a one-line note on what you took or why not. Rerun until it exits 0.
- An added skill in the summary ships untuned. Tune it: copy it to
  `overlays/skills/<name>/`, rewrite it, add its `owned_overlays` entry, rerun.
- 3 (upstream removed or renamed a skill), a licence change, or any other
  failure: blocked.

## 3. Release notes

The tool sets the version, one bump past the last `engineering-v*` tag (minor when
a skill was added). Add a `CHANGELOG.md` entry for it: the upstream range, each
ported or declined delta in one line, and any newly tuned skill.

## 4. Gates

`mise run vendor-engineering-check`, `mise run test`,
`mise run test-engineering-package` and `git diff --check` all exit 0.

## 5. Independent verification

A reviewer with a fresh context that did not write the ports (a subagent or a
separate session) gets the deltas, `git diff origin/main -- engineering/`, and
CLAUDE.md. It checks each delta: its intent is carried, or the decline is sound;
no load-bearing rule was lost from any changed skill; the ledger rows match. It
answers PASS or NEEDS REVISION with file:line findings. Fix and re-verify; still
not PASS after two revisions: blocked.

## 6. Land and tag

1. Branch `engineering-upstream/<new upstream short sha>`, commit, push, and open
   a PR: upstream range, per-skill decisions, the verifier's verdict, gate exit codes.
2. When the required `qualify` check passes, `gh pr merge --squash --delete-branch`.
   If main moved, update the branch and wait again. Never `--admin`, never push to main.
3. Tag the merge commit and push the tag:
   `git tag -a engineering-vX.Y.Z -m engineering-vX.Y.Z <merge sha> && git push origin engineering-vX.Y.Z`.
   The tag check re-qualifies the release and opens the consumer-sync PR that
   step 1 of the next run merges.

## Blocked

Open or update one issue labelled `engineering-routine:blocked` (create the
label if missing): what stopped the run, the command output, the upstream range.
Merge and tag nothing. The next run starts again at step 1.
