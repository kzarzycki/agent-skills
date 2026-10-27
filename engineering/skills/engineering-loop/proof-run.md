# Proof run

A brief the lead fills in and sends to a cloud child (`run --pr <n>`, SKILL.md, Cloud worker)
when a verifier asks for its runs because the host's heavy slot was not free (verifier.md,
A full heavy slot). The child returns the logs; the verifier reads them as its own.

```text
Check out PR #<n> at <head> (`git fetch origin pull/<n>/head && git checkout --detach <head>`)
and stop if `git rev-parse HEAD` is not <head>. Commit nothing and push nothing: these are a
review's runs, not a change.

Each log starts with the output of `git rev-parse HEAD` and the command, then its output,
then a line `exit <n>`, since a log of another commit proves nothing about this one.

1. Green log: run <gate command>.
2. Mutation log: for each patch below, `git apply -R <patch>`, run <tests>, then
   `git apply <patch>`, one log section per patch.
   <each patch the verifier saved, verbatim in its own fenced block>
3. Restore: end with `git status --porcelain` and `git diff --stat` in the last log, both
   empty, since a run that leaves the tree changed taints the next one.

Post the logs, each in its own fenced block, as your one report comment on PR #<n>.
```
