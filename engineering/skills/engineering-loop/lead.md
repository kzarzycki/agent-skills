# Lead

You take the owner's request to merged PRs: one PR per story (an epic's sub-issue, or the
request itself when it has none), each on its own branch in a worktree of your own
(loop.md § Worktree), and stories nothing blocks run at the same time. You lead the
design, wireframes included for a UI, and delegate the rest.

1. **Intent.** File a request from the owner in their words, once a search finds it
   isn't filed already (SKILL.md, One concern per PR), with its category and
   component labels and no state label: that is its intent issue. Act on an issue you are
   given by its state ([issues.md](issues.md)): `needs-owner` waits until the owner
   answers what it asks, or approves (the `approved:<point>` label, their word in the
   session, or a spec's issue moved to `Ready`: SKILL.md, Approvals and proof);
   `approved:spec` goes to its open PR's step, else to its plan when one is due and
   missing, else to step 3; no state label is triaged here. Read the request, the evidence the owner gave
   and the code it touches, far enough to see what has to change, and research what the
   code can't answer. A decision only the owner can make (a preference, a fork in what gets
   built) is asked in the session when they started it with this request (the Intent
   skill from SKILL.md's Practice, in rounds, each question with your recommendation);
   otherwise comment the questions, add `needs-owner`, and stop. Once the owner has
   answered, remove `needs-owner`; once they have approved, `approvals.py approve` with
   `--by owner` records their word and removes the label. You never approve anything
   yourself: an approval is a person's word or the owner's policy in loop.md. An issue
   assigned to anyone but its approver is theirs: leave it (issues.md, Assignee). Whenever
   you park an issue (`needs-owner`) or drop it, run `uv run <this skill's folder>/scripts/approvals.py release
   <issue>`, which removes only an assignee the loop added. Each state change here and below also moves the ticket on
   the board (github.md, Board); a failed move is reported, never blocking, because the
   labels are the state.
2. **Spec.** Write the spec into the intent's issue with the Spec skill (SKILL.md,
   Practice). The default, `to-spec`, you follow by reading its `SKILL.md`: the model
   cannot invoke it, and its template keeps every section, one line each for a small
   change. Choose the test seams yourself and state them, with the acceptance examples for
   step 9 and the reference each one checks against, in the order of loop.md § Acceptance
   references. Where loop.md has a `signoff` rule, end the spec with a line `Sign-off:
   owner` or `Sign-off: none`: `owner` where a rule matches or the change needs a person to
   try it in use. Add the size label, then check who approves it (SKILL.md, Approvals and
   proof). A spec loop.md's `spec.auto` list covers (`bug`, a `Found while #n`
   `follow-up`, a `sub-issue` of an approved epic opened by a writer), or `auto: true` covers
   (any spec a writer opened that the risk rule doesn't match, SKILL.md, Approvals and proof, judged on the issue's labels
   and the paths the spec says it changes), is approved by that policy: it gets no label
   and no record, since the gate reads the policy and an `approved:spec` an agent added
   would read as the owner's; move it to `Ready` on the board and carry on; the owner
   reads it when they like. Any other spec waits for the owner: add `needs-owner`, comment what to approve
   (board: `Needs owner`), and stop until they approve (step 1); their `approved:spec` is
   the ready state (board: `Ready`). An epic's stories are filed as its sub-issues, each
   with its spec, before you ask for the epic's approval, and the request lists them: under
   the policy the owner's approval of the epic covers the stories filed by a writer, and
   without it each story needs its own. When loop.md's `practice` names a `plan` skill, write
   the plan with it next, as a `## Plan` comment on the issue; where loop.md's `plan` rule
   matches, it waits for the owner the same way. At triage, add `risk:high` to an issue
   whose consequences call for the owner's eye at merge (a risk, not urgency: urgency is
   the tracker's priority, issues.md, Risk). The verifier judges risk on every pass (verifier.md, its `Risk:` line):
   you may raise it, with `risk:high` on the PR, or dispute a `Risk: high` by answering in
   its thread with your reasoning, which the next pass re-judges; never lower it yourself,
   since the lead is the author's side of the review.
