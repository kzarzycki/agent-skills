# Changelog

## Unreleased

New entries are files in [changelog.d/](changelog.d/), one per issue, until a release moves
them here.

## 0.25.0 - 2026-10-28

#322's `demo.sh` replaces `post_demo.sh`, and #595 declares the tools it needs as `metadata.requires`, data a host installer provides. Also: a lead lands every approved PR at once behind the merge queue; a risk:high PR into a feature branch can land on a delegated approval; `approvals.py brief` prints a verifier pass's brief; verifiers start in their own worktree; nothing `approvals.py` posts names the host; and `omnigent_agent.py` gains session-id prefixes, `signature`, and steadier cloud children.

- chief-of-staff: a successor archives its predecessor at takeover, whatever its turn shows; one `reap` keeps (any `kept (…)` state) is marked `to archive` in Owner contact and reaped again at every wake until it prints `archived` or `already archived`, and the owner is asked once whether it still works, since a lost turn end and a live turn look the same. The takeover recall runs in this repo and in each live lead's repo it can reach, since `memory.py` reaches only the bank of the directory it runs in (#198).
- demo: `scripts/demo.sh` replaces `post_demo.sh`. It records and posts in one command: a `.tape` is rendered with VHS, a `.webm` or `.mov` converted to H.264 MP4, and an `.mp4` taken as is, and all of them go into one `## Demo` comment through `gh pr comment --attach` (gh 2.99.0 or later), so each video plays inline instead of linking a release asset. Every refusal now runs before anything records, and untracked files count as a dirty checkout whatever `status.showUntrackedFiles` says. The caption is optional (`--caption`), and `SKILL.md` shows the mise task a project wraps it in. A project calling `post_demo.sh` moves to `demo.sh` (#322).
- engineering-loop: the docs name each loop script from the skill's folder (`uv run <this skill's folder>/scripts/board.py`, and the same for `approvals.py`, `labels.py` and `browse.py`), and SKILL.md says a `scripts/` path sits under the install in a project that installs the skill, not at the repo root, and runs with `uv run`, so an installed project's board move finds the script (#326).
- engineering-loop: `approvals.py check build` before a PR exists judges the issue `--issue <n>` names, else the one the branch is named for (`loop/329-fix`), with the build proofs a PR's issues get, and refuses a branch naming neither; before, it exited 0 with nothing to read, so an unapproved spec got built. worker.md runs it first on a branch with no PR (#329).
- `approvals.py`'s exact-revert check passes a revert that touches only the reverted PR's files and whose merge base and head trees hold that PR's merge-commit and base blobs (and modes) on every one of them, whatever order GitHub's diff pairs the restored lines in, since a plain `git revert` of a large file could be refused as changing "the lines #n changed in another order" though it restored the base tree; any other revert is still compared diff against diff (#351).
- engineering-loop: with loop.md's `carry_over_main` section (`except: <globs>`), a clean merge of main into a PR head keeps the head's verifier verdict: the merge's first parent is the verified head, its second is on main, its tree is `git merge-tree`'s, main's changes touch none of the PR's files, and neither side's changes touch an except glob (matched on the full path, so a nested copy needs `**/<name>`). `check merge` and `land` print one line naming both heads. It never carries a `local-ci` record: the merge reruns its gate, as CI would. A conflict, an evil merge, an overlap, a touched except path or any git error carries nothing; without the section nothing changes (#373).
- orchestrating-agents: a brief or message argument naming a directory or a path through a file follows the text-or-exit-2 rule, as a missing file does: text when it holds whitespace, else exit 2; a file that exists but cannot be read still exits 1 (#390).
- engineering-loop: every verifier starts in a worktree of its own at the reviewed head (`git worktree add --detach <path> <head>`, with the proof logs copied into its `tmp/loop/`), so the lead keeps working in its own and no commit there moves the head under review; step 10's teardown removes each verifier's worktree with the children's; a later pass also gets copies of the previous report and its repros, and an instance the change needs comes up from the verifier's worktree, so the verifier finds it and its log there (#408).
- engineering-loop: with `ci: false`, a `Local check passed` comment counts only from the PR's author, the account running `approvals.py` or a repository writer, as verifier reviews and batch proofs already do, since anyone can comment on a public repo (#452).
- engineering: `audit-third-party-software` and `omnigent-telemetry` say what their `scripts/__pycache__` file is for. apm 0.30.0 leaves `__pycache__` out of a skill's content hash, so a skill whose only change was that marker read as unchanged and was not redeployed, and `agent-sync --refresh` failed on drift; the changed `SKILL.md` redeploys both skills whole (#472).
- engineering-loop: `approvals.py check merge` and `check queue` wait for the checks the base branch requires, read once from its rulesets and branch protection as `land` does, instead of always the aggregate `check`, which stays the wait only on a base that requires none (#478).
- orchestrating-agents: a session whose only live background tasks are `monitor`s (a published Artifact's live updates) and whose last item is a reply finished at least 30 s ago reads `turn ended` in `omnigent_agent.py status`/`watch` and idle to the supervisor, which then treats it as any idle lead; a shell task still keeps it running, and `wait` and `reap` keep the server's `running` (#490).
- orchestrating-agents: a cloud worker's report carries the `tmp/loop/` files it names (a repro, a log) in its PR comment, and `wait` writes each beside the report on the host and lists a named file it lacks as missing (#494).
- engineering-loop: with `owner: <login>` under loop.md's `loop`, `check build`, `check merge` and `land` record an `approved:spec` (or `approved:plan`) label that login added after the spec's (plan's) last edit as the owner's approval, as `approve --by owner` does, and remove `needs-owner`; a label added before the edit is named and changes nothing, nor does another account's (#495).
- engineering-loop: every comment and review `approvals.py` posts (each string of a review's JSON as GitHub publishes it, and `verdict`'s report before any read) and a cloud worker's PR report (which the worker then replies with, for `omnigent_agent.py` to check and post) is checked first against a local deny list, the file the environment variable `LOOP_DENY_LIST` names, one term per line, and refused before any call to GitHub when a line names a listed term; without the variable nothing changes, and a list it names that can't be read refuses (#496).
- orchestrating-agents: `omnigent_agent.py start` and `run` put `LOOP_HEAVY_LOCK=<path>` atop a host child's brief, one lock per lead, and worker.md runs each gate under it, so a lead's parallel workers hold one heavy slot, not one each (#497).
- orchestrating-agents: `omnigent_agent.py relay`, `send`, `status` and `report` take a unique prefix of a session id, looked up among every session the caller sees, archived ones included; an ambiguous prefix lists its matches and an unknown one says "no session matches", both exit 1 (#502).
- orchestrating-agents: an HTTP failure in `omnigent_agent.py` names the server's reason after its status (the JSON `detail`, or Omnigent's `error.message`, else the text), from at most 2 KB of the body read within 2 s of its own, so a stalled body never holds the call (#505).
- engineering-loop: `approvals.py verdict` accepts free text after `pass <n>` on a report's `Verifier:` line and carries it into the posted review's first line, so a qualifier such as a same-family note needs no line or comment of its own; the heading the gate reads is unchanged (#506).
- engineering-loop and orchestrating-agents: a worker or verifier waits on a pending condition in the foreground, under the tool timeout, and never ends a turn on a pending run; a verifier reverts its own mutations before the report; `omnigent_agent.py wait-until --every <s> --limit <s> -- <cmd>` polls a command until it exits 0 (exit 6 at the limit), and `wait` fails, naming the paths, when a host child reports with a tracked change in its workspace that was not there at its start (#507).
- orchestrating-agents: the supervisor's nudge and revive messages end on an accepted wait (`STILL WORKING: waiting on the verifier`), and tests pin the two ordinary-word waits leads wrote (a queue, a heavy slot) so the repeat nudges stay gone (#508).
- orchestrating-agents: `omnigent_agent.py run` starts a cloud child that failed in setup, before its first turn, once more in a fresh session with the same brief, and `run` and `wait` send a cloud child that stalled with no progress one continue message; each recovery is named on stderr, and a second of either fails, naming both (#510).
- engineering-loop: an exact revert of a high-risk change waits for the owner's `approved:merge`, since `approvals.py` now reads its risk from `risk:high` on an issue it names, on the PR it reverts, or that PR's last verdict saying `Risk: high`; before, a revert skipped its issues and landed on the gates alone (#511).
- engineering-loop: a `Verifier model:` condition is judged on the PR as `check merge` judges risk (the labels of the PR and its issues, and the PR's files), and a lower-tier verdict that says `Risk: high` calls for a default-tier verdict on the head before the PR lands, even when the lower-tier one is satisfied (#514).
- engineering-loop: `check merge` refuses a high-risk change whose newest verdict came from a lower tier, read from a `mid` or `small` the verifier writes after its signature on the `Verifier:` line when its brief names that tier (loop.md's `Verifier model:`); a line naming no tier reads as the default, so existing verdicts keep landing (#516).
- engineering-loop: a merge-queue batch proof stands in for the CI or local-check wait only where loop.md opts in with `batch_queue: true` under `loop`, and `check queue` refuses a project without it; before, any project accepted a valid batch proof, a second way past the wait it never set up (#517).
- engineering-loop, orchestrating-agents: a worker, a lead and any child stop only the processes they started, by the pid or process group saved at launch or by a pattern holding their own worktree path, never `pkill -f` or `killall` on a pattern other agents share, which on a shared host kills their runs too (#520).
- engineering-loop: nothing `approvals.py` posts names the host any more (`local-ci <pr>`'s reused pass and the merge queue's `Gated:` line), and every comment and review it posts writes the home directory `~`, so quoted build output names no person on a public board; the local `local-ci` record keeps the host (#521).
- engineering-loop: `approvals.py brief <pr> [--priorities <file>] [--proof <log>]...` prints a verifier pass's brief with its facts read from the PR (base, head, spec, pass number and report path, and from pass 2 the previous report and its head), the priorities as given and loop.md's `## Verifier brief` appended, and refuses a proof log whose first line isn't the head; lead.md step 7 points at it (#522).
- orchestrating-agents: a cloud child's brief (`PR_PREAMBLE`) forbids an interactive question tool and a published page, since each waits on a prompt nobody in the cloud answers, and ends each commit message with the co-author line and no session link, since the commit reaches a public repository (#524).
- engineering-loop: a verifier whose gate or mutation run still waits for the host's heavy slot after 30 minutes of the foreground wait stops it and writes `<report>.question` asking the lead for a proof run, instead of a report without it; the lead has it run off the host, such as by a cloud child, with the new `proof-run.md` brief (green log, mutation log, restore, each headed with the head and the command) and answers with its logs; lead.md step 7 names the brief where the lead reads a verifier's question, and the child returns its logs as named `tmp/loop/` files (#526).
- orchestrating-agents and engineering-loop: a `run` that ends without a report, or a `start` whose launch fails, failed or stopped by SIGTERM, SIGINT or SIGHUP, writes `FAILED: <code>: <message>` to its report path (the child's state and `last_task_error` code, else the launcher's own), never over a report already there (the child's, or an earlier pass's), and `wait`, `send`, `start` and the supervisor never take that line as a report; `lead.md`'s wait rule waits on a child's status or a run's pid rather than its report file, watches for a run gone without an outcome (its pid matched with its command, since a pid can be reused), rechecks its runs on every wake, treats a child with no turn item as dead, stops a long command with its wait, and arms a timer for a timed wait, since a lead waiting on outcomes alone read dead runs as working for hours (#528).
- engineering-loop: the implementer's PR body ends `Impl: <harness>/<model>/<effort>`, and a verifier names the same signature as its family (`Verifier (codex/terra-6.1/med), pass 5`), from the `AGENT_SIGNATURE` line `omnigent_agent.py start` puts in a child's brief (`?` for what it was not given); the `> 🤖 AI` line is for other people's projects only (#529).
- engineering-loop: loop.md is read like a system prompt, so it holds the settings and facts agents act on, each with a short reason only where it changes a decision; history, undo steps, evidence and restatements of the skill go in the PR or issue that set the line (#530).
- engineering-loop: a `risk:high` PR into a feature branch (any base but the default branch) can land on the delegated approver's `approved:merge`, which `approvals.py delegate <pr>` adds with a record naming it the delegate's. `check merge` and `land` refuse that label on a PR into the default branch, and a branch's merge to the default branch is high risk while any PR merged into it carries `risk:high`, so the owner approves the stream as a whole (#534).
- orchestrating-agents: the supervisor reads a background task id (`b` and 8 lowercase letters and digits, one a digit at least, e.g. `STILL WORKING bz3jp5aod`) as a named wait, so a lead that names the watcher it waits on is no longer nudged with "no ending and no named wait" every turn (#537).
- orchestrating-agents: `omnigent_agent.py signature` prints the running session's `<harness>/<model>/<effort>`, read from Codex's rollout or Claude Code's `$CLAUDE_EFFORT` and transcript, so a lead or verifier started through Omnigent's own tools or with default models signs in full. A worker's report, the lead's `Impl:` line (the signature of the agent that did most of the work) and the verifier's `Verifier:` line use it, with the brief's `AGENT_SIGNATURE=` line as the fallback (#542).
- orchestrating-agents: `omnigent_agent.py start claude` (and `codex`) takes the server's native agent when a user copy shares its name, and any other name a server agent and a user agent share is refused with their ids, instead of failing on the server agent's missing config (#544).
- orchestrating-agents: `omnigent_agent.py reap` prints `<session> <title>: already archived` for a session finished before, so a lead reaping a list can tell it from a forgotten one; its exit code is unchanged (#546).
- engineering-loop: the verifier's mutation check undoes each production change on its own (one condition, branch or value, edited back by hand and saved as a patch that `git apply -R` redoes), never the whole diff at once, since a whole-patch revert fails the tests for the wrong reason and hides a change no test covers; a change whose undoing leaves every test green is a major (#547).
- engineering-loop: a `Flaky:` occurrence is its head SHA plus the failing run (a CI run's id, else the time the local gate started), so a second report of the same pair is not counted again toward the third; an `Owner step:` already on the issue for the same action is not posted again; a worker's brief and report name the PR, and its report names the run each retried test came from, so the occurrence comment has every field (#549).
- orchestrating-agents: `start --top-level` subscribes the root of its session's tree, so a worker a lead's helper child started (on another host too) wakes the lead, parked or not, rather than the helper (#592).
- engineering-loop: `approvals.py check merge`, and `check build` once a demo is posted, fails a PR whose newest `## Demo` comment links a video (a release asset, any URL but a user-attachments one) or embeds none, naming `demo.sh`; `demo.sh`'s refusal on a gh older than 2.99.0 says to stop and report rather than post another way (#593).
- engineering-loop: a scope or acceptance change to an approved spec rewrites the issue body, then comments briefly what changed and why, instead of carrying the new scope in a comment (#594).
- demo: `SKILL.md` declares `metadata.requires: "gh>=2.99.0 vhs ttyd ffmpeg"`, the tools `demo.sh` runs, as data a host installer provides and its doctor checks; `tests/test_skill_requires.py` checks the format (#595).
- engineering-loop: the lead lands every approved PR at once, one `land --wait` each, and `land` enqueues a head behind main where the base requires a merge queue instead of refusing it, so parallel lands never wait on each other's merge (#600).

## 0.24.4 - 2026-10-26

#361's merge-queue proof: a project that lands through a batching merge queue of its own gets a proof `check merge` accepts in place of the CI wait. Also: `approvals.py report` checks a verifier report offline; `run` and `start` attach to a live child that already holds the brief; the verifier's gate runs bare and detaches on macOS; long waits use few blocking calls; an optional `Verifier model:` line.

- engineering-loop: a project may land through a batching merge queue of its own. `approvals.py check queue <pr> --head <sha>` says whether a head may enter it (every merge proof but the CI wait, the head's own `local-ci --record` pass under the current env and, with CI, its `check`, not high risk, no `approved:merge`); `approvals.py batch` posts the queue's proof on each PR it merged; `check merge` accepts that proof in place of the CI wait once git shows the head merged unchanged, with no conflict resolution, into a batch whose full gate passed, and the head has its own green `local-ci --record` pass under the env the proof names; `batch` refuses a head without one. Only a batch proof by the running account or a writer counts, and a red or unproven one adds no hold: the wait is exactly as before (#361).
- engineering-loop: `approvals.py report <report>` checks a verifier report the way `verdict` reads it, without GitHub, and the verifier runs it before replying, so a report the lead cannot post costs no extra turn (#481).
- orchestrating-agents: `omnigent_agent.py run` and `start` attach to a live child of the same parent that already holds the brief, instead of starting a second session on the same pass, and refuse one that already wrote its report (#482).
- engineering-loop: the verifier runs an allowed gate as the bare command so a machine's allow rules match it, and detached runs use Perl's `setsid`, since macOS has no `setsid` command (#485).
- engineering-loop, orchestrating-agents: a verifier and the agents the preambles brief wait on a long run in few calls that each block close to the tool limit, not short polls, and a later verifier pass reruns the previous repros from one script (#487).
- engineering-loop: an optional `Verifier model: <tier> for <condition>` line in loop.md lowers the verifier's tier within its own family, as `Worker model:` does for workers (#488).

## 0.24.3 - 2026-10-26

#473's fix: a session `omnigent_agent.py` starts files under its caller's Omnigent project, so a scheduled run's leads land in the task's project. Also: a loop.md bot section may name an updater by head-branch prefix; urgency is the tracker's Priority field; the board's "Item closed" workflow keeps closed issues in a `Closed` column.

- A loop.md `bot.<name>` section may name an updater by its head-branch prefix (`branch: renovate/`) instead of a bot login, so Renovate run under a person's token lands routine lock and manifest PRs on the gates alone; the head must be the repository's own branch and every commit the PR author's. A PR labelled `verify` is never exempt (#353).
- engineering-loop: urgency is the tracker's priority, on a GitHub board its `Priority` field, instead of a `priority:` label no label set defined (#465).
- engineering-loop: the board's "Item closed" workflow stays on and sets the column `Done` maps to, named `Closed` since a closed issue may be completed, not planned or a duplicate; an issue GitHub closes on a PR's `Closes` no longer stays in its last column (#470).
- orchestrating-agents: a session `omnigent_agent.py` starts files under its caller's Omnigent project when `OMNIGENT_PROJECT` is unset, before the repo-name match, so the leads a scheduled run starts land in the task's project (#473).

## 0.24.2 - 2026-10-26

#448's fix: Antigravity reads its brief from a file and runs a role only with the `--permission-mode bypassPermissions` opt-in, so an installed launcher starts an Antigravity verifier; its effort comes from the user's agy settings (#459). Also: `omnigent_agent.py` places cloud workers from a host and keeps them for a fix round, resolves a name held by identical agent copies, and names the right command behind a pending question; this repo's own `test` task records pytest's pid in the gate slot.

- orchestrating-agents: a native agent outside the aliases reads its brief from a file, since agy dropped a long pasted brief; Antigravity refuses a `--role` unless `--permission-mode bypassPermissions` opts into skipping its approvals (#424).
- This repo's own `test` task runs its gate-slot lock inside `uv run` and writes its pid into `gate.1.lock`, as the template's `gate-slot` does, so a waiting `gate-slot` names the running pytest, not an exited process (#442).
- `omnigent_agent.py start|run --pr` sends the PR preamble whether or not the session is top-level, so `start --top-level --host <host> --pr <n>` starts a cloud worker from a host without the cloud harness and it reports on PR n; an agent is given by name or id, and a name several agents hold fails, listing their ids, instead of taking the first match (#447).
- `omnigent_agent.py send --pr` delivers to a session whose workspace is on another host: with `--pr` the report is the file `wait` writes here, so the check that it lies inside the session's workspace is skipped (#447).
- `omnigent_agent.py run|wait --keep` leaves the session open once its report is in; engineering-loop's Cloud worker sends a fix round to the kept worker with `send --pr` while it is still there, since a fresh session is a fresh VM, clone and build (#447).
- `omnigent_agent.py start` waits on this host's capacity only for a session on this host; one `--host` puts on another host starts at once (#447).
- The `--pr` preamble tells a cloud worker that its checkout is the branch checked out in the workspace it started from, not necessarily the PR's (`git fetch origin pull/<n>/head` gets that), and that a foreground command stops at 10 minutes, so a long run starts detached and is polled within the same turn (#447).
- `omnigent_agent.py` resolves a name several agents hold to the newest of them by `created_at` when their records and configs match apart from identity and bookkeeping (`id`, `version`, `created_at`, `updated_at`, `object`), since each upload of one spec registers another copy and a record has no host to tell them apart; the record carries policies, skills and terminals and the config instructions and model, so both are compared. Agents that differ are still refused, listing their ids (#454).
- `omnigent_agent.py relay`'s queued line names `approve` only for an approval prompt, each with what it holds; behind a question it says the message stays queued and lands once the question is answered, and names `relay --answer` only as what to use instead of a plain relay next time (with `--from`, it says only the owner's own relay answers it), since nothing withdraws a queued input and a rerun with `--answer` would deliver the same words twice; `approve` with only a question pending fails naming it and `relay --answer`, since both lines sent a caller blocked on AskUserQuestion to the wrong command (#457).

## 0.24.1 - 2026-10-26

#428's fix: an installed skill gets no Python bytecode, so a consumer's `apm install --frozen` leaves the lock clean (ignore `__pycache__/` with the slash). Also: long gates, repros and live runs start detached and are polled; cloud workers push to their assigned `claude/` branch; leads finish children whose reports are in; and `omnigent_agent.py` gets `owner-said`, a safer `relay`, and better capacity and supervisor reads.

- orchestrating-agents `supervise --console`: a lead's report-path reply is routed on the report's ending wherever it stands (`report_head`), not its `# title` line; a child's full session id after `STILL WORKING … on`, or any word after "waiting on/for", is a named wait (a commit after "on" is not); a report's endings in code fences, `>` quotes and backticked lines are not its own; the small model's output cap is 1000 tokens (at 200 `claude -p` exited 1) and a failed call names what it printed. `start --top-level` from a lead the registry follows, or from that lead's child, subscribes that lead and arms nothing, so a lead's own helpers no longer page the chief of staff; `report <session> <dir>` lists up to 1000 entries, not the API's default 20 (#366).
- `omnigent_agent.py owner-said <session> <quote-file>`: checks that the owner typed a quote in a session (not a brief, supervisor post, relay or Omnigent notice) and prints a citation, so a lead can verify a relayed owner decision instead of refusing it; a plain `relay` now opens with `[relayed by <session>]`, and the chief of staff cites each owner decision it relays (#369).
- `supervise --registry` re-executes itself in place when `omnigent_agent.py` is replaced on disk (once the file is stable and compiles, state written first), so a skills sync that updates the script needs no supervisor restart (#372).
- `engineering-loop` states that a project's heavy test part runs behind a host-wide gate slot shared by every worktree, and that a parallel runner takes the free cores (`GATE_JOBS`) rather than every core, so leads on one host queue their gates; this repo's own `test` task holds the same slot instead of starving each other and new sessions (#395).
- `omnigent_agent.py capacity` reads available memory on macOS from `kern.memorystatus_level` (the free share `memory_pressure` prints) instead of printing `inf MB available`, and says `memory not measured` when it cannot read it (#396).
- orchestrating-agents `supervise --console`: a lead due for "no progress" whose report was written after its last progress is not paged; the report's time comes from its folder's listing (`Omnigent.modified`), read only once the lead is due (#397).
- `omnigent_agent.py relay` answers an open question only with `--answer`; without it, a session waiting on a question holds the message behind it (exit 5), so an unrelated relay never becomes the answer (#402).
- verifier.md, worker.md, lead.md: a gate, repro, e2e or live run that may wait on a lock or outlast one tool call starts detached (`setsid nohup`, log, pid and exit code in files) and is polled, so a pass is not spent on its own timeout and Claude Code's low-memory reaper cannot stop it (#409).
- orchestrating-agents: the brief preambles and the nudge tell a child to start a long run detached (`setsid nohup`, log, pid and exit code in files) and poll it, not to run it in the foreground; a held lock outlasts a foreground call and a low-memory reaper stops in-session background shells (#417).
- orchestrating-agents `--pr` (cloud worker): the brief has the worker push only to its session's assigned `claude/…` branch and name it with its head SHA in the report; a worker whose comment post fails replies `UNPOSTED REPORT` and the body, which `wait` posts on the PR from the host and writes to the report path (#419).
- SKILL.md, Cloud worker; lead.md: a cloud worker pushes to its assigned `claude/…` branch and reports it with the head SHA, and the lead fetches and merges it, since a cloud session declines other branches; if its report fails to post (an expired proxy token), it replies `UNPOSTED REPORT` and the body, which `wait --pr` posts from the host (#419).
- lead.md: the lead finishes a worker or verifier as soon as its report is read or its verdict posted, and at each wake any child whose report it has and whose turn ended over 15 min ago, since idle children keep their processes, MCP servers and runners alive. With Omnigent, `run` and `wait` already finish the child they return; a report heard another way (`send`, `watch`, a `run` that died) needs `reap <id>` (#426).
- A `__pycache__` file in each owned skill's `scripts/` keeps Python from writing bytecode into an installed skill, whether a script runs or an agent imports a sibling module, so a consuming repo's `apm install --frozen` no longer rewrites `apm.lock.yaml` and its `agent:sync` stays clean (#428). A consumer must ignore cache folders as `__pycache__/`, with the slash: a bare `__pycache__` line also ignores these files, so a fresh clone lacks them and its first `apm install --frozen` rewrites the lock.
- orchestrating-agents `Omnigent.active`: a session it subscribes to (a top-level helper such as a cloud worker, which is no child) counts like a live child, so `supervise` no longer pages "no progress" for a lead whose cloud worker is running; an archived or gone helper counts for nothing, and an Omnigent without subscriptions keeps the children-only answer (#432).
- `omnigent_agent.py capacity` judges CPU by measured idle share (`OMNIGENT_MIN_CPU_IDLE`, default 10%), not the load average, which on macOS also counts threads waiting on I/O and memory; load per core decides only when idle cannot be measured. `OMNIGENT_CAPACITY_WAIT_SECONDS` sets how long `start` waits for room (#435).
- orchestrating-agents `start`/`run`: before creating a cloud session (harness `acp:claude-cloud`) whose workspace is on this host, a worktree without `remote.defaultEnvironmentId` in its `.claude/settings.local.json` takes its main checkout's pin, keeping its other settings; with no pin anywhere the start is refused before any session exists, since the session would land in the account's default environment (#437).
- chief-of-staff: a brief names the pack scripts installed in the lead's repo, else the chief of staff's own install, never a developer checkout, which can sit on a stale branch (#440).

## 0.24.0 - 2026-10-26

loop.md's settings are a YAML block (breaking: migrate loop.md and issue-tracker.md with this release), `land --wait` no longer reports a merged PR as failed and dequeues a merge-queue entry GitHub never started checks for, leads search before filing and park owner-only steps, and `omnigent_agent.py` retries a server restart.

- loop.md's settings are a YAML block that `approvals.py` reads with PyYAML's `safe_load`, in place of the line language its regular expressions read: a rule is keys (`labels`, `paths`, `always`, `verifier`), never words, so a path such as `docs/verifier.md` can no longer read as the `verifier` term, and a section or key the schema doesn't know, a key set twice or a value of the wrong type is refused, naming the key. Types match exactly, so a value YAML 1.1 reads as another type where a name was meant (`no` or `on` as a boolean, `1.10` as a number) is refused too: quote it. A value names a thing, never a rule in words: the spec policy is `spec.auto`, a list of the kinds it approves or `true`, not a phrase. SKILL.md § Settings holds the schema and why YAML: read and edited by hand as `key: value`, a list one item per line, and typed. `approvals.py`, `labels.py` and `board.py` declare PyYAML inline (PEP 723), so `uv run scripts/approvals.py` installs it on first use; run with a bare `python3` without PyYAML, each exits with one line saying to run it with `uv run`. They still run on Python 3.9 (#344).
- Migration: a loop.md on the line form is refused until it moves to a ```` ```yaml ```` block under `## Settings` (SKILL.md § Settings has an example of every key). `spec: auto unless risk` becomes `spec:` `auto:` with the items `bug`, `follow-up` and `sub-issue`, and `spec: auto` `auto: true`; `cap: <n>`, `CI: none`, `Local CI env: A B` and `Opt-out: allowed` become `cap: <n>`, `ci: false`, `local_ci_env:` with the items `A` and `B`, and `opt_out: true` under `loop:`; § Practice's lines become `practice:` keys (`plan: writing-plans`); each `risk:`, `plan:` and `signoff:` condition becomes that section's terms, `component billing` and `size:L or larger` written as `labels:` with the items `area:billing`, `size:L` and `size:XL`, and paths as `paths:` with `.github/**` and `CODEOWNERS`; `bot: <login> <condition>` becomes `bot:` `<login>:` with its `paths`, a glob starting with `*` quoted; `Land: local signed squash to <branch>, allowed signers <path>` becomes `land:` with `signed_squash_to` and `allowed_signers`. `merge: auto unless risk` was the default and goes; a `merge:` or `spec:` condition still read as a risk rule moves into `risk:`; `- risk-criteria:` lines become prose under `## Risk criteria`, which the verifier reads. The project's tasks and CI that call the scripts with `python3` call them with `uv run`. Migrate loop.md and issue-tracker.md in the change that moves the project's installed reader to this release, never before: an older reader finds no line form in the block and silently runs with none of its settings, no risk rule and no spec policy among them (#344).
- `docs/agents/issue-tracker.md`'s label and board facts move to the same kind of ```` ```yaml ```` block under `## Settings`, read by `approvals.py`, `labels.py` and `board.py` and refused the same way, naming the key: `## Components` items become `components:` (`billing: invoices.`), `## Extra categories` `categories:`, `## Extra labels` `labels:`, `## Renamed labels` `renames:` (`frontend: area:web`) and `## Board` `board:` (`Build: In progress`). Never on GitHub stays prose. A tracker file without the block is refused (#344).
- `approvals.py land --wait` reads a PR once more before exit 1 when it finds it open and neither queued nor on auto-merge, because GitHub takes a PR out of the merge queue a moment before it reports the merge: a PR that merged no longer exits 1 (#367).
- `omnigent_agent.py relay --from <name>`: a notice from a task or an agent opens with a line saying it is not the owner's words and never answers an open question, which it waits behind (exit 5) instead; a scheduled job's status relay had answered the chief of staff's question to the owner (#368).
- `omnigent_agent.py` takes every brief and message argument (`run`, `start`, `send`, `relay`, `broadcast`) as a file or the text itself, and exits 2 with one line for a single word naming no file, instead of a traceback (`File name too long` for a long text) (#370).
- Supervisor console: a lead the owner drives in its own session is marked `direct` (`omnigent_agent.py direct <session>`, `--off` clears it) and gets no deadline, nudge or quiet-end routing, and drops out of the `no event in <n>s` log line; and a relay or the owner's message to an idle lead starts a new progress chain, so a lead woken after hours on `USER NEEDED` is no longer nudged at once for `no progress <n>m` (#371).
- Stale proof is rerun before a verifier pass, not found by it: lead.md step 7 checks that every proof log names the head (a one-line `head -1` check) and reruns the rest first; a worker's fix reruns the proofs it touches and lists each log with its SHA (#374).
- A flaky test costs one retry, not a gate: a project's `check` retries a failed test once in its runner and prints what passed only on the retry; each such test has one `Flaky: <test id>` issue, found by its id before filing and commented per occurrence; the third occurrence quarantines it from main with the issue open for the fix; the verifier reports no recorded flake (#376).
- A step only the owner can unblock (a GUI dialog, a locked screen, a device, a permission denial, a credential, an expiring link) parks instead of blocking: stopped at its first sign, its slot or lock released, one `Owner step:` comment with `needs-owner` and a line in the decision-log issue, asked once; before an unattended run the owner-only prerequisites are tried while the owner can answer (#377).
- No two leads build the same fix: before filing an issue or starting one, search the open issues and PRs of this repo and of the repo that owns the cause for the symptom and comment there instead (whoever filed first owns it); the draft PR opens when the branch is cut, as the claim; another lead's PR is taken over only on that lead's word or its starter's (#378).
- `approvals.py land --wait` dequeues a merge-queue entry still waiting for checks 10 minutes after it was queued with no check suite on its merge-group commit, and lands the PR again: an entry GitHub never started CI for no longer waits out the queue's check timeout (#386).
- SKILL.md, github.md and `labels.py` say that `setup:github` syncs the labels, which project-templates already wires in, instead of sending readers to run it by hand (#393).
- `omnigent_agent.py` retries a `GET` on an SSL EOF, a refused or aborted connection and HTTP 502/503/504, over about two minutes, so a server restart no longer fails a `run` or `wait` whose session finished (#405).

## 0.23.3 - 2026-10-25

The verifier judges each change's risk, a cause in another repo gets a generic issue there, and a project can opt in to workers in a cloud session.

- The verifier judges risk on every review, a `Risk: low|high — <reason>` line that `verdict` requires, and asks for evidence that settles a risky but checkable change as a finding; a risk rule's new `verifier` term holds when that line on the head says anything but `low`, so `risk: verifier or path .github/**` sends the owner only what no check can settle. A `risk:high` the gate added for the line comes off when a later pass says `Risk: low`; the lead may dispute or raise risk, never lower it (#330).
- A problem whose cause is in another repo (a shared skill, a tool, a project template) gets two issues: a generic one in the repo that owns the cause, naming nothing of the project when that repo is more public, and one in the project for its side, linking to it; links point from the less public repo to the more public one (#346).
- An opt-in cloud worker, turned on by the `docs/agents/loop.md` line `Cloud worker: <agent>, gate <task>`: the lead and the verifier run on the host and only the workers run in cloud sessions, reporting on the PR (engineering-loop SKILL.md, Cloud worker). `omnigent_agent.py run|start|send|wait --pr <n>` has a cloud worker post its report as a REST comment on PR n and end its turn with the comment's URL, which `wait` writes to the report path once GitHub files the comment on that PR of the checkout's repository; `send --pr` takes only a comment newer than the report already there. Without the line the loop is unchanged (#355).

## 0.23.2 - 2026-10-25

A recorded local pass counts at landing only under the gate environment it ran in.

- `local-ci` records the environment its check depends on and reuses a pass only under the same one: a project names the variables on a loop.md line, `Local CI env: NAME NAME…`; a record holds each one's value or null for unset, `local-ci <pr>` reuses it only when every value equals the current environment, a record without `env` (0.23.1's) is never reused, and the posted comment names the values (`Env: GATE_SCOPE=changed GATE_UI_TESTS=0`, or `Env: default`), for a fresh run and a reused one alike. Before, a pass recorded under a lighter tier was posted as if it were the full run (#340).

## 0.23.1 - 2026-10-25

A local merge check that passed before review counts at landing.

- `approvals.py local-ci --record` runs the merge check, `mise run check:all`, on HEAD with the same clean-tree checks as `local-ci <pr>`, and on exit 0 records the pass by commit (head, command, exit, time, host) under the git common dir, which every worktree sees and nothing commits. `local-ci <pr>` posts the pass from a record for the PR's exact head and the same command, naming its time and host, instead of running the check again; any other head, command or a failed run runs it as before, and that pass is recorded too. With `CI: none`, the loop's check on a head pushed for review is `local-ci --record` (#335).

## 0.23.0 - 2026-10-24

Signed local landing, a verdict any writer can post, a chief of staff that files an intent
issue and delegates without investigating, a broadcast to every lead, any registered agent by
name, and headless browser checks.

- Chief of staff page shows every Omnigent session on every host, grouped by project and coloured by what the owner must do (needs you, when convenient, running, done), red items first with what to do, where and why, and what changed since the owner last looked (#274).
- `omnigent_agent.py start` and `run` label a session `omni.role` with its engineering-loop role, from the `--role` file's name (`lead`, `worker`, `verifier`), and `supervise --console` labels the chief of staff's own session `omni.role=cos`, so Omnigent's usage metrics can split spend by role (#276).
- `omnigent_agent.py broadcast <message-file>` relays one message to every followed lead in the registry, `--include`'s sessions and, with `--active-hours N`, every recently updated top-level session, all at once, printing one line per target and exiting 1 when one failed or could not be read; never its own session, an archived one, an automations project's or one with a question or approval prompt pending (`skipped: waiting on a question`), which `relay` would answer with the broadcast; `--project`, `--host`, `--exclude` narrow it and `--dry-run` lists it (#277).
- The native orchestration backend starts only native subagents of its own harness: the bare-CLI path (`codex exec`, `claude -p`) is gone, and a child of another model family points to the Omnigent backend. The engineering loop's Independent verification names the backend as a condition of the other-family verifier (#278).
- The supervisor reads a timed wait from the time its wait names: of several UTC times after `STILL WORKING`, the one in a sentence or line that says "wait", else the earliest still to come when the message was written, else the earliest (#283).
- The supervisor reads `USER NEEDED` anywhere in a lead's message as its ending, so an ask after a `DONE` line reaches the owner instead of reading as done (#285).
- The routing table, the supervisor's follow rules, the chief of staff's ending rules and the loop's Turns rule state that a `USER NEEDED` line wins over an earlier `DONE` or `PARKED` line, as `ending_of` already reads it (#290).
- The chief of staff page takes a board bullet's own 🔴🟡🟢⚪ marker as its level (#291).
- `approvals.py verdict` reads a verifier report's `###` headings without a `(<severity>)` as sub-headings, posting nothing for them, instead of refusing the whole report; it refuses a report whose finding headings don't add up to its `VERDICT: <n> blocker, <n> major, <n> minor` counts, so a finding in any other shape is never dropped without a word (#293).
- `post_demo.sh` posts in a repo with immutable releases: when `immutable-releases` reports `enabled: true` it creates one prerelease per post, `demo-pr<N>-<sha7>-<time>`, with the videos attached by the same `gh release create`, instead of uploading to the shared `demos` release, which GitHub refuses with HTTP 422. Other repos keep `demos` (#295).
- `supervise --registry` reports a followed lead's prompt only after it has been pending for 120 s (`PROMPT_CONFIRM_SECONDS`), re-reading the session at each look. Omnigent shows a child's prompt on its parent too, and the lead answers it within seconds, so the `--console` supervisor no longer posts the owner an approval that clears by itself (#297).
- `omnigent_agent.py` and `omnigent_telemetry.py` no longer read `config.yaml`'s `server:`: outside a session they act on `--server` or the one login, and refuse otherwise, since one account runs workloads on several servers (#302).
- The chief of staff page groups the board's asks, and its "Needs you now" list, by project or by the area a bullet names (`- 🔴 **voice_note:** …`); the "Board: when convenient" group is gone (#304).
- `omnigent_agent.py` acts on the session's own Omnigent server (`$RUNNER_SERVER_URL`) ahead of `config.yaml`'s, with `--server` to name one; the chief-of-staff page and the detached supervisor name it too, for hosts with runners for several servers (#312).
- The chief of staff files an intent issue before starting a lead and hands the lead that issue as its spec, so an ask's intent and state survive on the issue board across sessions; non-repo work gets none (#314).
- The chief of staff delegates a new ask without investigating it: it files the intent issue with the owner's words and only cheap missing facts, asks when the intent is unclear, and starts the lead, whose first step is the investigation (#316).
- `engineering-loop`: workers and verifiers run browser tests and UI drives in a headless browser of their own, attach to the owner's open automation browser only when the check needs its logins, and where headless is impossible open one in the background without focus, saying which test needed it (#318).
- `land` can land a PR as a locally signed squash: with loop.md's `Land: local signed squash to <branch>, allowed signers <path>`, it squashes the proven PR here, signs it with the checkout's SSH key, checks it against the allowed signers, and pushes it to the PR's branch and then the base, so a repo that trusts only its maintainers' signatures can use the loop's landing; without the line landing is unchanged (#320).
- The merge gate counts a verifier review posted by any account that can write to the repo, not only the PR's author or the account running it, so a colleague (or their agent) who verifies or fixes someone else's PR can post the verdict that lands it, in CI too (#323).
- `omnigent_agent.py start` and `run` take any registered agent's name, a user's own included (`claude` and `codex` stay aliases): the lookup reads the server's agents, then the caller's (`scope=user`), following pages, and an unknown name fails before any session is created. An agent outside the two aliases gets its brief inline in the first message, since its tools may run on another machine (#327).

## 0.22.0 - 2026-10-21

A chief of staff that runs from its own home and wakes only on a lead's news, through a
supervisor console that settles routine events; `land --wait` lands a PR end to end; worker
models named as tiers.

- `omnigent_agent.py reap` with `--registry` or `$OMNIGENT_SUPERVISE_REGISTRY` drops each
  session it finishes from the supervisor registry before archiving it (#249), so a chief of
  staff that reaps its finished lead is not woken by `archived` for its own reap, and no longer
  edits the registry by hand.
- A chief of staff's handover file and memory bank come from the project's instructions, with
  `tmp/loop/chief-of-staff.md` and the repo's bank as defaults, so it can run from a home of
  its own across projects (#230). A handover file in a repo with a remote is pushed after
  each rewrite and pulled on takeover, and a restart into another permission mode or harness
  is a fresh session that takes over from the file.
- A project may name its worker model in loop.md as a tier, `Worker model: <top|mid|small> for
  <condition>` (#245, #247): the lead starts a worker whose issue matches on that tier's model
  from the worker family's newest generation, the closest higher tier there when that
  generation lacks it, never an older generation's model and never a frontier model above
  `top` (Claude Fable, Codex Astra, #250), and on the harness default
  otherwise, so a cheaper worker model is one line the owner can change.
- A chief of staff wakes only on a lead's news (#238). `supervise --registry` follows a lead
  whose line ends in `follow`, posting to `--notify` a turn end that names `DONE`, `USER NEEDED`
  or `PARKED`, any other turn end once the lead and its live children were quiet for 300 s, a
  prompt, a failure, and `archived`, which drops the line; it never revives or nudges one.
  `start --top-level` with a registry arms that line and subscribes nobody, since 404 of 521
  subscription-woken chief-of-staff turns changed nothing; without one it subscribes as before.
  The chief-of-staff skill follows leads through one detached supervisor, and its handover names
  it.
- `approvals.py`, `board.py`, `labels.py` and the demo skill's `post_demo.sh` refuse to run
  in a checkout whose remotes name several GitHub repos while `gh repo set-default` names
  none (#236). gh then reads every `{owner}/{repo}` and `gh pr` as `upstream`'s, so a
  verdict posted from a fork's checkout landed on the upstream PR of the same number.
- `approvals.py land <pr> --wait` is the one background command a lead starts to land
  (#235): it marks a draft ready, waits while required checks are pending with none red,
  merges, or turns on auto-merge, and waits for GitHub's merge, through a merge queue too
  (exit 0 only once merged), and ends on every other outcome: auto-merge turned off or the PR
  out of the queue (exit 1), what CI won't clear (exit 3, so the owner is
  asked only about a head CI has passed) or 2 hours (exit 3). It replaces lead.md's two
  hand-written waiters, one of which watched a check named `check` that a repo may not have
  and so never ended. `land` also refuses (exit 1) a head GitHub reports `BEHIND` or `DIRTY`,
  naming the fix, where GitHub's own refusal read as a required check `expected`, and marks
  nothing ready nor merges while that merge state is `UNKNOWN` (exit 3; `--wait` reads again).
- The package's file inventory leaves out `__pycache__` and `*.pyc` (#223), so a script imported
  from a skill folder no longer fails `vendor-engineering-check` on a bytecode cache git ignores.
- `post_demo.sh` uploads each video as an asset of the repo's `demos` prerelease and links it
  in the `## Demo` comment (#234), since `gh pr comment` has no `--attach` and every post with
  a video failed. The video is a download link, not an inline player.
- `omnigent_agent.py approve <session> [--decline]` answers a session's pending approval prompts
  through Omnigent's resolve route, printing each tool call it answered (#229). `relay` to a
  session blocked only on a question answers it with the message through the same route,
  instead of interrupting it, which held the message up to 7 minutes (kzarzycki/omnigent#14).
  A chief of staff runs `approve` on the owner's word, and quotes an approval in a lead's
  brief word for word.
- `omnigent_agent.py start --top-level --host <name|id>` starts a lead on another Omnigent
  host (#215), since an agent's `sys_session_create` makes only children, which run on their
  parent's runner. On another host `--workspace` and the report are absolute paths there, the
  brief goes inline in the first message, and the lead is followed with `watch`.
- The chief-of-staff skill states how to work delegated and under load (#224):
  - a delegated decision is reported as options, a recommendation and the action taken;
  - a chief of staff records an owner's approval as a label with a quoted comment, and leaves
    the written record to the owner;
  - a release checks the standing decisions first;
  - an adopted session becomes a lead;
  - an overloaded host's leads park at a clean checkpoint;
  - a lead rewriting a shared checkout has it to itself;
  - a chief of staff counts why it involved the owner, and proposes a fix for a cause that
    repeats.

  The handover names the exact subscribe and info-only takeover calls, quotes the owner with
  the session id they spoke in, and records revives spent on every lead (#196's A1 dry run).
- `omnigent_agent.py` under load (#226):
  - `capacity` says whether this host has room for another session, and `start` and `run`
    wait for it, failing after 10 minutes;
  - a message whose POST timed out is confirmed from the history instead of failing the
    `start`, which had archived sessions that took their brief;
  - `run`'s usage says a lead (`--top-level`) uses `start`, then `watch`.
- `omnigent_agent.py start` and `run` take `--permission-mode <mode>`, defaulting from
  `$OMNIGENT_PERMISSION_MODE`, for a Claude child (#213). Omnigent applies it at terminal launch.
  Codex takes none: its CLI fails to start with the flag, so `start` refuses it there.
- New owned skill `omnigent-telemetry` (#206): `scripts/omnigent_telemetry.py` reports
  Omnigent spend, tokens by model, session trees, scheduled-task health and Codex rate limits
  over the last N days from the API, the server's Postgres and local Codex rollouts, with
  one-line anomaly flags (`SUBAGENT_EXPLOSION`, `VERIFIER_CHURN`, `FORK_BLOAT`,
  `SUBSCRIPTION_AMPLIFICATION`, `CRON_FAIL_LOOP`, `SIDEBAR_NOISE`) and `--html` for an
  offline page of the same numbers. A source that does not answer leaves its sections out
  and the report names them.
- `omnigent_agent.py run` takes a report written in the same clock tick as its launch (#185):
  it compared the report's mtime with `time.time_ns()`, which runs ahead of the kernel's coarse
  file clock, so three `run` tests failed in most runs. A report already at the path is still a
  pass before; only one newer than it counts.
- `status`, `watch` and `run`/`wait`'s failure lines print the session's last assistant message,
  or `(none)`, never a user message such as the brief or an injected reminder (#185).
- Cheaper runs, from the 2026-10-19 retro (#207). Continuing on the other model family, or
  replacing a chief of staff, starts a fresh session from the notes or handover file,
  never a fork of the old one; `operating-omnigent` lists the fork endpoint with when not
  to use it. A later verifier pass reviews its delta in one session, with no `code-review`
  axis sub-agents. A verifier reviews a pushed PR head only, never a helper script or a
  mid-edit snapshot, and a proof log's commit SHA is its whole provenance.
- A chief of staff relays an owner message to a lead in one call (#202): `omnigent_agent.py
  relay` returns at once with exit 0 (delivered), 5 (queued, and it will land) or 4 (not
  deliverable, and why), whatever the lead is doing and on whichever host. A lead blocked on
  a question gets the message as its answer (#229); an approval prompt never does. `status` reads a lead's state, queued inputs and last message in one call.
- A chief of staff reports to the owner at task level (#199): a task started, what blocks it,
  a decision the owner must make, its result. A lead's interim progress, such as a verifier
  pass, a gate re-run or a worker's hand-off, stays in the lead's session.
- A chief of staff nudges only a stalled lead (#201). A lead waiting on its own worker,
  verifier or CI, or on another lead, gets no nudge and no escalation, and a lead waiting
  on another lead hears of that lead's merge from the chief of staff.
- A chief of staff's handover file is one page, overwritten in the turn its state changes,
  before the owner hears it: owner contact, standing decisions, live leads, closed, follow
  (#196). A successor in either harness takes over from that file alone, never from
  transcripts.
- `retro` again has the agent read the `writing-for-agents` skill before drafting, or say it
  is unavailable; names teeing dev-server output to a log the agent can read; and prefers
  building a deterministic check over proposing one (#216).
- `supervise --registry --console`, the chief of staff's console, keeps its state where a
  successor or the web UI can read it (#255); without `--console` the supervisor behaves as
  before. Each poll writes `<registry>.state.json` (schema `cos-state/1`, atomically) with an
  entry per registry session (title, host, state, wait, ending, first line, `progress_at`,
  budgets) and the ids of events already posted, loaded on start, so a restart re-posts no
  follow end and keeps each lead's progress; appends each event to `<registry>.events.jsonl`;
  and labels each session with `status.line` and `status.at`, written only when the line
  changes or once a minute. A followed lead with no progress for 20 minutes, its own history
  and its live children counted, raises a `deadline` event, whatever its status reads, unless
  it is parked or ended with `DONE` or `USER NEEDED`; a nudged one with an unknown wait a
  second, 10 minutes later.
- `omnigent_agent.py report <session> [<path>]` prints a lead's report, or any file of its workspace or host, through Omnigent's file API from any host: exit 4 for a missing file, 1 for an offline host (#256).
- `supervise --registry --console` settles routine events itself and wakes the chief of staff
  within hard bounds (#257); without `--console` it posts every line as before. Each event is
  routed by one table (`route`): archived, parked, a named wait and exact repeats need no post;
  a quiet end goes to one small-model call (`claude -p`, `claude-haiku-5-5` unless
  `$OMNIGENT_SMALL_MODEL`; 20 s, 4,000 characters in, 200 tokens out; anything unclear routes
  act), and so does a `USER NEEDED` a `--decisions` file's standing decisions may cover. The
  supervisor sends the stall nudge (once per progress chain) and the revive (once per lead) and
  tells each lead started with `start --top-level --after <session>` of that lead's `DONE`, each
  through `relay` as an intent in `state.json` that a restart looks up in the lead's history and
  never sends twice. What needs the chief of staff or the owner is posted as `Supervisor [act]
  b-<id>: …` or `Supervisor [owner] b-<id>: …`, with each lead's status row and report head, at
  most one post per 5 minutes and 30 model calls an hour, both windows kept across a restart; a
  pending post is looked up by its id in the notified session's history after a crash and sent
  again only when missing. `status.line` on the notified session shows `needs you: <n>` while
  owner events wait. `--fyi post` also posts every line; `events.jsonl` names how each event was
  settled.
- `chief-of-staff` acts on `Supervisor [act]`/`[owner]` posts from what they carry, never nudges a lead whose history shows the supervisor's `LEAD_NUDGE`, follows with `supervise --console --decisions <board>` and `start --after`, and takes over from the predecessor's registry and state file (`leads.registry` → `leads.state.json`) read with `report`; the board drops its Live leads table (#258).
- `omnigent_agent.py supervise --console` reads a followed lead's report when its last message is only the report's path, once per message, and takes the lead's `ending` and `wait` from the report's first line, so a lead that ended `DONE` or names its wait is no longer nudged at the progress deadline (#264).
- `omnigent_agent.py supervise --console` reads a `STILL WORKING` that names a UTC time (`until 2026-10-21T23:17Z`, `2026-10-21 23:17 UTC`) as a timed wait and raises no progress deadline before that time plus 20 minutes; a wait word now counts only opening the `STILL WORKING` text or after `on`/`for`, so "per lead event" no longer reads as a wait on a lead (#266).
- `engineering-loop/scripts/browse.py` renders a web UI in headless Chromium and saves a screenshot, after an optional scripted interaction (`--do`); `--omnigent` signs it in to an Omnigent server with the CLI's login. worker.md asks for a rendered check on every web UI change and verifier.md drives the UI the same way (#268).
- `chief-of-staff/scripts/cos_page.py` serves one tailnet-only page of the supervisor's state: each lead with its Omnigent session link, state, wait, last line and age; events waiting on the owner; recent events with how each was settled (#270).
- `omnigent_agent.py start` and `run` print a stderr line when a top-level session matches no Omnigent project, naming the name looked up and `OMNIGENT_PROJECT`, instead of leaving it unfiled in silence (#272).

## 0.21.1 - 2026-10-18

Two fixes to `omnigent_agent.py`.

- A session files under the Omnigent project whose name matches the repo's ignoring case,
  spaces and punctuation, so `voice_note` files under "Voice note" (#194). An exact name wins;
  two loose matches with no exact one fail and name `OMNIGENT_PROJECT`. Letters and digits in
  any script count.
- `reap` exits 1 when a finish failed, after trying every session (#192).

## 0.21.0 - 2026-10-17

No model is hardcoded or picked in the pack (#175), and a finished sub-agent is archived (#188).
The latter needs an Omnigent build with kzarzycki/omnigent 4dd0af32, a new requirement, so this
is a minor version.

- A Codex verifier no longer defaults to `gpt-6.1-sol`: every child runs on `--model`, else
  `OMNIGENT_MODEL_<AGENT>`, else its harness's configured default (Codex:
  `~/.codex/config.toml`).
- `engineering-loop` SKILL.md § Models and `lead.md` step 4 no longer pick a model per item: a
  lead leaves it to the default unless the owner names one. A launch that fails on capacity is
  retried later on the same model, never on another (`backends/omnigent.md` § Model).
- A finished sub-agent is archived, like a top-level session, instead of having its turn
  interrupted and its terminals ended and being left unarchived (#188). It needs an Omnigent
  build with kzarzycki/omnigent 4dd0af32, where archiving a sub-agent leaves the runner it
  shares with its parent up; an older build stops that runner and the parent with it.
  `reap` prints `archived` for every session it finishes.

## 0.20.0 - 2026-10-17

A chief of staff hears its leads through Omnigent session subscriptions, not a detached
supervisor job (#182). It needs an Omnigent build with subscriptions (kzarzycki/omnigent#6);
a Codex chief also needs its shell to name its session (kzarzycki/omnigent#9).

- `omnigent_agent.py start --top-level` subscribes the session it runs in to the new lead,
  before the brief is sent. Omnigent then posts the chief a notice each time the lead ends a
  turn or waits on a prompt, and revives the chief for it. A subscribe that fails, or a shell
  that doesn't name its session, prints `not subscribed` and the start still succeeds: follow
  that lead with `watch`.
- `chief-of-staff` follows its leads by those notices and subscribes with
  `sys_session_subscribe` to a lead it takes over. The launchd supervisor is gone from the
  skill and the README.
- `send` bounds a follow-up's report by the session's own workspace, so a lead working in a
  parent directory or a sibling repo no longer has its report rejected.
- `watch` counts a native session's turn end only once it has held for 30s, since a Claude
  session reads idle in the middle of a turn.
- Ending a sub-agent interrupts its turn before ending its terminals. Ending only the terminals
  left a Codex child's turn running, and an ended verifier kept working and overwrote a report.

## 0.19.1 - 2026-10-17

- An Omnigent child's label names its work. Omnigent labels a child by a model summary of its
  first message, not by its title, and that message was the same line for every child, so
  labels came out as "Read Brief and Execute". The line now leads with the title
  (`Work on pr182-verifier-p2: read <brief> and do what it says.`), and
  `backends/omnigent.md` asks for titles that name the issue or PR.

## 0.19.0 - 2026-10-16

A chief of staff, an optional session the owner talks to while leads do the work (#179).

- New skill `chief-of-staff`, explicit-only (`/chief-of-staff` or a direct request): it sorts
  each owner message, starts one top-level lead per independent ask with the owner's words
  quoted, relays follow-ups, follows the leads with the detached `supervise --registry` job
  and reports their results, questions and stalls. A lead behaves the same with or without
  one, and every session started without it is a lead, as before.
- With Hindsight configured (`~/.hindsight/coding-agent.json`), the chief recalls and retains
  the owner's preferences and standing decisions per repo (`scripts/memory.py`). Workers and
  verifiers get no memory, and `verifier.md` says a verifier reads none.
- `omnigent_agent.py start` and `run` take `--workspace <dir>`: a lead for a change across
  sibling repos works in their parent, its report under the starter's `tmp/loop/`. Without
  it nothing changes. `lead.md` says each PR still follows its own repo's `docs/agents/`.

## 0.18.3 - 2026-10-15

A waiter takes a child's report only once it is final (#165), and a taken title no longer
fails a start (#174).

- `run`, `send` and `wait` count a report only once the child's turn has ended and the file
  is unchanged since, and read it again before returning it: a child can rewrite its report
  until then (a verifier revising its verdict, a lead writing progress at its report path).
  Omnigent can lose a turn end (kzarzycki/omnigent#4), so a report quiet for 10 minutes
  together with the session's history counts too. The supervisor's `report written` follows
  the same rule.
- The brief's preamble, `orchestrating-agents` § Rules and `lead.md` § Report say the report
  path holds the final report, written once at the end, and progress goes to another file.
- A create Omnigent refuses with 409, a title an earlier child of the same parent holds
  (archived ones too), tries the next free `<title>-r<n>`, the sequence the abandoned-start
  retry uses, and prints the title it used.

Starting a lead the owner can open (#152).

- `omnigent_agent.py start --top-level` starts a lead as a top-level session in the repo's
  project, which the owner opens from the sidebar and whose children report to it, not to
  the session that started it (#152). Its brief says only the owner's quoted words
  approve, and it asks the owner in its own session (`USER NEEDED`) instead of writing a
  question; `run` refuses the flag. Without it, `start` and `run` are unchanged.
- The one-line message naming a brief file reads "Your brief is the file …", no longer
  naming the lead as its sender.

Starting and collecting agents is its own skill, `orchestrating-agents` (#151).

- `engineering-loop/orchestration/{native,omnigent,herdr-link}.md` are now
  `orchestrating-agents/backends/`, and `engineering-loop/scripts/omnigent_agent.py` is
  `orchestrating-agents/scripts/omnigent_agent.py`: a brief or command that names the old
  path names the new one. Installed skills are siblings, so from the loop's folder it is
  `../orchestrating-agents/scripts/omnigent_agent.py`.
- The backend choice and the "Reports are files" rule moved from the loop's SKILL.md to the
  new skill, which also states questions as files and that whoever starts a child collects
  it. The loop keeps its roles and points at the new skill.
- `operating-omnigent` now covers the Omnigent install and its raw `sys_*` tools only.

Fixes.

- `supervise --registry` counts a verifier's report only with its `SATISFIED:` line, as
  `wait` does: a registry line carries a `verdict` field, written by `run` and `start` for a
  verifier role and by `send --verdict` (#167).
- `approvals.py land` waits on a head no check ran on instead of crashing on its null
  `statusCheckRollup` (#172).

## 0.18.2 - 2026-10-14

A finished sub-agent no longer takes its lead down with it (#163).

- `run`, `wait`, `reap` and `start`'s abandon path end a sub-agent's terminals and leave it
  unarchived, where they used to unbind and archive it. The child's turn-end idle bound it
  back to the parent's runner, and the archive's delayed stop then stopped that shared runner,
  so the lead was revived without its context (kzarzycki/omnigent#5). A top-level session is
  archived as before. `reap` prints `archived` or `ended` for each session it finishes, and
  operating-omnigent's Archive row says never to archive a sub-agent.

`omnigent_agent.py supervise --registry` supervises sessions from a process that outlives its
caller (#158).

- `supervise --registry <file> [--notify <session>]` runs until stopped, re-reading the file's
  `session=report` lines each poll. It prints every line with the local time and, with
  `--notify`, posts it into that session as `Supervisor: <line>`, reviving a reaped one first.
  Lines wait in order until posted, so a failed post delays a line but loses none, and a
  terminal event drops the session's line once its own line is posted, unless a newer brief
  armed it again meanwhile. Errors and a quiet `--timeout` window are logged and never stop it.
- `run`, `start` and `send` arm the registry (`--registry`, else
  `$OMNIGENT_SUPERVISE_REGISTRY`) once their message is in the history; `run`, `send` and
  `wait` disarm it when they return the report or a question. A line carries the session's
  brief files after the report, each after a tab: `start` writes its `<report>.brief`, and
  `send` appends its message file.
- After a revive, which can drop a session's context, `supervise` sends it one line naming its
  brief files (the registry's, else `<report>.brief`) and the report it owes, in place of
  nothing. Like the resume line, it is no instruction, so a report written for the brief still
  counts. A failed send of it is tried again at the next look.
- Silence counts the session's children: a lead waiting on its own worker or verifier
  gets no resume line while a child of it was updated within `--silent-seconds`.
- A resume line already in the history counts as sent, so a restarted supervisor gives up on a
  session still silent after it instead of sending a second.
- `orchestration/omnigent.md` shows how to run it detached under launchd or a systemd user
  unit; the chief-of-staff passages and `lead.md` § Waiting use it in place of
  in-session watchers, which die with the session.
- A regression test that one-shot `supervise` reads no other session after a caller event
  (#156).

The per-thread role is the lead (#150).

- `coordinator.md` is now `lead.md`, and the loop's files call the role "lead": most
  multi-agent systems use "coordinator" for the project-level agent, the layer a chief of
  staff fills. A brief that names `coordinator.md` names `lead.md` now.
- SKILL.md, Roles: a session whose brief names no role is the lead.
- `lead.md` opens with one PR per story, as its Branch step and issues.md, Epics already
  said.

## 0.18.1 - 2026-10-14

`omnigent_agent.py supervise` keeps a stalled session from going unnoticed (#154).

- `supervise <session>=<report>...` checks that sessions owing a report are alive: it
  revives a reaped runner in place, sends one resume line to a session silent past
  `--silent-seconds` (default 1800), and exits once one reports, asks, blocks, fails or
  is given up on. A chief of staff supervises its coordinators with it, since Omnigent can
  lose a sub-agent coordinator's turn end and leave it `running`.

## 0.18.0 - 2026-10-14

`land` works on a private repo on GitHub's free plan (#145).

- GitHub answers the rules read there with a 403 naming its plan: `land` reads that as no
  required checks, merges pinned to the head once its proofs hold, never asks for
  auto-merge, and says GitHub enforces nothing on the base. Any other error still fails.
- The consumer e2e test's fixture repos turn off git's auto-maintenance, whose background
  repack removed loose objects while the local clone copied them (#144).

A project may let a person work outside the loop (`Opt-out: allowed`).

- With the line `Opt-out: allowed` in loop.md, `check merge` reads a PR with no loop trail
  (no verifier review, no `Approved: spec` record or `approved:spec` on an issue it links,
  no `Reverts #<n>` line, not an exempt bot PR) as outside the loop: one line saying so,
  exit 0, so the approvals workflow posts success and its author merges it their usual way.
  `land` prints the same line and exits 1, so the loop never merges it or turns auto-merge
  on. A developer opts out with `Engineering loop: off` in their personal instructions.
  Without the line nothing changes (#134).
- SKILL.md, Adopting the loop, and coordinator.md, Land, cover a repo without a merge
  queue (#137): the same ruleset without the queue, and `land` merges directly or by
  auto-merge.
- `docs/agents/issue-tracker.md` takes an optional `## Board` mapping loop columns to the
  board's, one list item each, such as ``- `Build` is `In progress` ``; several loop columns
  may share one board column (#135). `board.py <issue> <column>` takes the loop's name and
  sets the mapped board column, and `board.py column` prints the loop's name, the earliest
  of those sharing the board's status. Without the section nothing changes.

Practices proven in a project's local workflow, now the loop's.

- A child that idles saying it is waiting gets a background wait from the coordinator on
  its process or log, which asks for the report when it fires; a worker never ends a turn
  on a wait (coordinator.md, Waiting; worker.md).
- Every proof log starts with `git rev-parse HEAD` and the command that produced it, and
  the verifier treats a proof whose SHA isn't the reviewed head as missing
  (worker.md, Report; verifier.md).
- Anything an agent writes under a person's GitHub account opens with `> 🤖 AI`; the
  records `approvals.py` posts keep their format, and its `## Spec`/`## Plan` lookup skips
  a leading marker line (github.md, Posting under a person's account).

The owner approves only the critical specs (`spec: auto`, #133).

- loop.md § Approvals takes `spec: auto`: every spec a writer opened, epics included, is
  approved by policy, except one a risk rule matches (a `risk:` line, or a conditional
  `merge:` or `spec:` line), which waits for the owner's
  record and `approved:spec`. The gate judges the rules on the labels of the issue and the
  PR and the PR's files (at `check build` the files pushed so far), and `check` says which
  rule holds the spec. Under `spec: auto` a risk rule holds the spec instead of the merge,
  so no `approved:merge` wait comes from it; `risk:high` and the cap still hold the merge.
  `spec: auto unless risk` keeps its meaning.

The owner signs off a landed change in use where loop.md asks for it.

- loop.md § Approvals takes `signoff: <condition>` lines, read and judged as `risk:` rules
  are. The spec records `Sign-off: owner` or `Sign-off: none`; `owner` asks for a sign-off
  where no rule does, and `none` never waives a matching rule.
- `Implements #<n>` is a PR link that leaves the issue open, like `Part of`. Where loop.md
  has a `signoff:` line, `check merge` and `land` need `Implements` for an issue that waits
  for a sign-off and a closing keyword for any other (`Part of` suits both). Without the
  line nothing changes.
- After landing, an `Implements` issue moves to the new board column `Sign-off`, between
  `Verify` and `Done`, and the owner closes it once they have tried it
  (issues.md, Sign-off). `board.py column` orders it there.

## 0.17.0 - 2026-10-09

A bot's lock- or manifest-only PR merges without a verifier review (#106).

- loop.md § Approvals takes `bot: <login> <condition>`, such as
  `bot: dependabot[bot] path uv.lock or path pyproject.toml`. `check merge` and `land`
  waive the verifier review for a PR that bot opened when every file it changes matches
  the condition on its path and every commit is the bot's (authors, and a committer that is the bot or no account);
  any other file, a renamed or copied one, or a person's commit or rebase needs the review as usual. Without the line, no PR is
  exempt. The login matches with or without `[bot]`, and only a bot account.
- The verifier resolves no review thread.
- The merge gate does not enforce reviewer family (#118): the verifier names its family
  in the review heading for the record, and the gate checks only that the newest pass on
  the head is satisfied, whichever family wrote it. The coordinator still prefers a
  verifier of the other family when it is installed and within quota; otherwise a fresh
  same-family session is the normal path, and the PR body names which ran.
- An unreadable `cap:` line in loop.md, such as `- cap: 3 passes`, is refused at the
  start of `check` and `land` (#119): the refusal is the only line printed, and `land`
  marks no draft ready. Before, a PR a risk rule or `risk:high` already held never read
  the cap, so `check merge` printed its proofs and `land` marked the draft ready.
- The cap hold (0.14.0) applies when a verifier review at the cap or later left a
  blocker or major open, and also when it says `SATISFIED: no` with none open; the hold
  line says "was not satisfied or left a blocker or major open".

## 0.16.0 - 2026-10-09

Labels as code: `area:` and `kind:` labels, synced with in-place renames, and the
assignee says whose an issue is (#103).

- Categories are `kind:bug`, `kind:enhancement`, `kind:chore` and `kind:documentation`;
  `documentation` is renamed to `kind:documentation`. A component's label is `area:<name>`, an extra category's
  `kind:<name>`. `approvals.py` reads only these names, and loop.md conditions
  (`component billing`, `category bug`) match them. Migration, since the old names no
  longer count: upgrade the pack, run `python3 scripts/labels.py --dry-run` from the
  installed engineering-loop skill in the project's checkout, then without the flag, then
  rerun `approvals.py check`. `setup:github` runs the sync only once project-templates
  wires it in, a follow-up.
- `scripts/labels.py [--dry-run]` syncs the repo's labels with the loop's set and
  `docs/agents/issue-tracker.md`: renames in place (the loop's map, the tracker's new
  `## Renamed labels`, and each bare component name), creates and updates the listed
  labels, deletes an unlisted one only when no issue or PR carries it, and never renames,
  folds or deletes Dependabot's or one whose name has a comma.
- `approvals.py check build` refuses an issue assigned to anyone but its spec's approver;
  once every build proof holds it assigns the approver where no one is, and the PR its
  issue's assignees, recording each assignment in a comment first. `approvals.py release <issue>` removes, on parking or dropping, only
  an assignee the loop added.

## 0.15.0 - 2026-10-09

Approvals come only from people, and risk is defined in one place (#121).

- `approvals.py approve` takes only `--by owner`: a person's record, written on their
  word. `check` and `land` no longer ask for a coordinator record, and an agent's earlier
  record approves nothing. Without a loop.md policy line every spec needs the owner's
  current record and `approved:spec`; a plan needs them only where a `plan:` rule asks.
- loop.md § Approvals `spec: auto unless risk` approves by policy, with no record or
  label, the spec of a `bug`, of an issue with a `Found while #<n>` line, or of a native
  sub-issue of an epic with the owner's current approval, opened by an account whose
  collaborator permission is admin, maintain or write. `needs-owner` still blocks.
- `risk: <condition>` lines define high risk, with the conditions `merge:` rules had. A
  change is high risk when `risk:high` is on the PR or an issue it closes, a risk rule
  matches, or the cap was reached with a core finding open; only then does the merge wait
  for the owner's `approved:merge`, and the wait line says why. `merge: auto unless risk`
  states the default. When the gate infers high risk, `check merge` and `land` add
  `risk:high` to the PR; a failure to add it is reported, never fatal.
- Migration: a `merge: <condition>` line reads as a `risk:` rule until the project
  rewrites it, so its paths still hold merges for the owner. A `spec: <condition>` line
  reads as one only beside `spec: auto unless risk`; without that line the owner approves
  every spec already, so a legacy `spec: always` holds no merge.

## 0.14.0 - 2026-10-09

- `scripts/gate.py` and `approvals.py record-check`, the old names kept through 0.13, are gone:
  run `approvals.py` and `approvals.py local-ci`.
- No fix lands without review (#116). `approvals.py land` merges only a head with a
  satisfied verifier review on that exact commit: any commit after the verdict, a merge of
  main included, needs a verifier pass of its own. A head that only took in main's changes
  to other files is no longer covered.
- The cap is defined once, in SKILL.md § The cap: 5 passes by default, or a project's own
  through a loop.md line `cap: <n>`, which `approvals.py` reads too. When a review at the
  cap or later left a blocker or major open, the owner decides: a fix and one pass past
  the cap, scoped to the open items, or leaving the code untouched. `land` holds such a PR
  for the owner's `approved:merge` label, added after the head's push. When the cap's last
  pass leaves only minor or edge findings, they go to the ledger and an issue, and the PR
  lands with no owner stop.

## 0.13.1 - 2026-10-09

- `approvals.py land` reruns a stale `loop:approvals`. Resolving a review thread starts no
  GitHub Actions workflow, so the FAILURE the approvals workflow posted while a thread was
  open stayed on the head and `land` exited 3 for good. When every proof holds and that
  status is the only required check that is red, `land` reruns the Actions run its target URL
  names (`gh run rerun`) and exits 3. A run still in progress is waited on, and a status naming
  no run of this repo is reported; neither is rerun.

## 0.13.0 - 2026-10-09

The merge contract's landing (kzarzycki/agent-skills#108, #106) and the launcher's resilience (#93).

- `approvals.py land <pr>` is the one way an agent lands a PR. It refuses (exit 1, the PR
  untouched) on a missing proof; marks a draft ready and waits (exit 3: run it again once CI
  starts); then merges at the head (`gh pr merge --squash --match-head-commit`), or turns on
  auto-merge pinned to the head while only required checks are pending. Required checks are
  the base's rulesets and branch protection; a base requiring none needs every check green,
  and a draft's skipped run is no result.
- The gates are the merge approval. A loop.md § Approvals `merge:` rule (same conditions as
  `spec:`, plus `path <glob>` read from the PR's files) asks for the owner's `approved:merge`;
  a `merge:` condition the gate can't read asks for it too. With no rule, no label is needed.
  A project that wants the 0.12.0 behaviour, a label on every merge, writes `- merge: always`.
- The verifier's verdict is a GitHub PR review: `approvals.py verdict <pr> <report>` posts the
  report on its reviewed `Head:` with one inline thread per finding, and refuses a report it
  can't parse. `check merge` and `land` need the newest pass's reviews on that commit
  satisfied with 0 blocker and 0 major, on the head or with only a main merge since that
  touches no PR file; no unresolved review thread; and no person's latest
  `CHANGES_REQUESTED`. A verdict comment no longer counts. Only a review by the PR's author
  or the viewer counts.
- A repo without `docs/agents/loop.md` has no rules: each issue the PR names needs
  `approved:spec` and no `needs-owner`. The loop's files are read from the checkout's top
  level, so a run from a subdirectory reads the same rules.
- The loop docs: land only through `approvals.py land`; every fix after a verdict, a note's
  included, gets a delta pass, and after pass 3 a delta check; who replies on and resolves
  which review thread (`ADDRESSED`, `WONT_FIX`, `INVALID`).
- `gate.py` and `record-check` stay as aliases until 0.14.0, which removes them.
- `omnigent_agent.py watch` exits as soon as a session ends a turn, blocks on a prompt or
  fails (#97); worktrees nest inside the project and the agent that starts them (#101); the
  launcher retries idempotent reads, never doubles a timed-out create and nudges a turn that
  ended without its report (#107); `send` revives a reaped session in place (#111).

## 0.12.0 - 2026-10-07

The merge contract's agent-skills part (kzarzycki/agent-skills#102, #104).

- `scripts/gate.py` is `scripts/approvals.py`, with the subcommands `check`, `approve`,
  `verdict` and `local-ci`. `local-ci` (formerly `record-check`) runs `mise run check:all` on a
  clean checkout at the PR head for a `CI: none` repo; a record of the old `mise run check`
  still counts. `gate.py` and `record-check` stay for this release as aliases with the same
  output and exit code.
- `check merge` reads one check, the aggregate `check` on the head, counting only its newest
  run per workflow, so a red advisory check or a run cancelled by a newer green one no longer
  blocks (replaces #76).
- The merge approval is the owner's `approved:merge` label, added after the head's push (dated
  by GitHub's repository activity) and still present; the `Approved: merge` record and
  `approve merge` are gone, and a loop.md `merge:` rule is ignored. `check merge` exits 1 when
  a proof is missing (Evidence, the verdict, an approved spec) and 3 while it waits for a green
  `check` or the label, which the approvals workflow posts as a `pending` `loop:approvals`
  status. The coordinator asks the owner only once `check` is green, turns on auto-merge with
  `gh pr ready` (`gh pr merge <pr> --auto --squash --match-head-commit <head>`), and deletes
  no remote branch: GitHub deletes the merged head branch.
- `headed()` matches a comment's whole first line, so `## Specification notes` is no `## Spec`.
- `approved:spec` is the ready state and `ready-for-agent` is gone: `check build` needs
  `approved:spec`, a size, a category and a component, and no `needs-owner`. A `wayfinder:`
  ticket needs `approved:spec` in place of `ready-for-agent`. Category, component and size
  names are read through one rule, `label_names`: the loop's fixed set plus
  `docs/agents/issue-tracker.md`.
- `board.py column` prints the later of the issue's board column and the one its labels give,
  so an issue with `approved:spec` reads `Ready`.
- The loop docs use the contract's task names (`check`, `check:all`, `test:changed`,
  `loop:approvals`, `setup:dev`, `setup:github`, `pr:demo`, `agent:sync`) and point at
  `mise tasks ls` for what each does. Main requires exactly `check` and `loop:approvals`;
  hooks are git hooks, and the proofs leave the push. The verification flow: the worker runs
  `test:changed` while iterating and `check` before each push; the PR goes ready once
  `check` passed and the verifier is satisfied; a check red after ready goes back to draft
  and to a worker with the failing log, while the coordinator waits on one
  `gh pr checks --watch --fail-fast`. An epic's stories are filed before its approval is
  asked for, and each has its own approval.

## 0.11.0 - 2026-10-06

- Human review findings on an open PR (`coordinator.md`, Land): each review comment is triaged
  with One concern per PR. A blocker, a major or a bug the PR introduced is fixed on that PR's
  branch; anything else is answered on its thread and waits for the merge. The fixes follow the
  review trail below: the PR goes back to draft, each fix is a pushed commit replied on its
  thread, and the PR is ready again after a verifier pass. No fix cascades down a stack: a merge
  queue tests each PR on top of main, and a stacked PR follows Stacks are one deep.
- Review trail on the PR (`SKILL.md`, `coordinator.md`, `worker.md`, `github.md`): the PR opens
  as a draft with the first push, and each verifier pass is posted as a PR review with one inline
  comment per finding, labelled `Verifier (<family>), pass <n>`, and the verdict in its summary.
  Each fix is its own commit, replied on its thread with the SHA and the thread resolved; a
  deferred finding's reply links its issue. The PR goes ready once no blocker or major is open,
  and is squashed on merge. `github.md` gives the `gh api` calls (review, thread reply,
  `resolveReviewThread`).
- Adopting the loop (`SKILL.md`): a new repo starts from kzarzycki/project-templates with
  Copier (`loop_enabled`); an existing repo copies the rendered CI workflow, `gate.yml`,
  pre-commit and pre-push hooks, mise `check`/`gate`/`merge-queue` tasks and main's ruleset from
  there, so the pack keeps no second copy. CI skips draft PRs and runs on `ready_for_review`;
  merge-queue and push runs are unaffected, and the local pre-push gate checks a draft.
- The merge gate lets an exact revert through without a new spec: a PR whose body says
  `Reverts #<n>`, with #n merged and a diff that is file for file the inverse of #n's (line
  order, file status and modes included), skips the spec proofs and the verifier verdict, and
  `approve merge` records `Verdict: exact revert of #<n>`. It still needs Evidence, green CI and
  the merge approvals. A merge rule's owner check reads the union of the PR's issues' labels, so
  a path rule also holds on a PR that names no issue.

## 0.10.0 - 2026-10-06

- Land small and soon (`SKILL.md`): every PR branches off `origin/main` and merges as soon as
  its gates pass. An epic lands as one PR per sub-issue, each off main, with no epic or
  integration branch; work not yet usable lands unexposed (no entry point, or a flag the user
  docs don't name), and the sub-issue that exposes it comes last.
- Stacks are one deep, and only on a PR already in Land; the stacked PR moves onto main the
  moment its base lands, moved by the coordinator only when it owns that PR (otherwise a
  comment naming the merge SHA asks its owner). A stacked PR keeps its own `Closes`; they are
  copied to the base only when the base contains the stacked work.
- One concern per PR, rewritten: a finding goes on the open PR's branch only when it makes that
  PR wrong or unmergeable; anything else, a satisfied verdict's note included, waits for the
  merge and starts from main. Never push to a PR someone else owns. A process fix that makes
  the open PR wrong follows this rule too, instead of going to a separate PR.
- Revert first: when main goes red after a merge, or a merged change proves wrong in use, the
  first fix is a revert PR off main, and the reverted PR's issues reopen. Accept starts by
  reading main's push run on the merge SHA.
- Waiting: while a PR waits for CI, the coordinator moves other ready items forward.

## 0.9.2 - 2026-10-05

- Epics (`issues.md`): an epic is an issue whose goal is an outcome the owner tracks, with
  its work items as native sub-issues and the `epic` label. Two levels only, so every work
  item shows under its epic on the board. Convert an issue whose spec already states the
  outcome rather than file a new one; the epic closes when its sub-issues are done.
- Triage places what a PR leaves unfixed by one test: would closing the issue without it be
  dishonest? Within the issue's acceptance, the issue stays open and the PR says `Part of #n`.
  Outside it, a new issue with a `Found while #n` line, attached as a sub-issue of the
  originating issue's epic, so follow-ups no longer grow into loose chains.
- A change to an approved spec's scope or acceptance removes `approved:spec` and parks the
  issue with `needs-owner`; a wording fix keeps the label.
- Landing: closing keywords fire only on a PR merged into the default branch, so a stacked
  PR's issues are closed on the PR that reaches it, or by the coordinator. A replacement PR
  carries `Closes` for every issue the replaced one closed.
- `gate.py` reads `Part of #n` as naming the spec, like `Closes #n`, so a PR that leaves its
  spec open still passes the gate.
- `github.md`: setting a parent with `addSubIssue`, after reading the current one, since an
  issue has at most one and a repeated add is refused.

## 0.9.1 - 2026-10-05

- Upstream intake, mattpocock/skills `d81f3a1..24fe0ef` (v1.3.1).
- `ask-matt` (ported): once `/diagnosing-bugs` has fixed a bug, run `/retro` in the same
  session to ask what would have prevented it; a finding that no seam can lock the bug down
  still goes to `/improve-codebase-architecture`.

## 0.9.0 - 2026-10-03

- New owned skill `demo`: record a change a user sees running at the PR's head and post the
  video to the PR. `scripts/post_demo.sh` posts one `## Demo` comment with the videos attached
  (`gh pr comment --attach`), refuses a checkout that is not the PR's head, and minimizes
  earlier demo comments as outdated. One file per recorder, read only for the surface in play:
  VHS for a CLI or TUI, Playwright for a web page, `simctl` for the iOS simulator,
  `screenrecord` for Android. When to record is the project's rule, not the skill's.
- `pr`: Evidence names the demo when one was recorded, or suggests one when the project's
  instructions call for it. A repo PR template's headings win; the sections fit under them.
- `ask-matt` routes `/demo`.

## 0.8.3 - 2026-10-02

- An approval names the spec or plan by its last edit, as GitHub's edit history shows it
  (`Spec: as edited 2026-10-02 14:35:27 UTC`), instead of a 12-character hash a person could
  not check against the text. Any edit still needs approving again. Records written with the
  hash no longer count: an issue approved before this release needs one more approval.
- A re-approval says why: `The spec changed after the last approval, so it was checked
  again.` (the head moved, for a merge). `approve` then minimizes, as outdated, each earlier
  record it supersedes, so the issue shows only the approvals that count. Another approver's
  record of the same version stays open. Minimized comments stay readable, and the gate still
  reads them.
- A merge path rule reads every file a PR changes, not just GraphQL's first 100. Past that page
  the gate lists the files through the REST API, up to GitHub's 3000. Adopting the template
  commits the synced agent files, so the adoption PR alone was refused as "more than 100
  changed files".

## 0.8.2 - 2026-10-02

- Under `CI: none`, the merge proof is a record, not a sentence. `gate.py record-check <pr>` runs
  `mise run check` on a clean checkout at the PR head and posts `Local check passed` with the
  head commit. The merge gate needs that record on the current head. It no longer reads
  `## Evidence` for `mise run check` and `exit 0`. That matching was brittle, and it was not
  tied to the head, so a line written for an earlier commit still passed.
- Instructions are code for the further-pass rule (coordinator step 7). A fix after a satisfied
  verdict skips another verifier pass only when it changes nothing an agent or tool reads. A
  skill, role file, brief, `AGENTS.md`, `docs/agents/` file or prompt needs the pass.

## 0.8.1 - 2026-10-02

- `gate.py` reads a PR's changed files only when a merge rule has a path condition. A PR with
  more than one page of files is refused only then, and at the merge point. Before this, every
  build check refused such a PR, and the pre-push hook refused the very push that would shrink
  it, because the hook reads the PR as GitHub last saw it. `approve merge` now refuses the
  unread page too, instead of judging a path rule on a truncated list.
- A project without CI says so with the line `CI: none` in `docs/agents/loop.md`. Its merge
  proof is then the PR's Evidence naming `mise run check` with exit 0 on the head, in place of
  green CI checks. Projects with CI keep the CI proof.

## 0.8.0 - 2026-10-01

The engineering loop ships as a method any project turns on. No upstream change.

- New owned skill `engineering-loop`: intent, spec, build, gates, proof,
  verify, land, with coordinator, worker and verifier roles, triage, the
  three-pass cap and the landing rule. It names no project: each step reads
  `mise run check` or the project's `docs/agents/loop.md`, `issue-tracker.md`
  or `coding-standards.md`, and a test fails on a project term. It carries
  the generic coding standards, the owner-on-the-loop rules and status
  conventions, and three stdlib scripts: `board.py` (move a ticket),
  `gate.py` (the proof gate) and `omnigent_agent.py` (its project defaults to the
  repo's name).
- A project configures the loop rather than forking it: `loop.md § Practice`
  names the skill that fills a stage (defaults: `grilling`, `to-spec`,
  `code-review`, `pr`), and `§ Approvals` lists the spec, plan or merge points
  that wait for a person. The loop keeps the state, the gate, the cross-family
  verifier and the merge whatever the practice.
- Every step leaves proof on GitHub, and `scripts/gate.py check <build|merge>`
  checks it: the issues the PR closes are specced and labelled (what
  `spec_gate.py` did), each approval is recorded, and at merge the PR has its
  `## Evidence`, a posted verifier verdict, green CI and a merge approval on its
  head. The coordinator approves spec, plan and merge itself (`gate.py
  approve`), the verifier only gives the verdict (`gate.py verdict`), and a
  `§ Approvals` rule adds a person's approval, made by adding the
  `approved:<point>` label. A project runs the gate as `mise run gate`, adding
  its own checks; the loop, a pre-push hook and CI call it. A step is skipped
  only when the owner asks: `size:XS` no longer skips the verifier.
- Orchestration backends: native subagents (the default), Omnigent and
  herdr-link, picked by `Orchestration backend: <name>` in personal
  instructions. Without the other model family, the verifier is a fresh session
  of the same family and the PR body says `verifier: same family`; the brief
  never says so.
- The loop's issue conventions (states, categories, sizes, board columns) are
  its `issues.md`, and its `github.md` does them on GitHub (`gh` operations,
  board moves, the issue-batch protocol the setup skill used to write). Both
  are read in place, never copied: a project's `issue-tracker.md` holds the
  line `Tracker: GitHub (engineering-loop's github.md)`, its Components, what
  is Never on GitHub, and optionally Extra labels and Extra categories.
- Removed `setup-engineering-workflow-for-apm`: the project template writes
  `docs/agents/`, and two writers drift apart. `to-spec`, `triage`,
  `to-tickets`, `implement-spec`, `ask-matt`, `code-review` and `wayfinder`
  send a user without `docs/agents/issue-tracker.md` to create it. Drop
  `/setup-engineering-workflow-for-apm` from your own instructions.

## 0.7.0 - 2026-09-30

Upstream `mattpocock/skills` `c55ee46..d81f3a1` (release v1.3).

- Removed `resolving-merge-conflicts`, as upstream did in `daa01d8`: nothing
  replaces it, because the agent works through a merge or rebase conflict
  without a dedicated skill. Drop any reference to `/resolving-merge-conflicts`
  or the `resolving-merge-conflicts` skill from your own instructions.
  `ask-matt` and `implement-spec` no longer name it.
- The domain glossary is now `GLOSSARY.md`, and the multi-context map
  `GLOSSARY-MAP.md`, in every skill that reads or writes it, and
  `domain-modeling`'s format file is `GLOSSARY-FORMAT.md`. The skills no longer
  look for `CONTEXT.md` or `CONTEXT-MAP.md`: `git mv` an existing one to the new name.
- `implement-spec` (ported): the goal is one integration branch with every ticket
  resolved the way the tracker closes work. A draft PR opens only when the
  tracker closes work through PRs or the user asks, after the first merge. Each
  implementer checks its worktree's base, builds with `tdd` and merges the
  integration tip before reporting. Upstream's description wording is declined.
- `ask-matt` (ported): `retro` closes the main flow, and `implement-spec` is
  routed as landing on one integration branch.
- `pr` (ported): the glossary rename. Upstream's reformatted component-tree
  example and CREDITS rewording touch text the tuned skill had already condensed away.
- `codebase-design`, `diagnosing-bugs`, `domain-modeling`,
  `improve-codebase-architecture`, `tdd`, `triage`, `wait-what` (ported): the
  glossary rename only. `grill-with-docs`, `to-spec`, `to-tickets` and the setup
  skill take the same rename for consistency.
- Upstream graduated `implement-spec`, `pr` and `retro` out of `in-progress/`;
  the package now imports them from `skills/engineering/`.
- A skill is retired by removing its `vendir.yml` entry and its overlay: the
  refresh prunes the leaf and proposes a minor version. A configured leaf that
  vanishes upstream still stops the refresh.

## 0.6.2 - 2026-09-30

- `to-spec` writes the spec into the issue the conversation started from, under
  the original text quoted in full, instead of filing a second issue. The
  project's `docs/agents/issue-tracker.md` can send it to a comment where an
  issue's body is not the skill's to rewrite. With no issue it files one, as before.

## 0.6.1 - 2026-09-29

- `code-review` hands each reviewer this skill's path and its section instead
  of a paraphrased brief, which had dropped the smell baseline and report rules.
- The tuning contract says the same for any skill that prescribes a subagent's
  brief.

## 0.6.0 - 2026-09-23

- Tuned all 26 imported skills, the setup overlay and the owned skills
  (`audit-third-party-software`, `context-extractor`, `operating-omnigent`)
  for current models:
  generic advice, pressure language and step choreography removed, delegation
  left to judgment, harness- and tracker-neutral wording. Formats, gates and
  cross-references are kept. Supporting files that only repeated their skill
  were merged into it.
- Tuned skills are now owned overlays. The GitHub issue-batch patch is folded
  into `to-tickets` and `wayfinder`, and the patch series is gone.
- Upstream intake is now semantic: an upstream change under a tuned skill stops
  the refresh with its delta saved until a port or decline is recorded in
  `upstream-intake.yml`. The first intake ports upstream `c55ee46` (Merge
  Danger template in `pr`).
- An agent routine (`ROUTINE.md`), meant for a scheduled host: it ports
  upstream, has a fresh-context reviewer check the ports, merges its own PR and
  tags the release. It replaces the scheduled deterministic refresh,
  which followed upstream stable tags (none since `v1.2.3`) and could not port;
  that workflow and its publication tooling are deleted.
- Version bumps count from the last `engineering-v*` tag, so a port, review and
  rerun loop bumps once per release.
- `upstream-intake.yml` is validated on every check, and the package-test
  hang guard is 300 s (the APM install tests take about 110 s).
- Refreshed upstream from `74ca5fe` to `c55ee46` (`v1.2.3-54-gc55ee46`).
- Behaviour changes: `to-spec` publishes through the tracker document's issue-batch rules;
  `code-review` diffs against the merge-base and includes uncommitted and
  untracked files; `tdd` treats seams agreed in the spec as confirmed;
  `context-extractor` proposes edits to the sources when agent files are
  compiled (for example through APM); the third-party audit drafts the vendor issue and never files it.

## 0.4.0 - 2026-09-01

- Imported four skills from the upstream `in-progress` bucket at
  `6654f6b60cd9d5be8b54c6fafe44346dabeb3b76`: `claude-handoff`,
  `implement-spec`, `loop-me`, and `retro`.
- These are upstream beta: that bucket is excluded from the upstream plugin and
  its skills may change or disappear without warning. A disappearance fails the
  refresh rather than silently dropping a skill, because the removal check
  compares the committed inventory against what vendir produced.
- No change to the eighteen previously imported skills or to the source commit.
- Replaced the `/setup-matt-pocock-skills` rename patch with a literal
  substitution rule in `upstream.yml`, applied before the ordered patches. The
  shipped output is unchanged; the rule survives upstream rewording that a
  context diff did not.

## 0.3.1 - 2026-09-01

- Refreshed the reviewed Matt Pocock skill inventory from
  `84fdeffd12f2ee307994d1eb6feb48173b6e0502` to
  `6654f6b60cd9d5be8b54c6fafe44346dabeb3b76` (`v1.2.3-39-g6654f6b`).
- Adopted an untagged upstream snapshot: upstream has published no stable tag
  since `v1.2.3`, so `stable_baseline_tag` stays `v1.2.3` and the package
  version magnitude comes from the inventory delta (no skills added or
  removed, so a patch bump).
- Rebased both downstream patches onto the upstream rewording (repo-wide
  em-dash removal and the "tell the user to run" setup phrasing).
- No inventory change: the same eighteen imported skills, all seventeen
  changed in content.

## 0.3.0 — 2026-08-09

- Refreshed the reviewed Matt Pocock skill inventory from
  `2ab958093e83e0ec752e6c1c5932da465bf23e0c` to
  `84fdeffd12f2ee307994d1eb6feb48173b6e0502` (`v1.2.3-2-g84fdeff`).
- Added the upstream `wizard` skill and adopted upstream updates across the
  existing engineering inventory.
- Rebased the downstream APM setup patch while preserving the package's
  repository-owned compilation and audit contract.

## 0.2.0 — 2026-07-30

- Added an independent APM manifest targeting Claude Code and Codex.
- Added the `engineering-v0.2.0` package tag contract and `^0.2.0` consumer
  dependency.
- Preserved native Claude marketplace installation through
  `engineering@kzarzycki-agent-skills`.
- Removed the floating `mattpocock-skills` marketplace entry in favor of the
  reviewed, pinned inventory shipped by this package.
