# Worker

You implement one item of a spec, or a list of findings, on your own branch. The
coordinator's message gives the spec, the item, worktree, branch, notes path and gates.
Read the notes, the spec, [coding-standards.md](coding-standards.md) and the project's
`docs/agents/coding-standards.md` first. Run every command in your worktree, never in the
main checkout. A coordinator that builds an item itself follows this file on its own PR
branch: it pushes that branch, merges nothing, and writes the report into its notes.

1. **Build**, with the Build skill when loop.md § Practice names one, under these rules.
   Fixtures are synthetic: nothing in `docs/agents/issue-tracker.md` § Never on GitHub
   goes into code, tests or commits. A changed rule gets its line
   where the project records rules. Review angles you want run as native subagents.
2. **Gates and push.** Run `mise run test:changed` while iterating and `mise run check`
   before each push. Once it exits 0, commit and push with `git push -u origin <branch>` as
   its own command, since a pre-tool hook may scan the whole command text. Commit and push
   after each step whose gates are green, not only at the end, so a worker killed mid-task
   leaves its work on the branch. The coordinator merges your branch and opens the PR: a
   brief that asks for a PR means push the branch and report it. A spec or plan the brief
   asks for goes in a file under `tmp/loop/`, and you report its path: the coordinator
   posts it, since the spec lives on the issue. Your job ends at the push: don't wait for
   CI. A brief that is a failing CI log is a check red after the PR went ready: fix it in
   the worktree you are given, then `mise run check` and push the same way.
3. **Trail.** Fixing findings from a PR review, make each fix its own commit. After the
   push, reply on each finding's thread with its commit SHA and resolve it, reason
   `ADDRESSED` (github.md, Review trail). Resolve only a thread you fixed: deferring or
   rejecting a finding is triage, the coordinator's.
4. **Report.** Clean up what you started (servers, temporary files), then write your
   report to a file and send the coordinator its path: the branch and head SHA, the gate
   exit codes, the model you ran on, anything left out and why, and what you tried and
   dropped. A follow-up starts fresh from this report, not your transcript. If you're
   blocked, report that and stop.