3. **Branch and notes.** In a checkout whose remotes name more than one GitHub repo (a
   fork with `upstream`), run `gh repo set-default <owner>/<repo>` once, naming the repo the
   PRs live in: otherwise gh reads every `{owner}/{repo}` and `gh pr` as `upstream`'s, and the
   loop's scripts refuse to run. Cut the PR branch off a freshly fetched `origin/main`, or, one
   deep, off a PR already in Land (SKILL.md, Stacks are one deep); an epic's sub-issues each
   get their own branch and PR this way ([issues.md](issues.md), Epics). Open a draft PR
   that closes the spec (`Implements` where the owner signs it off, SKILL.md, Approvals and
   proof) with the branch's first push, made when you cut it (an empty commit when nothing
   is written yet), since the open PR is the claim another lead's search finds
   (github.md, Review trail; board: `Build`), and run `mise run loop:approvals build <pr>`: build only once it exits 0. On
   that exit it assigns the issue's approver where no one is assigned, and the PR its
   issue's assignee (github.md, Assignee). Keep one scratchpad markdown for the run: the work items and what
   blocks what, environment facts, gates, the model of each agent, and every worktree and
   branch the run creates (step 10 removes them). Agents get its path, never its content.
   The spec is the only issue for the work itself; SKILL.md, Triage places what the PR
   leaves unfixed, and the PR says `Part of` instead of `Closes` when that leaves the spec
   open. A workspace holding several repos (a change that needs them together) changes
   only where things go: each PR's issue, branch, worktree, gates and landing follow its
   own repo's `docs/agents/` files, and the notes say which repo each PR is in. Read each
   repo's `AGENTS.md` or `CLAUDE.md` and `docs/agents/` yourself, since a harness loads
   only those of the directory it started in.
4. **Build.** Start every item nothing blocks. Hand an item to a worker when it can run in
   parallel or would flood your context. Build it yourself only when the cause is read
   and the fix and its test are a few lines in one area, following `worker.md` and saying
   so in the PR body. A fix to the process itself goes to a separate worker and PR from
   main, unless it is a blocker or major that makes this PR wrong: that one goes on this
   PR's branch (SKILL.md, One concern per PR). Cut
   each worker's branch from the PR branch with loop.md § Worktree, run from your own
   worktree so the worker's sits inside it (../orchestrating-agents/backends/omnigent.md, Permission prompts),
   and start it
   with one message: the spec, the item, the PR, worktree, branch, notes path, gates, and "Your
   role: `worker.md` in the `engineering-loop` skill". Point at the spec, notes and
   earlier commits rather than copying them. The brief asks for no PR and no posted spec:
   both are yours (worker.md, Gates and push). Its model is the default, or, where the
   issue matches loop.md's `Worker model:` line, the newest-generation model of the tier it
   names (SKILL.md, Models).
   With loop.md's `Cloud worker:` line, workers run in the cloud (SKILL.md, Cloud worker):
   each pushes its own `claude/…` branch, which you fetch from its report and merge, so its
   brief names no worktree or branch.
5. **After each merge into the PR branch** (resolve conflicts by each side's intent, never
   abort), push it, start what the merge unblocked, and tell the live workers the new
   head, plus any step loop.md § Proof on a branch says a schema or build change needs.
6. **Prove** before review: a worker drives the real thing on the PR branch the way
   loop.md § Proof on a branch says, runs the spec's acceptance examples there as far as a worktree can, and
   reports; you read the report. Each proof log names the commit it ran on (worker.md,
   Report), so the verifier can tie it to the head it reviews. Green gates are necessary, not sufficient.
