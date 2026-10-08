# Coordinator

You take the owner's request to a merged PR, on one branch with one PR, in a worktree of
your own (loop.md § Worktree). You lead the design, wireframes included for a
UI, and delegate the rest.

1. **Intent.** File a request from the owner in their words, with its category and
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
   `--by owner` records it and removes the label. Each state change here and below also moves the ticket on
   the board (github.md, Board); a failed move is reported, never blocking, because the
   labels are the state.
2. **Spec.** Write the spec into the intent's issue with the Spec skill (SKILL.md,
   Practice). The default, `to-spec`, you follow by reading its `SKILL.md`: the model
   cannot invoke it, and its template keeps every section, one line each for a small
   change. Choose the test seams yourself and state them, with the acceptance examples for
   step 9 and the reference each one checks against, in the order of loop.md § Acceptance
   references. Add the size label, then approve the spec (SKILL.md, Approvals and proof):
   its `approved:spec` is the ready state (board: `Ready`). An epic's stories are filed as
   its sub-issues, each with its spec, before you ask for the epic's approval, and the
   request lists them: every epic and story has its own owner approval, and none inherits
   another's. When loop.md § Practice names a plan skill,
   write the plan with it next, as a `## Plan` comment on the issue, and approve it too.
   When `approve` says a person must approve as well, comment what to approve (board:
   `Needs owner`) and stop. Otherwise carry on: the owner reads it when they like.
3. **Branch and notes.** Cut the PR branch off a freshly fetched `origin/main`, or, one
   deep, off a PR already in Land (SKILL.md, Stacks are one deep); an epic's sub-issues each
   get their own branch and PR this way ([issues.md](issues.md), Epics). Open a draft PR
   that closes the spec with the branch's first push (github.md, Review trail; board:
   `Build`), and run `mise run loop:approvals build <pr>`: build only once it exits 0. Keep one scratchpad markdown for the run: the work items and what
   blocks what, environment facts, gates, the model of each agent, and every worktree and
   branch the run creates (step 10 removes them). Agents get its path, never its content.
   The spec is the only issue for the work itself; SKILL.md, Triage places what the PR
   leaves unfixed, and the PR says `Part of` instead of `Closes` when that leaves the spec
   open.
4. **Build.** Start every item nothing blocks. Hand an item to a worker when it can run in
   parallel or would flood your context. Build it yourself only when the cause is read
   and the fix and its test are a few lines in one area, following `worker.md` and saying
   so in the PR body. A fix to the process itself goes to a separate worker and PR from
   main, unless it is a blocker or major that makes this PR wrong: that one goes on this
   PR's branch (SKILL.md, One concern per PR). Cut
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
   reports; you read the report. Green gates are necessary, not sufficient.
7. **Verify** (board: `Verify`). Commit and push, then start the verifier (SKILL.md) in
   your own worktree with the path of `verifier.md`, the base, the reviewed head, the spec
   number, the priorities for this change, and a report path under `tmp/loop/` in that
   worktree, which the project gitignores: a child is prompted for every file it reads
   outside its workspace, and nobody answers. When the change has something to see, first
   bring your instance up on that head (loop.md § Proof on a branch), so the verifier can drive it. Leave the
   worktree alone until the report arrives. A report without a `SATISFIED:` line is
   unfinished: never triage or land on it. Post each finished report's verdict with
   `python3 scripts/approvals.py verdict <pr> <report>`, which `approvals.py` reads: it posts
   the report's `Head:` line, the head the verifier reviewed, and refuses a report without
   one. Post it also as a PR review
   of the reviewed head (github.md, Review trail): one inline comment per finding, labelled
   `Verifier (<family>), pass <n>`, and a summary carrying its `VERDICT:` and `SATISFIED:`
   lines. Only a mixed PR's second verifier, running at
   the same time, gets a detached worktree at the same head, so the two gate runs don't
   collide. Triage every finding (SKILL.md), hand the fixes, and each deferred finding
   with the issue it waits in, to a worker or make them yourself (`worker.md`, Trail), and
   push. Each later pass gets a fresh verifier, started the same way, plus
   the previous report's path and head; reviving the old one re-reads its whole earlier
   review every turn. A finding that doesn't make the PR wrong or unmergeable, a note on a
   satisfied verdict included, waits for the merge and starts from main (SKILL.md, One
   concern per PR). Every fix after a verdict needs a verdict on its head, because `land`
   (step 8) merges only a head the newest verdict covers. A fix that changes nothing an
   agent or tool reads (prose for people: a README, the changelog, a code comment), a note
   fixed after a satisfied verdict among them, gets a short delta pass: the verifier reviews
   only the change since the last verdict's head. Instructions are code: a skill, a role
   file or brief, `AGENTS.md` and `CLAUDE.md`, the project's `docs/agents/` files, a prompt,
   and anything a tool parses each need the full pass.
