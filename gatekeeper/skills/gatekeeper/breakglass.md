# Break-glass land

A way to land one exact head whose required check is red or missing for a reason that is not the change: a flaky or
broken suite, or CI infrastructure down. The owner approves the head, `land` verifies the proof from GitHub's run data,
and **the owner merges it in the GitHub UI**: `land` never merges a break-glass PR. Read this when a required check
blocks a PR the owner wants landed anyway, or when writing the proof.

## The verbs

- `approvals.py breakglass-proof <pr> --head <sha> --failed-run <id> [--rerun <id>] [--smoke <id>] [--earlier <id>...]`:
  any writer or agent posts the proof comment. It names run ids only. The owner's record pins its hash, so an edit voids
  the approval.
- `approvals.py approve breakglass <pr> --head <full-sha> --by owner --reason <line> [--expires <ISO time>]`: the owner's
  word. It writes the `breakglass` commit status and an `Approved: breakglass` record (`By`, `Head`, `Proof`, `Expires`,
  `Reason`). `--by delegate` is refused, and `loop.delegate: all` never covers it. `--withdraw` revokes it. A push moves
  the head and voids it; the carry-over of a go (same tree, merge of base) does not apply.
- `check merge`: where a required check is red or missing and the record is current, it prints
  `required check `qualify` red; break-glass approved by the owner on <sha>` and does not hold on that check. Every other
  proof (spec, verifier, a `risk:high` go) is still required. With no record its output is unchanged.

The approval counts only when `loop.owner` (the policy) names the login that created the status and wrote the comment.
Without `loop.owner` no login is the owner's, and every record is refused.

## Settings

`breakglass` in the policy (policy.md): `max_age` (`7d`), `max_commits` (`20`), `smoke` (the gate command), `earlier_runs`
(`2`), `artifact` (`failed-tests`).

## Owner-side setup

The owner's merge needs the Admin repository role as a bypass actor, `bypass_mode: pull_request`, on each managed repo's
landing ruleset (mirrored in the repo's ruleset file where one exists). The owner adds it on approval; no PR of the pack
edits a ruleset. Agents act as the same Admin account, so the pack's own code refuses every bypass merge (below).
