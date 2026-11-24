# Changelog

## Unreleased

New entries are files in [changelog.d/](changelog.d/), one per issue, until a release moves
them here.

## 0.1.5 - 2026-11-24

- loop: R6 states what the merge queue runs: the `select.unkeyed` checks and the cross-change tests, plus the affected tests of a PR with no record of the `Affected tests:` command for its tree (the floor), a refusal when a merge would have neither (the batch check, and the local queue's `land` on a head with no pass record), the fallback to the entry's affected tests without a per-test map, and batching from gatekeeper.md's `land` block (#2178). worker.md names the worker's final-head `affected-tests --record` as its one recorded test run, which the floor reads (#2178).

## 0.1.4 - 2026-11-24

- loop: lead.md says `land <pr> --wait` on a GitHub-queue or Mergify base waits until the queue merges the PR or takes it out, so a lead no longer polls the PR itself (#2101).
- engineering-loop: a test set never runs again on a tree it passed on (#2140, R1). The push hook's affected-test run is the worker's one run; the worker makes the one acceptance run through `local-ci --record` and the verifier reads that record by tree; a ready PR's CI reads the pass record of the head's tree (`tools/pr_head_record.py`), skips its checks when one exists, says which, and still reports success.
- loop: lead.md says a lead holds a PR it must not land with `loop:hold` and a PR comment naming who holds it and why, and removes the label before landing; `loop:dequeued` is no hold (#2162).
- loop: lead.md step 1 says a lead asks the owner its own questions on its own question card (`sys_ask_user_question`), acts only on an `answered` read, and ends `USER NEEDED` with the card open; a question that spans projects goes to the session that started it with no card; while the card is open the lead keeps working on its recommended answer, holding back only what is hard to undo or reaches outside the project (#2170).
- loop: once the owner approves a spec, plan or merge on the lead's own card (`answered`), the lead records it with `approvals.py approve … --by owner` instead of asking the owner to add the label by hand (#2170).
- engineering-loop: SKILL.md states the rule "a check runs only if it can fail because of the change" once: its two conditions (the inputs match a run that passed, and the check is deterministic), its exceptions and R1–R7. worker.md, verifier.md, lead.md and the Flaky tests bullet point at that section instead of restating the rule (#2174).
- engineering-loop: a fix round runs only what its own diff reaches (R4). The worker selects tests against the last head its run passed on, not the PR's base. The lead calls a proof stale when the round changed its inputs, not when its log names another commit. A verifier's later pass reruns only the acceptance checks and repros the round's diff reaches, plus every repro still `NOT FIXED` (#2176).
- loop: SKILL.md's R5 now reruns a red by cause: a fix since the red reruns the failed tests plus what it reaches, no change reruns the red run's own selection once (a pass there is a flake, red again leaves the queue), never the failed tests alone on an unchanged tree, with `approvals.py rerun-tests` as the verb; the flaky fallback follows it, and the queue and `land` lines name the whole rerun as a gap until #1400 and #1794 land (#2177).
- loop: lead.md's Accept step reads the queue's run for a merge whose tree the queue tested, instead of waiting on a push run that tests nothing; SKILL.md's Nightly runs only when the default branch moved since its last green and otherwise skips with that run's link (R7, #2179).

## 0.1.3 - 2026-11-23

- A known-red test is skipped with its issue linked, never listed as an expected failure: the loop skill (Known-red tests, Nightly) and its verifier say so.
- engineering-loop: the merge model. The worker runs only the tests the PR affects, never the whole suite or a gate of record, and writes the e2e tests the verifier proves the change with; the verifier's review is unchanged and its test run is those e2e tests, with no full suite. Without a merge queue a PR merges on the verifier's satisfied record with no gate step; with one, the PR head gets no CI check and the queue's batch check, the one run on the merged tree, runs only the tests the batch affects. The nightly runs the full suite, and a red nightly becomes an issue, a bisect and a fix or revert PR. A selector that can't tell which tests a change touches runs nothing and says so. SKILL.md gains a Merge model section (#1872).
- engineering-loop: in a Claude cloud VM, the pack's scripts come from a clone of its latest release tag, resolved in the VM at run time, or the tag the brief pins with a `Pack:` line, never the checkout's vendored copy (#1987).

## 0.1.2 - 2026-11-22

- engineering-loop: verifier.md and worker.md wait on a long run with one wake, one harness-tracked background `wait-for --budget <the run's expected length>`, never a short `wait-for`, `until grep` or `sleep` loop, since each return re-reads the whole context (#1790).
- engineering-loop: verifier.md runs the suite, or more than a few test files, only through the project's test task, never a bare `pytest`, and a selection of over half the suite as the whole suite (#1798).
- engineering-loop: lead.md says the lead runs no test suite: the worker's gate and the verifier's runs are the runs of record (#1806).
- engineering-loop: the verifier reads the gatekeeper's record of a command on the head's tree (`gate-record`) instead of running the same tests again, and runs only what has no record. A worker's log or report never stands in for it; mutation and repro probes stay the verifier's own runs (#1822).

## 0.1.1 - 2026-11-22

- loop: `brief` prints the findings the previous verifier pass posted, read from the PR, so a cloud verifier needs no host report file (#1591).
- engineering-loop: lead.md says a lead's own long run (a build, a test, a gate, a land) ends in something that wakes it, a harness-tracked background task, a detached run with `LOOP_NOTIFY` or a `wait-for` in the same turn, never a turn ended on a bare pid, a log or a cloud subagent; a step handed back to the manager goes on a `Handback: #<n> <what>` line (#1753).
- engineering-loop: the public-repo rule bans host names and paths on GitHub but no longer session links or ids, which may stay in commits, PR bodies and comments (#1764).
- engineering-loop: update a PR branch by merging its base in (`git merge origin/<base>`, plain push), never by rebasing or force-pushing it, and never with a replacement PR (#1768).

## 0.1.0 - 2026-11-22

- loop: the first release, split out of `engineering`. It holds the `engineering-loop` skill, under its old name, with its lead, worker and verifier roles, and `scripts/loop.py`, which takes over `brief` (a verifier pass's brief) and `release` (removes the assignee the loop added) from the gatekeeper. It depends on `gatekeeper` and `github`; it gains `engineering` when `engineering` drops its dependency on `loop` (#615).
- engineering-loop: SKILL.md § Settings points at the `gatekeeper` skill's policy.md for each key, since the gatekeeper ships its own policy reference; § Approvals and proof stays. `cloud_verifier.py` and `nightly.py` stay with the loop and read the gatekeeper's `folding.py` and `events.py` through the host's install layout (#615).
- engineering-loop: the script paths engineering 0.25.0 shipped in this skill keep working for this release line: `scripts/approvals.py` and `scripts/gatekeeper.py` run the `gatekeeper` skill's gatekeeper.py (`approvals.py brief` and `release` run `scripts/loop.py`), `scripts/acceptance.py` and `scripts/events.py` the `gatekeeper` skill's, `scripts/board.py`, `scripts/labels.py` and `scripts/rulesets.py` the `github-tracker` skill's, and `scripts/browse.py` the `browsing` skill's, with the same arguments, stdin and exit code, after one deprecation line on stderr naming the new path. They go away with the release that drops `engineering`'s dependencies on the packages split out of it (#615).
- engineering-loop: `approvals.py brief` embeds the PR's title and body verbatim, each in a code fence longer than any backtick run inside it, and lists its labels, so a verifier with no GitHub access (a cloud VM) can check a criterion about the PR text without a `Not run:` line. The linked and closing issues were already in its `Spec:` line (#1697).
- engineering-loop: the repo's committed `.claude/settings.json` sets `attribution.sessionUrl` to `false`, so a cloud session stops being told to add the claude.ai session link to its commits and PR bodies. The footer the cloud GitHub proxy appends has no setting; the gatekeeper's footer regex still strips it (#1708).
- engineering-loop: the gate of record runs once, on the head the verifier is satisfied with, and again on any later head; review heads get only the narrow checks (tests and lint for what changed). A gate failure now shows after the verifier, so its fix needs a short re-verify of the delta, and a fix round runs the narrow checks only, with no gate on a review head (#1715).