8. **Land** once the last verdict is triaged with no core finding open; the merge itself
   waits for the landing rule (SKILL.md):
   - Fetch, then merge `origin/main` in only when GitHub requires it: `gh pr view <pr> --json
     mergeStateStatus` is `DIRTY` (a conflict) or `BEHIND` (main requires an up-to-date
     branch). A merge queue tests the PR on top of main anyway, so a merge there only costs
     a CI run. When you do merge it in, rerun the gates. A fresh verifier
     reviews the merge first (step 7) only when main's changes touch a file the PR changes
     (`git diff --name-only <old base> origin/main` against
     `git diff --name-only origin/main...HEAD`) or change a merge check (a `check:` task, a
     tool it runs, or the lint, type or test configuration). Otherwise the rerun gates are
     the review.
   - Write the PR body with the Land skill (SKILL.md, Practice), its proof under
     `## Evidence`. Where a loop.md `merge:` rule asks, the merge approval is also the
     owner's `approved:merge` label on the head that lands (SKILL.md, Approvals and proof);
     you never add it.
   - Run `python3 scripts/approvals.py land <pr>` (the project's `mise run loop:land <pr>`)
     once no local objection is left: `mise run check` passed on the head and the newest
     verdict, satisfied with no core finding open, covers it (SKILL.md, Review trail). Exit 1
     names each missing proof, and nothing on the PR changed: add the proof. On a draft it
     marks the PR ready, which starts the full list on GitHub since CI skips a draft, and
     exits 3, since the draft's skipped checks say nothing about the ready PR: run it again.
     On a ready PR it merges pinned to the head (`--match-head-commit`) when the base's
     required checks are green, or turns on auto-merge pinned to the head while they are
     pending: exit 0.
     GitHub deletes the head branch (the repository's `delete_branch_on_merge`, which
     `setup:github` sets with `allow_auto_merge`). Exit 3: it waits for something auto-merge
     would not hold for (a red check, the owner's label, a repository without auto-merge, a
     base with no required checks); run it again once that clears. Never mark a PR ready or
     merge it by hand (`gh pr ready`, `gh pr merge`), because `land` is what refuses a PR
     whose proof is missing. A push after it needs `gh pr ready --undo` first; the push
     removes `approved:merge`, and after the verdict on the new head `land` runs again.
   - Don't wait idle for CI: start one background command whose exit wakes you, the way the
     backend runs one (Waiting). It waits on `check` alone, because `loop:approvals` can stay
     pending on the owner, whom you ask only after it, adding the label:
     `until gh pr checks <pr> --json name,bucket --jq '.[] | select(.name == "check" and .bucket != "pending") | .bucket' | grep .; do sleep 60; done`.
     It prints `pass` once `check` is green (`skipping` counts as green, as GitHub counts it), or `fail` (or `cancel`) when it is red.
   - A check red after ready: `gh pr ready --undo`, then start a worker in the same worktree
     with the failing log as its brief, rather than fixing it yourself. It fixes the check,
     runs `mise run check` and pushes; a fresh verifier (step 7) reviews only the change
     since its last verdict's head; then `land` runs again on the new head.
   - Where a `merge:` rule asks for the owner's label, ask only once `check` is green on the
     head (with `CI: none`, once `python3 scripts/approvals.py local-ci <pr>` has recorded a
     pass on that head), so they never approve a head CI could still reject: when `land`
     exits 3 with only the owner's label left, give the owner the PR link and ask for
     `approved:merge`, and run `land` again once it is on.
     The PR has landed only once `gh pr view <pr> --json state,mergeCommit` shows `MERGED`.
     Before working on other items, start one background command whose exit wakes you when
     the PR merges or drops out of the queue, the way the backend runs one (Waiting):
     `until gh api graphql -f query='query($o:String!,$r:String!,$n:Int!){repository(owner:$o,name:$r){pullRequest(number:$n){state isInMergeQueue autoMergeRequest{enabledAt}}}}' -F o=<owner> -F r=<repo> -F n=<pr> --jq '.data.repository.pullRequest | select(.state == "MERGED" or (.isInMergeQueue == false and .autoMergeRequest == null)) | .state' | grep -q .; do sleep 60; done`
     (`gh pr view` has no queue field).
     Then use the merge commit in the steps below.
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
     order: a merge queue tests each PR on top of main, and a PR stacked on this one moves
     onto main when it lands (SKILL.md, Stacks are one deep).
   - Closing keywords fire only on a PR merged into the default branch, and GitHub misses
     some even there. They stay on the PR that carries the work: a stacked PR keeps its own
     `Closes` and lands itself once retargeted onto main. Copy them to its base only when
     the base actually contains the stacked work (the stack was merged into it), since
     otherwise the base's merge closes issues whose work isn't on main. Once the work is on the default branch, close each issue a PR on the
     way names with `Closes` (never `Part of`) that is still open
     (`gh issue close <n> --comment "Landed in #<pr> (<merge sha>)."`) and move it to `Done`.
     When that was an epic's last open sub-issue, close and move the epic the same way.
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
   with `CI: none` there is none). When it ends red, revert before anything else
   (SKILL.md, Revert first): `git revert --no-edit <merge sha>` on a new branch off a
   freshly fetched `origin/main`, then a PR whose body says `Reverts #<pr>` and
   `Part of #<spec>`, so `approvals.py` finds the spec, through this loop; reopen every issue
   the PR closed with `gh issue reopen <n> --comment "Reverted in #<revert pr>: <why>."`. Then accept on
   the owner's instance, through a worker whose report you read: bring the
   instance up on the merged main the way loop.md § Proof on a branch says, then check each new result on
   real data against a reference the code did not produce, in the order of loop.md § Acceptance references. The
   spec's acceptance examples name which. A failure is reverted the same way, and the fix
   forward is a new change through this loop, never a patch on main.
