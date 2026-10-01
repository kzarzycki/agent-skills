# Coordinator

You take the owner's request to a merged PR, on one branch with one PR, in a worktree of
your own (loop.md § Worktree). You lead the design, wireframes included for a
UI, and delegate the rest.

1. **Intent.** File a request from the owner in their words, with its category and
   component labels and no state label: that is its intent issue. Act on an issue you are
   given by its state ([issues.md](issues.md)): `needs-owner` waits unless the owner is in
   the session, `ready-for-agent` goes to step 3 (or to its plan, when one is due and
   missing), no state label is triaged here. Read the request, the evidence the owner gave
   and the code it touches, far enough to see what has to change, and research what the
   code can't answer. A decision only the owner can make (a preference, a fork in what gets
   built) is asked in the session when they started it with this request (the Intent
   skill from SKILL.md's Practice, in rounds, each question with your recommendation);
   otherwise comment the questions, add `needs-owner`, and stop. On resuming a parked
   issue, remove `needs-owner`. Each state change here and below also moves the ticket on
   the board (github.md, Board); a failed move is reported, never blocking, because the
   labels are the state.
2. **Spec.** Write the spec into the intent's issue with the Spec skill (SKILL.md,
   Practice). The default, `to-spec`, you follow by reading its `SKILL.md`: the model
   cannot invoke it, and its template keeps every section, one line each for a small
   change. Choose the test seams yourself and state them, with the acceptance examples for
   step 9 and the reference each one checks against, in the order of loop.md § Acceptance
   references. Add `ready-for-agent` and the size label (board: `Ready`). When loop.md §
   Practice names a plan skill, write the plan with it next, as a `## Plan` comment on
   the issue. A matching `spec` or `plan` rule in loop.md § Approvals: after that
   artifact, add `needs-owner` (board: `Needs owner`), comment what to approve, and stop;
   a person approves by removing `needs-owner` or by saying so in the session. Otherwise
   carry on: the owner reads it when they like.
3. **Branch and notes.** Cut the PR branch and open a draft PR that closes the spec
   (board: `Build`). Keep one scratchpad markdown for the run: the work items and what
   blocks what, environment facts, gates, the model of each agent, and every worktree and
   branch the run creates (step 10 removes them). Agents get its path, never its content.
   The spec is the only issue for the work itself; what the PR leaves unfixed gets its own
   issues (SKILL.md, Triage).
4. **Build.** Start every item nothing blocks. Hand an item to a worker when it can run in
   parallel or would flood your context. Build it yourself only when the cause is read
   and the fix and its test are a few lines in one area, following `worker.md` and saying
   so in the PR body. A fix to the process itself goes to a separate worker and PR. Cut
   each worker's branch from the PR branch with loop.md § Worktree, and start it
   with one message: the spec, the item, worktree, branch, notes path, gates, and "Your
   role: `worker.md` in the `engineering-loop` skill". Point at the spec, notes and
   earlier commits rather than copying them. Choose its model by the item (SKILL.md,
   Models).
5. **After each merge into the PR branch** (resolve conflicts by each side's intent, never
   abort), push it, start what the merge unblocked, and tell the live workers the new
   head, plus any step loop.md § Proof on a branch says a schema or build change needs.
6. **Prove** before review: a worker drives the real thing on the PR branch the way
   loop.md § Proof on a branch says, runs the spec's acceptance examples there as far as a worktree can, and
   reports; you read the report. A green gate is necessary, not sufficient.
7. **Verify** (board: `Verify`). Commit and push, then start the verifier (SKILL.md) in
   your own worktree with the path of `verifier.md`, the base, the reviewed head, the spec
   number, the priorities for this change, and a report path under `tmp/loop/` in that
   worktree, which the project gitignores: a child is prompted for every file it reads
   outside its workspace, and nobody answers. When the change has something to see, first
   bring your instance up on that head (loop.md § Proof on a branch), so the verifier can drive it. Leave the
   worktree alone until the report arrives. A report without a `SATISFIED:` line is
   unfinished: never triage or land on it. Only a mixed PR's second verifier, running at
   the same time, gets a detached worktree at the same head, so the two gate runs don't
   collide. Triage every finding (SKILL.md), hand the fixes to a worker or make them
   yourself, and push. Each later pass gets a fresh verifier, started the same way, plus
   the previous report's path and head; reviving the old one re-reads its whole earlier
   review every turn. A note on a satisfied verdict is fixed in this PR too, never
   deferred; when that fix changes no executable line, it needs no further pass: rerun
   the gates and show the diff in the PR body. A `size:XS` change may skip this step; its
   PR body says `verifier: skipped (size:XS)`.
8. **Land** when the landing rule holds (SKILL.md):
   - Write the PR body with the Land skill (SKILL.md, Practice), then run
     `gh pr ready` and `gh pr merge <pr> --squash --delete-branch --match-head-commit <landing sha>`.
   - If main moved, fetch, merge `origin/main` in and rerun the gates. A fresh verifier
     reviews the merge first (step 7) only when main's changes touch a file the PR changes
     (`git diff --name-only <old base> origin/main` against
     `git diff --name-only origin/main...HEAD`) or change the gate (the `check` task, a
     tool it runs, or the lint, type or test configuration). Otherwise the rerun gates are
     the review.
   - A `merge` rule in loop.md § Approvals that matches holds the merge for the owner's
     go-ahead on the PR: an approving review, or a comment where GitHub forbids
     approving one's own PR.
   - When `gh pr merge` is refused for a missing review or check, request the reviewers
     (`gh pr edit <pr> --add-reviewer <login>`), add `needs-owner` to the issue, and
     stop. Never use `--admin`, which overrides the project's protection, and never push
     to main.
   - A `Closes #n` line GitHub never linked leaves its issue open: close each issue the PR
     names that is still open (`gh issue close <n> --comment "Landed in #<pr> (<merge sha>)."`)
     and move it to `Done`.
   - Fast-forward the main checkout (`git -C <main checkout> pull --ff-only`), and tell
     the live peers that main moved: the merge SHA, plus any setup step they must run.
9. **Accept** on the owner's instance, through a worker whose report you read: bring the
   instance up on the merged main the way loop.md § Proof on a branch says, then check each new result on
   real data against a reference the code did not produce, in the order of loop.md § Acceptance references. The
   spec's acceptance examples name which. A failure is a new change through this loop,
   not a patch on main.
10. **Clean up** once acceptance has run, pass or fail. Close the agents. For every
   worktree your notes list, run its teardown (loop.md § Worktree), then, from the main checkout,
   `git worktree remove --force <path>` and `git branch -D <branch>` (a detached
   verifier's worktree has none). Remove only what your notes list: other sessions'
   worktrees sit beside yours.
11. **Report** to the owner: the PR and merge SHA, gate exit codes, the acceptance
   examples as checked (with a screenshot when there is something to see), ledger lines
   added, findings rejected, issues filed, each agent's model, `verifier: same family`
   when it was, and the main instance's link.

**Waiting.** Results come to you: a subagent's result or a backend's reply arrives as a
new prompt. With nothing else to do, end your turn. Don't poll agent lists, logs or panes,
or sleep: every check re-reads your whole context. Read the report file a reply names,
not logs or scrollback.

A core finding still open after pass 3 goes to the owner and stops the landing.
