# Loop package

`loop/` ships the `engineering-loop` skill: the loop's method, its lead, worker and verifier
roles, and `scripts/loop.py` (the loop's `brief` and `release`). It depends on `gatekeeper`
and `github`, whose skills it finds where the host installed them.

- Delegation is the loop's method: its role split is what the skill teaches, unlike the
  craft skills, where subagents are the model's judgment.
- `engineering-loop` names no project: a project's facts live in its `docs/agents/` files,
  and `tests/test_engineering_loop.py` fails on a project term.
- A change's changelog entry is its own file in `changelog.d/`.