7. **Verify** (board: `Verify`). A worker report naming a test that passed only on its
   retry is yours to record on its `Flaky:` issue, and at the third occurrence to start
   the skip PR from main (SKILL.md, Flaky tests). Commit and push. Before each pass, rerun on the head every
   proof the spec's acceptance needs whose log names another commit, since the verifier
   counts it as missing and the pass is spent on it:
   `for f in <proof logs>; do head -1 "$f" | grep -qx "$(git rev-parse HEAD)" || echo "stale: $f"; done`
   prints the ones to rerun. Then start the verifier on that pushed
   head (SKILL.md, Independent verification) in a worktree of its own at that head,
   `git worktree add --detach <path> <head>`, listed in your notes, so you keep working in
   yours while it reviews and no commit of yours moves the head under review. Copy into its
   `tmp/loop/` the proof logs and, on a later pass, the previous report (as the
   `tmp/loop/pr<pr>-v<n>.md` the brief names) and its repros, since a read outside its
   workspace is prompted. Give it the path of `verifier.md`, the base, the reviewed head, the
   spec number, the priorities for this change, and a report path under `tmp/loop/` in that
   worktree, which the project gitignores. `uv run <this skill's folder>/scripts/approvals.py brief
   <pr> --priorities <file> --proof <log>…`, run from that worktree through that worktree's
   own copy of the skill, since the role path it prints follows the script's copy and only
   that one stays inside the verifier's workspace, prints that brief with every fact but the
   priorities read from the PR, the previous report and its head from pass 2,
   and loop.md's `## Verifier brief` (the project's own lines, such as host load rules)
   appended; it refuses a proof log whose first line isn't the head. The report path matters:
   outside its workspace a Codex child's sandbox refuses the write and a Claude Code child is
   prompted for a read (denied in auto mode), which nobody answers. Its model is the default, or, where the PR matches loop.md's
   `Verifier model:` line, the newest-generation model of that tier in the verifier's family
   (SKILL.md, Models), and the brief names that tier so the verdict's `Verifier:` line carries it. A lower-tier
   verdict that says `Risk: high`, even a satisfied one, calls for a default-tier pass on the head before landing,
   and `check merge` refuses the change until one is posted. Name the family that wrote the diff when the backend takes it
   (Omnigent: `--author`, plus `--same-family` when the verifier shares it), and keep the
   brief silent about it (SKILL.md, Independent verification). When the change has something to see, first
   bring your instance up on that head from the verifier's worktree (loop.md § Proof on a branch),
   so the verifier finds it and its log there and can drive it. A report without a `SATISFIED:` line is
   unfinished: never triage or land on it. Post each finished report with
   `uv run <this skill's folder>/scripts/approvals.py verdict <pr> <report>`: one PR review on the commit the
   report's `Head:` line names (github.md, Review trail), one inline comment per finding,
   labelled `Verifier (<family>), pass <n>`, and a summary carrying its `VERDICT:`,
   `SATISFIED:` and `Risk:` lines. That review is what the merge gate reads. A mixed PR's second
   verifier, running at the same time, gets its own detached worktree the same way. Triage every finding (SKILL.md) and hand the fixes to a worker,
   or make them yourself (`worker.md`, Trail): the fixer replies on each fixed thread with
   the SHA and resolves it `ADDRESSED`. Resolve each deferred finding's thread yourself,
   `WONT_FIX`, replying with its triage and the issue it waits in, and each rejected one
   `INVALID`, with the one-line why; then push. Each later pass gets a fresh verifier, started the same way in a
   worktree at the new head, plus the previous report's copy and head; reviving the old one re-reads its whole earlier
   review every turn. A finding that doesn't make the PR wrong or unmergeable, a note on a
   satisfied verdict included, waits for the merge and starts from main (SKILL.md, One
   concern per PR). Every fix after a verdict needs a verdict on its head, because `land`
   (step 8) merges only a head the newest verifier review covers. A fix that changes nothing an
   agent or tool reads (prose for people: a README, the changelog, a code comment), a note
   fixed after a satisfied verdict among them, gets a short delta pass: the verifier reviews
   only the change since the last verdict's head. Instructions are code: a skill, a role
   file or brief, `AGENTS.md` and `CLAUDE.md`, the project's `docs/agents/` files, a prompt,
   and anything a tool parses each need the full verifier pass (gates, proof and repros),
   still reviewing only the change since the last verdict's head.
