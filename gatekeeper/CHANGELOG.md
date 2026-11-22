# Changelog

## Unreleased

New entries are files in [changelog.d/](changelog.d/), one per issue, until a release moves
them here.

## 0.1.1 - 2026-11-22

- gatekeeper: `verdict` refuses an `Accepted on evidence:` phrase written inline in a `Manual:` line (a quote in prose, inline code or a fence takes nothing on evidence); verifier.md states the one-line form and the `Out of scope:` line, which blocks nothing (#1591).
- gatekeeper: `approve breakglass` and `breakglass-proof` record the owner's break-glass on one head with a red or missing required check, and `check merge` stops holding on that check while the record is current (#1722, part 1: the run-data proof and the refusals follow).
- gatekeeper: land verifies the break-glass proof from GitHub's run data (the failure on the head, its failed tests classified against main's runs, a re-run alone, a smoke run, earlier green runs) and leaves a verified PR unmerged for the owner's UI merge; `qualify` publishes the failed test ids as the `failed-tests` artifact and takes a `tests` input for the re-run (#1722, part 2).
- gatekeeper: no helper merges past the base's rules: `gh()` refuses the bypass flag and any REST merge field but the merge's own, the adapter's `merge` and `land` refuse any merge while a required check is red, pending or missing on the head, and a test asserts no script of the pack holds the bypass flag (#1722, part 3).
- gatekeeper: under `land.queue: mergify`, `approve merge` and `record verdict` each end by queueing the PR when `check merge` passes, and print what is missing otherwise; `check stalled` lists every open PR that has its go and a satisfied verdict but is neither queued nor merged (#1741).
- gatekeeper: behaviour change: session links now stay in squash bodies, PR bodies and comments. `land` merges with GitHub's default squash body (no `--body`, no REST `commit_message`) and edits no PR body or comment before a merge, an enqueue or a Mergify hand-over; `check merge` no longer names a text holding a session link, and the `commit-msg` verb is gone, so drop any hook that runs it (#1764).
- gatekeeper: a test pins that two successive merges of the base carry the old head's verdict (#1768).

## 0.1.0 - 2026-11-22

- gatekeeper: the first release, split out of `engineering`. The `gatekeeper` skill holds `scripts/gatekeeper.py`, its GitHub adapter `scripts/github_adapter.py` and the `scripts/approvals.py` shim, with their tests; it depends on no other package. `brief` and `release` leave it for the loop's own `scripts/loop.py` (#615).
- gatekeeper: a team that installs only the gatekeeper finds the policy it reads in this skill. `policy.md` holds every policy key with its type, default and an example block, and issue-tracker.md's settings block, which the loop's SKILL.md § Settings held; the gate's rules stay in the loop's SKILL.md § Approvals and proof. The helpers it loads from beside itself (`acceptance.py`, `events.py`, `folding.py`) and `events.md` move with it, and the omnigent-agents skill's driver is found by the host's install layout. Its references to the loop's role files no longer name them by file (#615).
- gatekeeper: a cloud session on a base without the merge queue and without `land.signed_squash_to` now lands over REST (`PUT pulls/N/merge`, squash, `sha` the gated head), which GitHub signs, so it needs no signing key; the adapter's `merge` takes this route whenever GitHub refuses GraphQL. A land that asks for `signed_squash_to` with no `ssh-keygen` installed is refused with that reason instead of a `FileNotFoundError` (#1712).
