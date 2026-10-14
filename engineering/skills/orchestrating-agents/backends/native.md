# Orchestrating with native subagents

The default backend: every harness has one, and it needs no setup.

- **Start:** your harness's own subagent tool, in the background, working in the item's
  worktree. The first message is the role file's path plus the specifics (spec and item,
  worktree, branch, base, report path). Name agents by spec, item and role
  (`s120-parser-worker`, `s120-verifier-p1`: one verifier per pass).
- **Message:** the harness's send-to-agent operation while the agent is live; otherwise
  a fresh agent whose brief points at the earlier report.
- **Wait:** end your turn. The harness notifies you when a background agent finishes,
  with its final reply, the report path; read the report then.
- **Watch:** the same notification arrives for every background agent you started, so
  there is nothing to arm for one no wait is on.
- **List:** the harness's list of running agents and background tasks.
- **Close:** stop the agent once its final reply has arrived.

## A child in another harness

When the caller wants a child of another model family (which role does is the caller's
policy: under the engineering loop, its SKILL.md, Independent verification) and that
family's CLI is installed, run it non-interactively, as one background command from the
worktree. Its prompt is one line naming a brief file under `tmp/loop/`, because a child
given pasted text tends to ask for a go-ahead:

```bash
codex exec -C <worktree> "Read <brief-file> and follow it."   # a Codex child
claude -p "Read <brief-file> and follow it."                  # a Claude child
```

The permission settings for unattended runs are the developer's. The command's exit is
the wake (wait and watch both); then read the report it names. Without that CLI, a fresh
native subagent of your own harness is the only child this backend can start.
