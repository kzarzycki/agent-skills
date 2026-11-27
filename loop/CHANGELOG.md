# Changelog

## Unreleased

New entries are files in [changelog.d/](changelog.d/), one per issue, until a release moves
them here.

## 0.1.17 - 2026-11-27

- `lead.md`'s merge-queue rerun line no longer names #1400 and #1794 as pending, and says a project's queue rerun is narrow only where its own CI calls `rerun-tests` (#2832).

## 0.1.16 - 2026-11-27

- `lead.md`'s Verifier route points to the setup's `verifier:` setting instead of naming Codex as the default and a fixed Gemini model; the fallback rules read in the configured order (#2840).

## 0.1.15 - 2026-11-27

- cloud_verifier: child usage posts to `POST /v1/sessions/{id}/child-usage` on the server `OMNIGENT_SERVER_URL` names (replacing `OMNIGENT_CHILD_USAGE_URL`), with `key`, `harness` and the optional model, token and cost fields, and an `X-Omnigent-Orchestration-Source` header naming the parent; the key is stable per child run, so a retry replaces its entry (#2805).

## 0.1.14 - 2026-11-26

- cloud_verifier: the usage a verifier's `codex` or `agy` prints is posted under its parent session when `OMNIGENT_CHILD_USAGE_URL` is set (#2775).

## 0.1.13 - 2026-11-26

- `cloud_verifier.py verify --harness gemini` now runs the Antigravity CLI (`agy -p`, installed in the VM when missing) instead of the Gemini CLI, on `AGY_OAUTH_JSON` (the base64 of a tar of its two login files, unpacked with mode 0600 and any other tar member refused) in place of `GEMINI_OAUTH_JSON`; with no login it still prints one line and exits 5 (#2756).

## 0.1.12 - 2026-11-26

- `cloud_verifier.py verify --harness gemini` runs the Gemini verifier in the worker's cloud VM on the owner's login (`GEMINI_OAUTH_JSON`), and with no login prints one line and exits 5 so the lead starts a host verifier (#2694).

## 0.1.11 - 2026-11-26

- engineering-loop: SKILL.md says every `land` sweeps the `loop-gate/` record branches, merged by Mergify or a queue too, so a consumer needs no cleanup workflow (#1869).
engineering-loop: a change that can't reach the product runs no product suite (#2175, R2 of #2143). An instructions change's verifier pass runs the `select` checks its layer reaches, and the product's affected tests only for a build input or an unclassified file; PR CI's scope is unchanged here (R1's line stands).
engineering-loop: Adopting the loop gains "Moving a repo onto the rule set" (#2231, part of #2143): the three steps, the `gatekeeper.md` keys a repo states and the table of local copies to delete by kind, so a repo's migration story is a release tag, a config block and one row per deleted file.
engineering-loop: `nightly.py moved tag --nightly <file>` names a consumer's nightly workflow (default `engineering-ci.yml`), and a verb-level test pins that `moved tag` asks for the tagged commit's runs (#2323).
engineering-loop: `affected-tests` always runs `tests/test_one_package_per_skill_name.py`, a sweep of every skill folder that names no script, so a batch can no longer land a file it rejects (#2372).
- engineering-loop: the pre-queue run is the queue's own selection: the worker's proof and the verifier's run are loop.md's `Affected tests:` command, not the changed test files, so a root rule test the PR did not change fails before the PR is queued (SKILL.md, Narrowed mode; lead.md, verifier.md) (#2455).
engineering-loop: one placement rule, "Where work runs" (#2469, part of #2459). All loop work runs in the cloud, lead, worker and verifier alike; a host only when the step needs that machine. The heavy/light split and its "heavy run" definition are gone, "Where heavy steps run" is renamed, and every pointer to it (role files, the heavy-run hook's refusals, omnigent-agents, a lead's brief) names the new section. The launch fallback order is unchanged. A cloud lead's role file names the Omnigent session tools (`sys_session_create` with a `model`, `sys_session_get_history`, `sys_session_close`) for starting its children.
- engineering-loop: its forwarders resolve the installed copy of the pack's skills, never a developer checkout: a checkout (a git tree holding the marketplace file) is searched only where `AGENT_SKILLS_CHECKOUT` is set, as the pack's own tests set it (#2485).
- loop: the pack's own CI finds its scripts in the checkout it runs in: a checkout counts when it is the `GITHUB_WORKSPACE` of the job running there, so main's push run, the nightly and the tag check run `nightly.py moved` again (#2560).
gatekeeper: the deny list (`LOOP_DENY_LIST`) lets an Omnigent session link (`<scheme>://<host>[:port]/c/<32 hex id>`) through, so a listed host name inside one no longer refuses a post, and still refuses the same name anywhere else; `gatekeeper.py`, engineering-loop's `nightly.py` and `omnigent_agent.py` now share the one check in `scripts/denylist.py`, and engineering-loop's public-repo rule says session links may be posted (#2571).
- engineering-loop: lead.md's Verifier route says a lead in a cloud VM cannot start a Gemini verifier and asks its coordinator to (#2572).
- engineering-loop: a fix round or verifier brief sent to a kept cloud worker names `send --pr --wait`, since `send` alone now returns once delivered (#2578).
engineering-loop: SKILL.md says a green cloud gate run is recorded by `approvals.py local-ci --record`, the one writer, with a plain git push and no host credential, and that a project's gate script writes no record of its own (#2579).
- engineering-loop: a claude-cloud session is not woken by a finished background task, so the rule (verifier.md, worker.md, lead.md, orchestrating-agents) and the cloud brief tell it to wait in the foreground, each call under 10 minutes, and never end a turn on a background task (#2593).
- loop: lead.md names the pack's push hook that refuses a clean merge of the base into a PR and its `LOOP_MERGE_MAIN=<why>` bypass (#2602).
- engineering-loop: `affected-tests` runs no test for a change that selects the whole suite (a declared `select.whole_suite` file; `select.checks` still run) when the project's CI is the merge proof (`loop.ci` not false): it records `whole suite selected; CI runs it` as the head's tests pass, and `--local` runs the suite here (#2621).
- engineering-loop: `nightly.py moved` takes `--sha` and `--workflow`, so a `workflow_run` job asks about the CI run's commit and workflow instead of its own (#2678).
- engineering-loop: a PR head always lints its changed files, with no tests and no build, and a gate record skips that only when it shows lint ran on that tree (R1); the role files stop relying on the commit hook for a cloud session (#2687).

## 0.1.10 - 2026-11-24

- R5 and loop.md's settings name the `Test report:` line: a rerun whose report shows zero tests, where the red run had some, did not run (#2277).

## 0.1.9 - 2026-11-24

- loop: SKILL.md and worker.md say an affected-test selector that can't tell exactly which tests a change touches runs the narrowest set it can still name, never nothing: a coarser selection for a selector that can't run, the tests under a test-setup file's directory, the tests that read a file by path, a file's package or directory tests when no test names it, and the whole suite for a build input; zero only for a change of non-product paths, saying `0 selected: <layer>` (#2217).
- loop: in a repo with no CI, `loop.py brief` tells the verifier to start a fresh session that reruns the head's selection with `local-ci --record --rerun` and to name its record on a `Rerun:` line, where gatekeeper.md's `levels` asks a rerun; engineering-loop's rule section points at the option (#2240).

## 0.1.8 - 2026-11-24

- loop: `scripts/nightly.py moved push|schedule|tag` is the R7 check a project's CI calls to skip a tree a merge queue's batch run tested, or a head the last green nightly ran; `push` reads the batches of the policy's `land.queue` (`mergify` or `github`, whose batch runs are `merge_group` events), so a consumer no longer copies the script and `tag` skips the tag check's suites when a green nightly ran the tagged commit (#2261, #2264).
- engineering-loop: R5 names no runner in its rerun-did-not-run case ("a task the head lacks") (#2301).

## 0.1.7 - 2026-11-24

- engineering-loop: lead.md's `claude` verifier route no longer asks for a `--model` other than the author's (#2297).

## 0.1.6 - 2026-11-24

- engineering-loop: R6 names the pack's `approvals.py queue-select [<base>]` as what a queue's batch check runs: the commands it prints for the batch at HEAD, one per line, each to pass (#2279).

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
