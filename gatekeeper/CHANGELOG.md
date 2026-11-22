# Changelog

## Unreleased

New entries are files in [changelog.d/](changelog.d/), one per issue, until a release moves
them here.

## 0.1.0 - 2026-11-22

- gatekeeper: the first release, split out of `engineering`. The `gatekeeper` skill holds `scripts/gatekeeper.py`, its GitHub adapter `scripts/github_adapter.py` and the `scripts/approvals.py` shim, with their tests; it depends on no other package. `brief` and `release` leave it for the loop's own `scripts/loop.py` (#615).
- gatekeeper: a team that installs only the gatekeeper finds the policy it reads in this skill. `policy.md` holds every policy key with its type, default and an example block, and issue-tracker.md's settings block, which the loop's SKILL.md § Settings held; the gate's rules stay in the loop's SKILL.md § Approvals and proof. The helpers it loads from beside itself (`acceptance.py`, `events.py`, `folding.py`) and `events.md` move with it, and the omnigent-agents skill's driver is found by the host's install layout. Its references to the loop's role files no longer name them by file (#615).
- gatekeeper: a cloud session on a base without the merge queue and without `land.signed_squash_to` now lands over REST (`PUT pulls/N/merge`, squash, `sha` the gated head), which GitHub signs, so it needs no signing key; the adapter's `merge` takes this route whenever GitHub refuses GraphQL. A land that asks for `signed_squash_to` with no `ssh-keygen` installed is refused with that reason instead of a `FileNotFoundError` (#1712).
