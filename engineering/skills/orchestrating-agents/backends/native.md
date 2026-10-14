# Orchestrating with native subagents

The default backend: every harness has one, and it needs no setup.

- **Start:** your harness's own subagent tool, in the background, working in the item's
  worktree. The first message is the role file's path plus the specifics (spec and item,
  worktree, branch, base, report path). Name agents by spec, item and role
  (`s120-parser-worker`, `s120-verifier-p1`: one verifier per pass).
- **Message:** the harness's send-to-agent operation while the agent is live; otherwise
  a fresh agent whose brief points at the earlier report.
- **List:** the harness's list of running agents and background tasks.
- **Close:** stop the agent once its final reply has arrived.

## Verifier

When the other model family's CLI is installed, the verifier runs there,
non-interactively, as one background command from the worktree. Its prompt is one line
naming a brief file under `tmp/loop/`, because a child given pasted text tends to ask
for a go-ahead:

```bash
codex exec -C <worktree> "Read <brief-file> and follow it."   # verifies a Claude-written diff
claude -p "Read <brief-file> and follow it."                  # verifies a Codex-written diff
```

The permission settings for unattended runs are the developer's. The command's exit is
the wake; then read the report it names. Without the other family's CLI, start the
verifier as a fresh native subagent and write `verifier: same family` in the PR body.
