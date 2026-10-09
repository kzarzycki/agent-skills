# Loop facts

The `engineering-loop` skill reads this file at every step but the gate.

## Owner

@kzarzycki

## Proof on a branch

- Bring it up: in Claude Code, `/plugin marketplace add <worktree path>`, then
  `/plugin install <plugin>@kzarzycki-agent-skills` and run the changed skill.
- An engineering pack change: `mise run test-engineering-package` installs the pack into a
  scratch consumer (`engineering/tests/test_consumer_e2e.py`); `mise run
  test-engineering-agents` runs it in live Claude Code and Codex sessions.
- Its log: the session's transcript and the commands' output.

## Acceptance references

1. The upstream source a skill is imported from, at the commit `engineering/vendir.lock.yml` pins.
2. A consumer repo running the released pack (getindata/axis, kzarzycki/project-templates).
3. Invariants a test states without running the code under test.

## Practice

Default.

## Approvals

- spec: auto unless risk
- merge: auto unless risk
- risk: path `.github/**` or path `.pre-commit-config.yaml` or path `mise.toml` or path `apm.yml` or path `docs/agents/**` or path `CODEOWNERS`

## In use

Coding agents load these skills in the owner's and the team's repos, and the loop's scripts
run there with the user's `gh` credentials. A finding is judged by what an agent or a
consumer repo hits in use. Hostile input is out of scope.

## Worktree

- Create: `git worktree add .worktrees/<branch> -b <branch> origin/main`, then
  `mise install` and `uv sync` in it.
- Before removing: nothing; then `git worktree remove .worktrees/<branch>`.

## Ledger

`docs/agents/ledger.md`, created with its first entry.

## Verifier checklist

None.