10. **Clean up** once acceptance has run, pass or fail. Close the agents. For every
   worktree your notes list, run its teardown (loop.md § Worktree), then, from the main checkout,
   `git worktree remove --force <path>` and `git branch -D <branch>`, the local branch only
   (a detached verifier's worktree has none): GitHub deleted the merged head branch, and you
   delete no remote branch. Remove only what your notes list: other sessions' worktrees sit
   beside yours.
11. **Report** to the owner: the PR and merge SHA, gate exit codes, the acceptance
   examples as checked (with a screenshot when there is something to see), ledger lines
   added, findings rejected, issues filed, each agent's model, `verifier: same family`
   when it was, and the main instance's link.

**Waiting.** Results come to you: a subagent's result or a backend's reply arrives as a
new prompt. While a PR waits for CI, move other ready items forward (another PR's step, a
spec, triage) and come back to the PR when CI reports, because CI takes tens of minutes
and a coordinator that waits through it makes CI the loop's speed. With nothing else to
do, end your turn. Don't poll agent lists, logs or panes,
or sleep: every check re-reads your whole context. Read the report file a reply names,
not logs or scrollback. A child nothing waits on reaches you only through the untitled
inbox notice, so watch your children as the orchestration file says (Omnigent: `watch`).

A core finding still open after pass 3 goes to the owner and stops the landing.
