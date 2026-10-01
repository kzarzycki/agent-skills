# Orchestrating with herdr-link

Where the harness loads herdr-link (the `herdr_link*` tools), use its tools rather than
the `herdr` CLI. A message needs no instructions on how to answer: the reply rule in
SKILL.md ("Reports are files") tells every role.

- **Start:** `herdr_link_start` with `name` and `cwd` set to the worktree. Name agents by
  spec, item and role (`s120-parser-worker`, `s120-verifier-p1`: one verifier per pass).
  An OMP worker takes loop.md's `OMP worker profile: <name>` as `config_agent`, when that
  line exists; other agents take `kind` and `args`.
- **Message:** `herdr_link_send`. The first message is the role file's path plus the
  specifics (spec and item, worktree, branch, base, report path). The agent's reply is
  the path of its report.
- **List:** `herdr_link_peers` shows the live agents: use it before a main-moved notice
  and before touching a worktree someone else may have open.
- **Close:** `herdr_link_close` once the agent's final reply has arrived.

A harness without herdr-link uses the `herdr` skill for the same four operations. A
worker can instead be a native background subagent of your own harness; a verifier only
when the other family is unavailable (SKILL.md, Independent verification).