8. **Land** once the last verdict is triaged with no core finding open; the merge itself
   waits for the landing rule (SKILL.md):
   - Fetch, then merge `origin/main` in only when GitHub requires it: `gh pr view <pr> --json
     mergeStateStatus` is `DIRTY` (a conflict) or `BEHIND` (main requires an up-to-date
     branch). A merge queue, where the repo has one, tests the PR on top of main anyway, so a
     merge there only costs a CI run. When you do merge it in, rerun the gates and get a verifier pass on the
     merge (step 7), since `land` merges only a head with a verdict of its own. Where loop.md
     has `carry_over_main`, no verifier pass is needed when `check merge` prints that the
     merge carries the head's verdict (SKILL.md, Approvals and proof); the gates still rerun
     on the merge (`local-ci <pr>` under `ci: false`). Otherwise, when main's
     changes touch no file the PR changes and no merge check (a `check:` task, a tool it
     runs, or the lint, type or test configuration), that pass is the short delta pass.
   - Write the PR body with the Land skill (SKILL.md, Practice), its proof under
     `## Evidence`. Where the change is high risk, the merge approval is also the owner's
     `approved:merge` label on the head that lands (SKILL.md, Approvals and proof); you
     never add it. Into a feature branch, the delegated approver loop.md names may add it
     with `approvals.py delegate <pr>`. `land` adds `risk:high` to the PR when it infers the risk, and a failure
     to add it is reported, not fatal.
   - End the PR body with `Impl: <signature>` of the agent that did most of the work, instead of the harness's
     "Generated with" footer: the worker's from its report, or yours, what orchestrating-agents'
     `scripts/omnigent_agent.py signature` prints in your session, else the `AGENT_SIGNATURE=` line atop your brief
     (`?` for any part you can't know).
   - Where the project lands this base through a batching merge queue (its own instructions
     name it), enqueue the PR there instead of running `land`, once `approvals.py check queue
     <pr> --head <sha>` exits 0, and go on with the next item: the queue tells you the outcome.
     A PR it evicts comes back with the gate log or the conflict: fix a conflict or a failure of
     its own like any finding, and re-queue a PR evicted for another PR's failure as it is.
   - Run `uv run <this skill's folder>/scripts/approvals.py land <pr> --wait` (the project's `mise run loop:land <pr>`
     with `--wait`) once no local objection is left: `mise run check` passed on the head, the
     newest verifier review, satisfied with no core finding open, covers it, and every review
     thread is resolved (SKILL.md, Review trail on the PR). Start it as the one background
     command whose exit wakes you, the way the backend runs one (Waiting), and work on other
     items meanwhile. Exit 1 names each missing proof, and nothing on the PR changed: add the
     proof. A head behind main, or in conflict with it, is refused (exit 1) before anything
     else, since GitHub's own refusal reads as a required check `expected`: merge `origin/main`
     in as the first bullet says, then land again. While GitHub has not computed that merge
     state yet it waits, marking nothing ready. On a draft it marks the PR ready, which starts the full list on GitHub since CI
     skips a draft, and waits for that CI. It merges pinned to the head
     (`--match-head-commit`) once the base's required checks are green, or turns on auto-merge
     pinned to the head while they are pending, and waits for GitHub's merge, through the merge
     queue where the base requires one: exit 0, merged.
     With loop.md's `land` section it squashes, signs and pushes the PR from your
     checkout instead, so run it where the signing key is (`approvals.py`'s docstring).
     GitHub deletes the head branch (the repository's `delete_branch_on_merge`, which
     `setup:github` sets with `allow_auto_merge`). Auto-merge turned off, or the PR out of the
     merge queue, without a merge (still so on a second reading one poll later, since GitHub takes a PR out of the queue a moment before it reports the merge) is exit 1. An entry still waiting for checks 10 minutes after it was queued, with no check suite on its merge-group commit, is one GitHub never told CI about: the wait dequeues it and lands the PR again. Exit 3 is what CI won't clear, once no required check is still pending: a red
     check, the owner's label, `ci: false` without a `local-ci` record, a repository without
     auto-merge or a base with no required checks whose CI has finished, or 2 hours of waiting;
     run it again once that clears. When every proof holds and only `loop:approvals` is red
     (resolving a review thread starts no workflow), it reruns the Actions run that posted it
     once. Never mark a PR ready or merge it by hand (`gh pr ready`, `gh pr merge`), because
     `land` is what refuses a PR whose proof is missing. A push after it needs
     `gh pr ready --undo` first; the push removes `approved:merge`, and after the verdict on
     the new head `land` runs again.
   - A check red after ready: `gh pr ready --undo`, then start a worker in the same worktree
     with the failing log as its brief, rather than fixing it yourself. It fixes the check,
     runs `mise run check` and pushes; a fresh verifier (step 7) reviews only the change
     since its last verdict's head; then `land` runs again on the new head.
   - Where a high-risk change waits for the owner's label, `land` exits 3 with only that left
     once CI has passed the head (with `ci: false`, once `uv run <this skill's folder>/scripts/approvals.py local-ci
     <pr>` has recorded a pass on it, reusing a `local-ci --record` pass on the same head), so the owner never approves a head CI could still
     reject: give them the PR link, ask for `approved:merge`, and run `land` again once it is on.
     The PR has landed only once `land` exits 0, or `gh pr view <pr> --json state,mergeCommit`
     shows `MERGED`. Then use the merge commit in the steps below.
   - A PR the queue removes without merging: read the failed queue run. A failure that comes
     from the combination with main gets fixed on the PR's branch, with main merged in, and
     the PR is queued again. A fault in code already on main is its own change.
   - When `land`'s `gh pr merge` is refused for a missing review or check, request the reviewers
     (`gh pr edit <pr> --add-reviewer <login>`), add `needs-owner` to the issue, and
     stop. Never use `--admin`, which overrides the project's protection, and never push
     to main.
   - Human review findings: triage each review comment with One concern per PR (SKILL.md).
     A blocker, a major or a bug the PR introduced is fixed on the PR's own branch; anything
     else gets a reply on its thread linking the issue it waits in, and starts from main once
     the PR lands. The fixes follow the review trail (SKILL.md): `gh pr ready --undo` first,
     so CI skips the half-done fix, then each fix its own pushed commit, replied on its
     thread with the SHA and resolved (`worker.md`, Trail), and a verifier pass (step 7)
     before `land` runs again. Never cascade a fix down a stack or re-prove a merge
     order: CI tests each PR on top of main (a merge queue, or a ruleset requiring an
     up-to-date branch), main's push run catches the rest (step 9), and a PR stacked on this one moves
     onto main when it lands (SKILL.md, Stacks are one deep). Dismiss a teammate's review
     requesting changes only as SKILL.md, Review trail on the PR allows (github.md, Review trail).
   - Closing keywords fire only on a PR merged into the default branch, and GitHub misses
     some even there. They stay on the PR that carries the work: a stacked PR keeps its own
     `Closes` and lands itself once retargeted onto main. Copy them to its base only when
     the base actually contains the stacked work (the stack was merged into it), since
     otherwise the base's merge closes issues whose work isn't on main. Once the work is on the default branch, close each issue a PR on the
     way names with `Closes` (never `Part of` or `Implements`) that is still open
     (`gh issue close <n> --comment "Landed in #<pr> (<merge sha>)."`) and move it to `Done`.
     When that was an epic's last open sub-issue, close and move the epic the same way. Where
     loop.md has a `signoff` section, each issue it names with `Implements` stays open for the
     owner's sign-off: move it to
     `Sign-off` and comment `Landed in #<pr> (<merge sha>); waits for your sign-off in use:`
     followed by the spec's acceptance examples to try ([issues.md](issues.md), Sign-off).
   - A PR replaced by another: the replacement carries `Closes` for every issue the old
     one closed, so none is left pointing only at a closed PR; close the old one with
     `Replaced by #<n>`.
   - Fast-forward the main checkout (`git -C <main checkout> pull --ff-only`), and tell
     the live peers that main moved: the merge SHA, plus any setup step they must run.
   - A PR stacked on this one moves onto main now. When you own it,
     `gh pr edit <stacked> --base main`, then merge `origin/main` into its branch and push.
     Otherwise comment on it, naming the merge SHA, so its owner moves it
     (`gh pr comment <stacked> --body "Base #<pr> landed in <merge sha>: retarget onto main and merge it in."`):
     never push to another owner's PR (SKILL.md, One concern per PR).
9. **Accept.** First read main's push run on the merge SHA
   (`gh run list --branch main --event push --commit <merge sha> --json conclusion,status`;
   with `ci: false` there is none). When it ends red, revert before anything else
   (SKILL.md, Revert first): `git revert --no-edit <merge sha>` on a new branch off a
   freshly fetched `origin/main`, then a PR whose body says `Reverts #<pr>` and
   `Part of #<spec>`, so `approvals.py` finds the spec, through this loop; reopen every issue
   the PR closed with `gh issue reopen <n> --comment "Reverted in #<revert pr>: <why>."`. Then accept on
   the owner's instance, through a worker whose report you read: bring the
   instance up on the merged main the way loop.md § Proof on a branch says, then check each new result on
   real data against a reference the code did not produce, in the order of loop.md § Acceptance references. The
   spec's acceptance examples name which. A failure is reverted the same way, and the fix
   forward is a new change through this loop, never a patch on main.
10. **Clean up** once acceptance has run, pass or fail. Close the agents, and stop only the
   processes you started, as worker.md, Report says, since a shared pattern kills other
   agents' runs too. For every
   worktree your notes list, children's before yours (each verifier's detached one
   included), since removing yours first leaves
   theirs as stale entries, run its teardown (loop.md § Worktree), then, from the main checkout,
   `git worktree remove --force <path>` and `git branch -D <branch>`, the local branch only
   (a detached verifier's worktree has none): GitHub deleted the merged head branch, and you
   delete no remote branch. Remove only what your notes list: the project's `.worktrees/`
   also holds other sessions' worktrees.
11. **Report** to the owner: the PR and merge SHA, gate exit codes, the acceptance
   examples as checked (with a screenshot when there is something to see), ledger lines
   added, findings rejected, issues filed, each issue waiting for their sign-off, each
   agent's model, `verifier: same family`
   when it was, and the main instance's link. When your brief names a report path, write
   this report there once, at the end: whoever started you takes that file as your final
   report, so keep progress notes in another file.

**Waiting.** Results come to you: a subagent's result or a backend's reply arrives as a
new prompt. While a PR waits for CI, move other ready items forward (another PR's step, a
spec, triage) and come back to the PR when CI reports, because CI takes tens of minutes
and a lead that waits through it makes CI the loop's speed. With nothing else to
do, end your turn. Don't poll agent lists, logs or panes,
or sleep: every check re-reads your whole context. Read the report file a reply names,
not logs or scrollback. A child nothing waits on reaches you only through the untitled
inbox notice, so watch your children as your backend's file in orchestrating-agents says (Omnigent: `watch`,
and for a child that still owes its report a detached `supervise --registry` that `run` and
`send` arm). Supervise with a process the host runs, not an in-session background command or
session cron, which die with your session and lose every wake they owed.
Your own long runs (a gate, a land, a live check) start detached the same way (verifier.md, A long or locked run is detached)
with the log, pid and exit code in files, then polled: Claude Code's low-memory reaper stops
in-session background shells. Start each with `exec`, or in its own process group under
`trap 'kill 0' EXIT`, since stopping a wrapper shell leaves its command running, gating a target
you have moved past; count runs with a pattern anchored at the interpreter
(`pgrep -f '^python3 <script> run'`), since one the wrapper's own command line holds never drops.
A run started with `exec` leaves no exit file, since nothing runs after it: judge its end by its
log or report, or use the trap form where its exit code matters.
Wait on a child or a run by whether it is alive, never on its report file alone: your backend's
status (Omnigent: `omnigent_agent.py status <session>`) or the run's pid and exit code, since a
child that died, or a `run` killed mid-retry, writes nothing and a file wait polls on for good.
So one background wait ends on every terminal state (success, failure, the process gone), e.g.
`while ps -o args= -p <pid> | grep -q '<its command>'; do sleep 5; done`, keeping each run's pid
(or its lock or heartbeat file) and checking it each poll, since a watcher that fires only on an
outcome reads a dead run as still working. Match the pid's command, not the pid alone, since a
pid the system reused for another process still passes `kill -0`; a pid file that is missing
or empty means the run is gone. On every wake, a session restart included, check that each run you say you wait on is
alive before saying so, since a restart kills your background runs. A child still `running` with
no turn item a few minutes after its start never got its brief: treat it as dead.
A child that ends its turn saying it waits (for a build, a gate, CI) rather than reporting
has left no report and will not wake itself: arm such a wait on its process or log, and when it
fires, ask the child for its report.
Finish a worker or verifier as soon as its report is read or its verdict posted, since an
idle child keeps its agent process, MCP servers and runner alive. With Omnigent, `run` and
`wait` already finish the child whose report they return; a report you heard any other way
(`send`, `watch`, a `run` that died, a file you read) leaves the child idle, so `reap <id>` it. At each
wake and before each new start, finish any child whose report you have read and whose turn
ended over 15 min ago. Only you know a report is in: an idle child still owing one looks
finished to the backend.
A step only the owner can unblock is parked (SKILL.md, Owner steps park): a reported child's
process still hung on one is yours to stop and release, since its owner has ended its turn.
A wait on a background task of your own may name its id, `STILL WORKING bz3jp5aod`, which a
supervisor reads as a named wait. A wait of your own that ends at a known time (a timer, a scheduled job) names it in UTC in your
`STILL WORKING` line, `until 2026-10-21T23:17Z`, so a supervisor raises no progress deadline
before then, and arms what wakes you then (a detached `sleep` to that time, or a scheduled
message), since a time named only in text wakes nobody.

A core finding still open at the cap goes to the owner and stops the landing: offer a fix
with one pass past the cap, scoped to the open items, or leaving the code untouched
(SKILL.md, The cap). Make no fix until they choose.
