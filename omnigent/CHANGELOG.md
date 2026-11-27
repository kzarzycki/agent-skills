# Changelog

## Unreleased

New entries are files in [changelog.d/](changelog.d/), one per issue, until a release moves
them here.

## 0.1.27 - 2026-11-27

- Land's reap deletes the `claude/…` branches a PR's worker sessions pushed (each session record's `git_branch`), keeping a branch that is an open PR's head or whose worker is still running; a refused delete is said, never an error. The gate signal of `wait-for --until gate` reads `refs/loop/gate/` records first, then `loop-gate/` branches (#2821).

## 0.1.26 - 2026-11-27

- omnigent-agents: `reap --force` finishes a session whose runner has gone away: when the `interrupt` is not queued and the session stays running, `Omnigent.interrupt` sends the server's `stop_session` event, so `start-lead` no longer refuses a new verifier on that PR (#2808).

## 0.1.25 - 2026-11-27

- omnigent-telemetry: the report reads `GET /v1/usage/telemetry` and `GET /v1/usage` `sessions[].child_usage[]` instead of Postgres: no SQL, no database credentials, `--db-container` is gone and `--max-sessions` is new; sections the server truncated print as gaps, not zeros, and child usage shows beside its parent session without joining any cost (#2805).

## 0.1.24 - 2026-11-27

- omnigent-agents: `reap --merged --pr N` (started by `land`) spares its caller and every session whose `omni.role` is a lead or manager, and still finishes the PR's workers and role-less children (#2794).

## 0.1.23 - 2026-11-26

- omnigent-agents: `start` passes a model unchecked when the host answers its model-options call with HTTP 501 (a current Omnigent host on an ACP harness such as `claude-cloud`), as it did for the older "unsupported for harness" text (#2797).

## 0.1.22 - 2026-11-26

- omnigent-telemetry: `--split-tool` / `--split-label` (or `--values`) compare two sides of sessions by the same metrics, overall and by role; cloud sessions get their own table with their children's usage; Gemini sessions with tokens and no cost show "no price" instead of $0 (#2775).

## 0.1.21 - 2026-11-26

- omnigent-agents: `supervise --install` run from a developer checkout of the pack refuses and names the installed copy to run it from, instead of writing a service that runs that checkout for ever (#2761)

## 0.1.20 - 2026-11-26

- omnigent-agents: an idle session whose `Waits:` names its supervisor is recorded with no event while the owner has an open question card on that supervisor or up its parent chain, since the wait is on the owner's answer; with no open card the wait is still acted on (#2755).

## 0.1.19 - 2026-11-26

- omnigent-agents: `claude-cloud-run` takes the forge's remote from the branch's upstream (else the policy's `forge_remote`, else `origin`) as the gatekeeper does, so a worktree tracking a fork starts its cloud session on the fork's repo; its launch dir sits beside the worktree it serves; the folder-trust check accepts a folder whose parent is trusted; and a `--reference`/`--shared` clone is refused before any session is created (#2710).

## 0.1.18 - 2026-11-26

- omnigent: a lead whose `USER NEEDED` line names a `question_<id>` card that is open on its parent no longer draws the supervisor's "no question card open" event; once the card is answered the usual events resume (#2145).

## 0.1.17 - 2026-11-26

- omnigent: a `--pr` cloud worker started with a supervise registry now gets a followed line, so its supervisor tells its end from its last message and never nudges it toward a host report path (#2718).

## 0.1.16 - 2026-11-26

- `supervise` watches the Omnigent login of its server (#2119): once an hour it runs `omnigent login-status <server> --live` (exit 1 ends soon, 2 cannot renew) and reads `host_auth_rejected.json` in the host data dir, and raises one USER NEEDED event naming `omnigent login <server>` per change of state, noting the return to ok once; a missing or older `omnigent` is logged once and never alerts. Needs omnigent#698; lands after it.
omnigent-agents: the brief sent to every cloud child and the `claude-cloud-run` and `Placement:` text point to engineering-loop's "Where work runs" (renamed from "Where heavy steps run", #2469); the placement rule itself is unchanged.
- omnigent-agents: finds the gatekeeper's script in the installed copy of the pack, never a developer checkout: a checkout (a git tree holding the marketplace file) is searched only where `AGENT_SKILLS_CHECKOUT` is set, as the pack's own tests set it (#2485).
omnigent-agents: the supervisor finds a dequeued PR's lead from the PR's `Owner: <session link>` record, and for a record naming a session its server does not list prints one `owned elsewhere` line and raises no event; a PR with no record is found as before (#2496).
omnigent-agents: a Mergify dequeue over failing checks leaves a `Queue failure` record on its PR (checks with job links, failing tests) from the new `queue-failure` workflow, and the supervisor's dequeue message reads the same `queue_failure.py` (#2497).
omnigent-agents: `wait-on pr <n> --story <m>` records the blocker as GitHub's own "blocked by" link of issue `<m>` and refuses one it cannot watch; the supervisor tells the waiting lead once, "you can queue now", when it closes or merges (#2499).
- omnigent-agents: a PR's `Waiting on:` record past its `Deadline:` with no clearing record raises one `wait-due` event to the owner session its `Owner:` record names, and for another agent tree's session an `owned elsewhere` line and no event; a repo with no such record is unchanged (#2501).
omnigent-agents: `wait-for`'s stall limit for a gate run (a log showing the gate lock) is the project's `timeouts.run`, not 300 s; `claude-cloud-run` prints a `still running` line every minute; a `stalled:` outcome names `--stall` (#2510).
- omnigent: the pack's own CI finds its scripts in the checkout it runs in: a checkout counts when it is the `GITHUB_WORKSPACE` of the job running there, so main's push run, the nightly and the tag check run `nightly.py moved` again (#2560).
gatekeeper: the deny list (`LOOP_DENY_LIST`) lets an Omnigent session link (`<scheme>://<host>[:port]/c/<32 hex id>`) through, so a listed host name inside one no longer refuses a post, and still refuses the same name anywhere else; `gatekeeper.py`, engineering-loop's `nightly.py` and `omnigent_agent.py` now share the one check in `scripts/denylist.py`, and engineering-loop's public-repo rule says session links may be posted (#2571).
- omnigent-agents: a cloud worker's report prompt and SKILL.md no longer ban session links; they ban a host or path outside a full Omnigent session link (#2571).
- omnigent-agents: `--verifier-route gemini` from a cloud VM is refused at once, saying the verifier must be started by the coordinator on a host with an Omnigent server route; engineering-loop's lead.md says a cloud lead asks its coordinator for it (#2572).
- omnigent-agents: a `run` or `start` with `--pr` that reads as a verifier's (`--same-family`, or a title or report named for a verifier) but has no `--role` verifier.md is refused, so a fallback verifier cannot skip the report format `record verdict` reads (#2573).
- omnigent-agents: a verifier's verdict is recorded the same way on every route: `run --pr N` and `wait --verdict --record-pr N` post the collected report through the gatekeeper's `record verdict`, and a failed record ends on a `record verdict BLOCKED:` line in the report and on stderr, exit 1 (#2575).
- omnigent-agents: `send` returns once the message is accepted (delivered, or queued behind the session's current step), with a delivery line and exit 0, instead of waiting past a caller's timeout for the report; `send --wait` (implied by `--notify` and `--verdict`) waits for the report as before (#2578).
- `start --top-level` puts the lead's own session link on a `OMNIGENT_SESSION_LINK=<server>/c/<id>` line right after `AGENT_SIGNATURE=` (the id exists only once the session does), and the lead preamble tells it to give `approvals.py check build` and `claim` that variable, so a cloud lead's claim records its session (#2583).
- omnigent-agents: the cloud child's brief and the supervisor nudges tell it to wait in the foreground with `wait-for --budget 570`, since a finished background task does not wake a claude-cloud session (#2593).
- omnigent-agents: a cloud lead's brief says its manager runs the verifier and that it ends its turn with `READY FOR VERIFIER: PR #<n> head <sha>`; the lead role text no longer has a cloud lead start a verifier (#2610).
- omnigent-agents, engineering-loop: the cloud brief and lead.md say a detached run wakes a claude-cloud session never, though a tracked background task has (probe, #2611); a cloud lead waits in the foreground and ends its turn only once its run has ended, pinned by tests on the lead brief and on lead.md (#2611).
- omnigent-agents: a merge-queue dequeue never goes to a PR's verifier (a followed verifier carrying the PR label was picked before the lead), and a dequeue for a head replaced by a later push goes to no session (#2614).
omnigent-agents: the supervisor routes a lead's `STILL WORKING` on the verifier to its manager at once when no verifier session labelled with that PR is running (`lead gated #N <head>, no verifier running: start one`); a running verifier on the PR still holds the wait. The registry records a verifier's PR, not its head, so the PR label alone decides (#2618).
- omnigent-agents: the supervisor reads a `STILL WORKING` that names a poll or sleep loop of its own as a wait nothing wakes the lead for, so it is nudged, then handed to the manager; a turn end in any wording that names no `Waits:` line and no followed child is flagged to the manager once the deadline passes (`DEADLINE_SECONDS`), and a `Waits:` line naming a live session holds it; tests pin both (#2623).
omnigent-agents: the supervisor reads `STILL WORKING` as a lead's state only where it opens a line, one helper for every reader, and routes a turn that ends on `READY FOR VERIFIER` or `Handback:` as a hand-back whatever it quotes (#2629).
- omnigent-agents: `supervise` raises no dequeue for a conflict once the PR reads mergeable, and a head pushed after a dequeue that names no queue time drops it too (#2646).
- the supervisor sets an issue's `Session` field from the `Session:` line of its claim record when the field is empty or differs (the poll's comment read, one REST read per such issue, gatekeeper's `issue_field` and `set_issue_field`), so a cloud lead's claim, which cannot call GraphQL, still gets the field in every repo of the account (#2677).

## 0.1.15 - 2026-11-25

- omnigent-agents: `omnigent_agent.py sweep` archives each session idle over a day through `finish_delivered`, keeping running sessions, open cards, background work, managers and a keep-list file, and prints one multiSelect owner card (`CARD:`) for the sessions the owner talked to, "Archive all" recommended (#1580).
- omnigent-agents: `start --cloud-env <name>` runs one cloud start in the named environment instead of the project's, from a launch dir pinned to it; an unknown name, another workspace, a host agent or another host is refused before any session exists, the unknown name listing the environments on the login (#2246).
- omnigent-agents: a supervisor started by its `--install` service logs, as its first line, that a kill restarts it, with the exact stop and restart commands for its platform; SKILL.md says to stop the service to pause it and restart it to pick up new code (#2350)
- omnigent-agents: `send` unarchives an archived session the supervisor registry lists, then delivers and waits for its report; an unlisted one is still refused, and `send --unarchive` forces it, as `relay` does (#2420)
- omnigent-agents: the stall sweep treats a `loop:queued` PR with any queue check run still `in_progress` as held by the queue, whichever run started last, so a PR in a live Mergify batch is no longer reported stalled (#2428)

## 0.1.14 - 2026-11-24

- `omnigent_agent.py supervise`: a merge-queue dequeue reaches the lead that owns the PR when the lead lands several or took the PR over. A lead's `omni.pr` label may hold several PRs, comma-joined (new `omnigent_agent.py own-pr <owner/name#N>` adds one); every reader of the label takes the list. A followed lead whose report head names `<repo>#<n>` or the PR's URL is the fallback, used only when exactly one lead matches: a label owner wins, and a tie goes to the coordinator naming both leads. `own-pr` takes several refs and writes once, checking only their format, so a mistyped PR number holds the session in `reap` (#2161).
- `omnigent_agent.py supervise`: a PR carrying `loop:hold` raises no `pr-stall` and no `dequeued` event for a manager to fix, until the label comes off (#2316).
- operating-omnigent: the "Restart server" row says running turns keep going through a restart, as observed, not that it interrupts mid-turn work (#2389)

## 0.1.13 - 2026-11-24

- `omnigent_agent.py start` and `run` write the registry line when the session is created, before its brief is sent, so a slow cold start can no longer pass the 60 s adoption grace and be followed by a second supervisor; and a non-numeric `created_at` skips that one session in the console's adoption sweep instead of ending the sweep (#2319).
- `omnigent_agent.py`: `rest_pages` stops on a page that repeats the one before and at 50 pages, so an endpoint that ignores `page=` (`git/matching-refs`, once a repo holds 100 loop refs) no longer loops forever and spends the REST quota (#2343).

## 0.1.12 - 2026-11-24

- `omnigent_agent.py supervise`: a followed coordinator (a manager with its own leads registry) whose turn ends on a `DONE` with no result on its line no longer wakes the notified session; the leads waiting on it are still told, and it stays followed (#2309).
- `omnigent_agent.py supervise`: the chief of staff console adopts no lead younger than 60 seconds, so a launcher that writes its lead to another registry is not followed twice, nor reported as a lead on no registry (#2313).

## 0.1.11 - 2026-11-24

- `start --verifier-route claude` accepts any `--model`, the author's own included, and no longer needs `--author-model`; the session is still marked same-family. A fresh session given only the code and the spec is what makes a verifier independent, so the same-model refusal only pushed verifiers onto models nobody chose (#2297).

## 0.1.10 - 2026-11-24

- `wait`, and with it `run` and `claude-cloud-run`, reads a claude-cloud child idle on its own background run as working: it finds the run in the session's history (Omnigent's record shows no cloud task), sends a check-in every 5 minutes instead of a nudge, and fails only at `--timeout`, naming the run. A `STILL WORKING` ending naming that run is no report, and a reply sharing the bridge's opening `cloud session:` line is still read (#959).

## 0.1.9 - 2026-11-24

- The supervisor reads a registered PR wait through ETag reads (the pull, its check runs and its combined status), so a poll of an unchanged PR answers 304 and spends no quota, and a restart's backfill reads each PR once however many waits name it. Part of #2068.
- `omnigent_agent.py supervise` wakes the notified session only for turn ends it must act on: a `DONE` whose result the lead sent to that session (a send carrying the result's first line) or whose session it already archived is told to the leads waiting on it but queues no `act` line, a turn end showing only progress or a named wait stays recorded, and the "no progress (quota)" line is said once until GitHub's quota resets (#2090).
- `wait-until` refuses a command that polls one PR through `gh` (exit 2) and names `wait-for --pr <n>`, whose ETag reads spend no quota while the PR doesn't move (#2115).
- `supervise` reads a turn's ending as its first line that opens with `DONE`, `USER NEEDED`, `PARKED` or `STILL WORKING` (`USER NEEDED` anywhere still wins), so a manager's status block that opens `STILL WORKING` and lists a `DONE:` section no longer routes as a delivered `done`; a new `Waits: own supervisor` footer (`wait-on own`) says a manager's own supervisor wakes it, and routes `record` (#2135).
- `omnigent-agents start` on `claude-cloud` now sends no permission mode unless `--permission-mode` names one, so update the Omnigent server to one with agent default modes first; the client-side "start refused … bypassPermissions" message is gone (#2148).
- `supervise` raises one `deadline` per declared wait: a wait that names sessions is keyed by its text and the sessions it names, so a reply that restates it starts no new chain, a changed wait does, and a wait still stuck after 4x `DEADLINE_SECONDS` fires once more. No `deadline` while every session the wait names ended its turn `PARKED`; its news line still tells the waiter (#2150).
- `supervise` routes a `USER NEEDED` turn end with no card open (`unasked`) to its manager as `act`, never to the owner and without the small model: the manager asks on its own card a question that spans projects, or sends the lead to its card. The lead preamble tells a lead to ask on its own card (#2170).
- `supervise` says a lead's question card still unanswered 4 hours after it first saw it (`CARD_REMIND_SECONDS`) to the lead's manager once, as a `card-waiting` event routed `act`, so a manager the owner told to act in their name can answer it; a lead the owner drives directly records it (#2170).
- The `loop.delegate: all` lead brief no longer says never to run `approve spec`: once the owner approves on the lead's own card, the lead records it with `--by owner`, as lead.md step 1 says (#2170).
- The chief of staff's console adopts a live top-level lead that no registry holds: it writes the lead a `follow` line and posts one `adopted` event, so a lead started without a registry no longer stalls unseen. `start --top-level --role lead` with no registry now exits 2 before any session exists (#2181).

## 0.1.8 - 2026-11-23

- The supervisor no longer reports a PR the merge queue holds as stalled. A `check stalled` line is checked against the PR's live state before it goes out, and dropped when the PR merged, closed, moved to a new head or is held by the queue since the sweep read it, which may be 15 minutes earlier. A PR carrying `loop:queued` whose queue check on its head is still running is waiting, not a `pr-stall`, however long the queue takes (#2100).

## 0.1.7 - 2026-11-23

- omnigent-agents: `send` and `relay` take `--expires <minutes>` (default 30, 0 = never) and tag their message with that expiry and the sending session, so one still queued behind a busy turn after its sender is gone is dropped instead of landing out of context (#909).
- `claude-cloud-env <checkout>` checks the environment the checkout pins (`.claude/settings.local.json`'s `remote.defaultEnvironmentId`, else its main checkout's) before it makes or updates one: a pinned environment named otherwise than loop.md's `Cloud worker: …, env <name>` (else the definition's name, else the repository's) fails naming both, as does a pin the login has no environment for, where it used to create a second, empty environment named after the repository beside the pinned one (#2078).

## 0.1.6 - 2026-11-23

- An archive (`PATCH /v1/sessions/<id>`) waits up to `ARCHIVE_SECONDS` (120 s) rather than the 30 s every other call gets, since a claude-cloud session's archive returns only once its bridge has archived the claude.ai session, which ends the VM and can take about 65 s; a slow archive was reported as `finish failed` (#2060).

## 0.1.5 - 2026-11-23

- omnigent-agents: `--role` takes `lead`, `worker` or `verifier` as well as a file path, naming the pack's engineering-loop role file, so a cloud child needs no role file in its launch dir (#1868).
- `start --top-level --host <other>` takes the report as that host's absolute path with `--pr` too, as without it: a relative one is refused and an absolute one is no longer created or resolved here, which failed with `PermissionError` when this host could not make that folder. `brief` does the same, and `wait --pr` on a session on another host writes the PR comment to `tmp/loop/<name>` here, where `send --pr` reads it as the report before (#2028).
- A cloud worker, verifier or gate child (`acp:claude-cloud`) whose result `run`, `wait` or the supervisor took is archived even while background tasks still run in its VM, since those pollers keep spending the account's GitHub quota; its line names how many ended with it. A lead, a manager, a top-level session with no role, a `--keep` child, an open card or prompt, a blind `reap` and every host session keep today's holds (#2052).

## 0.1.4 - 2026-11-23

- omnigent-agents: every cloud session's preamble installs gh-quota's logging gh shim from the pack clone and ends its report with its `gh_quota.py counts` and a count of its `curl` calls to `api.github.com`, since its log stays in the VM (#1994).
- omnigent-agents: `wait-for` and `supervise` resume up to 3 minutes after a GitHub rate-limit reset at random, so every poller that waited on one reset does not resume in its first second (#2000).

## 0.1.3 - 2026-11-23

- orchestrating-agents: `supervise --registry` runs the gatekeeper's `check stalled` at most once an hour for each repo its followed leads work in, detached from its poll, and says each stalled PR once per head as a `stalled` event, which `--console` routes to the chief of staff; a sweep that judged none of a repo's PRs is said once too (#1746).
- omnigent-agents: `supervise --registry` watches every open, non-draft PR of the repos it follows (and each `--stall-repo`) and wakes the manager with one `pr-stall` act event when a PR has had no push, verdict, go or merge-queue step for `--stall-minutes` (default 60), naming its blocker: a red required check, a conflict, a verdict without a go, a card waiting. It replaces the per-lead verdict-stall wake, which is now one blocker of this check (#1819).
- omnigent-agents: `start claude-cloud --host` on a bridge whose `~/.claude.json` is over 64 KB (the host files API answers 413) prints a warning that folder trust was not checked and goes ahead, instead of refusing (#1870).
- omnigent-agents: `relay` and `send` check a message for an off-request issue only when it names one: a message that names no issue reads nothing from Omnigent, so it no longer costs a session read and the follow-up path `test_a_failed_line_is_no_report_to_the_supervisor_a_start_a_follow_up_or_a_rerun` covers passes again (#1892).
- omnigent-agents: `start --host <remote> --workspace <path> --pr N` reads the workspace's `origin` through the host file API to name the PR's repository, and refuses with `--pr owner/repo#N` when it cannot, instead of labelling the current directory's repository (#1902).
- omnigent-agents: `omnigent_agent.py wait-for --pr` and the supervisor's required-check read spend no GitHub quota on a round where nothing they read changed: every REST read carries its last ETag (a 304 is free), and `--until checks|merged|closed` decides from those REST answers alone, with no GraphQL read (#1984).
- omnigent-agents: a cloud child's brief says where the pack's scripts come from: a clone of the pack's latest release tag, resolved in the VM with `git ls-remote` (no API quota), or the tag the brief pins with a `Pack: engineering-vX.Y.Z` line, never the checkout's vendored copy, whose pin may be releases old (#1987).

## 0.1.2 - 2026-11-22

- omnigent-agents: the cloud brief waits on a run with one tracked `wait-for --budget <the run's expected length>` instead of a `--budget 480` loop, and `wait-for --budget`'s help says its default is for a foreground call (#1790).
- omnigent-agents: `supervise --console` wakes a followed lead quiet an hour whose PR has a verdict on its current head over an hour old with no push or go since, with one `news` line per PR and head naming the step it owes (#1802).
- omnigent-agents: `start` refuses a second worker or verifier of a PR while one with the same role and PR runs, and `reap --force <id>` stops and finishes that running one, its open PR included (#1806).
- omnigent-agents: `relay` and `send` to a lead print a warning, and still deliver, when the message names an issue outside the lead's request, its epic or the epic's sub-issues (#1830).

## 0.1.1 - 2026-11-22

- orchestrating-agents: a session whose result is taken is archived at one shared point, `finish_delivered`: `run`, `wait`, `reap`, the supervisor's relay of a child's `DONE` report or failure and of a followed lead's `DONE` all call it, and a kept session (`--keep`, an open card, a PR hold, background work) stays open; `start --keep` labels a session so the supervisor leaves it open; a run that ended failed, cancelled or errored is finished too, a stale `omnigent.keep` label holds nothing, and archiving a parent finishes its idle children (#1579).
- omnigent-agents: `supervise --console` acts on a `STILL WORKING` that nothing wakes or that hands work back (#1753). A wait on a process the harness does not track ("waiting on pid 4242", "its pid is 4242", a pid file or a log or output file, with no `--notify`, `LOOP_NOTIFY`, child, CI or `Waits:` line), or in a cloud session on a background subagent, gets one nudge (`LEAD_UNTRACKED`) saying why nothing wakes it and how to wait instead, then act if the lead ends that way again; it used to record the turn as a named wait and leave the lead idle until the no-progress deadline. A hand-back, a `Handback: #<n> <what>` line or prose such as `#12 READY` or `#12 ... is yours`, goes to the session it notifies at once.
- omnigent-agents: `ssh` runs only short read-only checks and setup steps (#1754).
- omnigent-agents: a cloud worker's preamble no longer tells it to leave the session link out of its commit messages (#1764).
- omnigent-agents: Host steps over SSH points to orchestrating-agents' rule *Host work* instead of repeating it (#1765).
- omnigent-agents: a follow-up run updates a PR branch by a merge of the base, not a rebase (#1768).

## 0.1.0 - 2026-11-22

- omnigent: the first release, split out of `engineering`. It holds `omnigent-agents` (the Omnigent backend, formerly orchestrating-agents' `backends/omnigent.md`, and its driver `scripts/omnigent_agent.py`), `operating-omnigent` and `omnigent-telemetry`, with the cloud launcher `claude_cloud.py` and its client `claude_environments.py`, which `orchestrating-agents` held. It gains its `engineering` dependency when `engineering` drops its dependency on `omnigent` (#615).
- The full test suite is green again after 0.34.1: the remote-loop fake answers `GET /v1/hosts`, the cloud-floor start pins its launch dir, the picked-host start writes its report under a local folder, and the installed-pack settings test skips a setting the pinned release predates (#1701).
