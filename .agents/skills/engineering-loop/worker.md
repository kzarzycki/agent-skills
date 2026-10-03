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
2. **Gates and push.** Once `mise run check` exits 0, commit and push with
   `git push -u origin <branch>` as its own command, since a pre-tool hook may scan the
   whole command text. The coordinator merges your branch; open no PR.
3. **Report.** Clean up what you started (servers, temporary files), then write your
   report to a file and send the coordinator its path: the branch and head SHA, the gate
   exit codes, the model you ran on, anything left out and why, and what you tried and
   dropped. A follow-up starts fresh from this report, not your transcript. If you're
   blocked, report that and stop.
