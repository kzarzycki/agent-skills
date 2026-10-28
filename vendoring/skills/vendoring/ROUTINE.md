# Pack maintenance routine

Unattended, on a schedule: bring upstream changes into a pack's tuned skills, release
them, and land everything without a human. Paths are from the repository root, with
`<pack>` the pack's folder. Read the pack's tuning contract (how its overlays are
written) first.

The steps are the method. The project's own instructions give its values, one per slot
below, since branch names, gates and landing differ by project. A slot the project leaves
empty is skipped.

- **Setup**: what a fresh host runs before step 1 (fetch tags, sync the environment, the
  tools that must be on `PATH`) and the credentials it needs.
- **Blocked marker**: where a stop is recorded, so every later run sees it (an issue
  label, a file).
- **Earlier work**: the project's own steps a previous run may have left unfinished (an
  untagged release, a running release check, an open follow-up PR), in order, each with
  what to do.
- **Intake**: the command that runs the tool's `update <pack>`.
- **Branch**: the name of a run's branch.
- **Gates**: the commands that all exit 0 before a PR lands.
- **Landing**: what must pass before a merge, and the merge command.
- **Release**: the changelog step, the version tag, how it is published, and the version
  files a release changes.

## 1. Finish earlier work

In order, and start nothing new while any of these is open:

- **Blocked:** an open blocked marker means a person has to act. Stop; clearing the
  marker resumes the routine.
- **Earlier work:** each of the project's steps, as it states them.
- **Open routine PR:** if a PR from a run's branch is open, draft or not, check it out and
  carry it on from step 4.

## 2. Intake

From a fresh default branch, run the intake command and branch on its exit code:

- **0 with a clean `git status`:** upstream has nothing new. Stop.
- **0 with changes:** go to step 3.
- **5:** upstream changed tuned skills.
  - For each `artifacts/<pack>-deltas/deltas/<skill>.diff`, port the intent into
    `<pack>/overlays/skills/<skill>/` in the tuned style.
  - Decline instead when the change only restates what the model already does, or
    contradicts a tuning decision.
  - Record each decision in `<pack>/upstream-intake.yml`: the new commit (the second in
    the stop message's `old..new`), and a one-line note on what you took or why not.
  - Rerun until it exits 0.
- **An added skill in the summary** ships untuned. Tune it:
  - copy it to `<pack>/overlays/skills/<name>/` and rewrite it;
  - add its `owned_overlays` entry in `<pack>/upstream.yml`;
  - rerun.
- **2 or 4, when your own edit caused it** (a malformed ledger row, package tests broken
  by a rewrite): fix it and rerun.
- **3** (upstream removed or renamed a skill, changed its licence, or collides with an
  owned skill), **or anything you can't fix:** blocked.

A rerun follows the tracked ref, so it may move the lock further. New deltas go through
this step again.

## 3. Branch

Create the run's branch (its name stays if the lock moves later), commit everything, new
files included, push it, and open a draft PR, so step 1 resumes an interrupted or blocked
run. From here on, every change is a commit that is pushed. A change to an overlay is
followed by a rerun of the intake, and the rerun's output is committed too.

## 4. Gates

With a clean `git status`, every gate exits 0.

## 5. Independent verification

A reviewer with a fresh context that did not write the ports (a subagent or a separate
session) gets:

- the deltas for the whole range: in a clone of upstream, `git diff <old>..<new> --
  <source_path>` for each tuned skill, with `old` and `new` the `source_commit` in
  `<pack>/provenance.yml` on the default branch and on the run's branch, and
  `source_path` from its `source_mappings`;
- `git diff <default branch>...HEAD -- <pack>/`;
- the pack's tuning contract.

It checks each delta: its intent is carried, or the decline is sound. No load-bearing
rule is lost from any changed skill, and the ledger rows match. It answers PASS or
NEEDS REVISION, with file:line findings.

For each fix: commit it, rerun the intake, rerun the gates, then have the reviewer
review again. If it still isn't PASS after two revisions, you're blocked.

## 6. Release or not

Decide after the last rerun, from `git diff --quiet <default branch>...HEAD -- <pack>/skills/`:

- **Skills changed:** a release. The tool already set the version, one bump past the
  newest release (minor when a skill was added). Record it as the release slot says, with
  the upstream range, each ported or declined delta in one line, and any newly tuned
  skill.
- **Skills unchanged** (every delta declined, or upstream touched only files outside
  the pack's skills): no release. Restore the release slot's version files from the
  default branch.

Commit, push and rerun the gates.

## 7. Land and tag

1. Write the PR body and mark the PR ready. The body holds:
   - the upstream range;
   - each delta's commit subjects and the decision taken;
   - the reviewer's verdict;
   - the gate exit codes.
2. When the landing slot's checks pass, merge with its command. If they fail, fix,
   commit and go back to step 4; a third failure is blocked. If the default branch
   moved, update the branch and wait again. Never bypass the landing rule (an admin
   merge, a push to the default branch), since no person reviews what an unattended run
   lands.
3. For a release, tag the merge commit and publish the tag as the release slot says.

## Blocked

Push the branch if there is one, then set the blocked marker, or update it if it is
already set, with:

- what stopped the run;
- the command output;
- the upstream range and the branch.

Merge and tag nothing. Every later run stops at step 1 until a person clears it.
