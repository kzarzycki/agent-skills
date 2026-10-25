# Worker

You implement one item of a spec, or a list of findings, on your own branch. The
lead's message gives the spec, the item, worktree, branch, notes path and gates.
Read the notes, the spec, [coding-standards.md](coding-standards.md) and the project's
`docs/agents/coding-standards.md` first. Run every command in your worktree, never in the
main checkout. A lead that builds an item itself follows this file on its own PR
branch: it pushes that branch, merges nothing, and writes the report into its notes.

1. **Build**, with the Build skill when loop.md's `practice` names one, under these rules.
   Fixtures are synthetic: nothing in `docs/agents/issue-tracker.md` § Never on GitHub
   goes into code, tests or commits. A changed rule gets its line
   where the project records rules. Review angles you want run as native subagents.
2. **Gates and push.** Run `mise run test:changed` while iterating and `mise run check`
   before each push (with `ci: false`, `approvals.py local-ci --record` on the committed
   head, SKILL.md, Adopting the loop). Once it exits 0, commit and push with `git push -u origin <branch>` as
   its own command, since a pre-tool hook may scan the whole command text. Commit and push
   after each step whose gates are green, not only at the end, so a worker killed mid-task
   leaves its work on the branch. The lead merges your branch and opens the PR: a
   brief that asks for a PR means push the branch and report it. A spec or plan the brief
   asks for goes in a file under `tmp/loop/`, and you report its path: the lead
   posts it, since the spec lives on the issue. Your job ends at the push: don't wait for
   CI. A brief that is a failing CI log is a check red after the PR went ready: fix it in
   the worktree you are given, then `mise run check` and push the same way. A command too
   long for one turn runs in the foreground with a long timeout, or in the background behind
   one wait that ends on every outcome (success, failure, the process gone); never end a
   turn saying you are waiting, since nothing wakes you and the lead reads silence
   as work.
3. **Trail.** Fixing findings from a PR review, make each fix its own commit. After the
   push, reply on each finding's thread with its commit SHA and resolve it, reason
   `ADDRESSED` (github.md, Review trail). Resolve only a thread you fixed: deferring or
   rejecting a finding is triage, the lead's.
4. **Report.** Every log or capture you hand over as proof (a gate run, a repro, a drive
   of the instance) starts with the output of `git rev-parse HEAD` and the command that
   produced it, since a proof of another commit says nothing about the one under review.
   That SHA is the whole provenance: a checksum manifest or digest exchange adds nothing a
   commit does not already pin.
   A change to a web UI gets a rendered check, since passing tests say nothing about what
   the page shows: the project's own browser e2e when it has one, else `uv run
   scripts/browse.py <url> --out <png>` (`--do <file.py>` to click, hover or assert first,
   `--omnigent` to sign in to an Omnigent server; its docstring says what a sandbox needs).
   Every host with Playwright's Chromium in `~/.cache/ms-playwright` can render headless;
   hand over the PNG paths.
   Run browser tests and drives headless: a window that opens on the owner's machine takes
   focus from what they are doing. Start a headless browser of your own rather than attaching to one already open there
   (over CDP or a remote-debugging port), since that one is headed; attach only when the
   check needs that browser's logins, and say so in the report. Where a test can't run headless,
   open the browser in the background without taking focus and say in the report which
   test needed it and why. A project whose e2e opens a headed browser by default names the
   headless switch in its `docs/agents/` files.
   Clean up what you started (servers, temporary files), then write your
   report to a file and send the lead its path: the branch and head SHA, the gate
   exit codes, the model you ran on, anything left out and why, and what you tried and
   dropped. A follow-up starts fresh from this report, not your transcript. If you're
   blocked, report that and stop.
