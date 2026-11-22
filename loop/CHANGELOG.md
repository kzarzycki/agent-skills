# Changelog

## Unreleased

New entries are files in [changelog.d/](changelog.d/), one per issue, until a release moves
them here.

## 0.1.0 - 2026-11-22

- loop: the first release, split out of `engineering`. It holds the `engineering-loop` skill, under its old name, with its lead, worker and verifier roles, and `scripts/loop.py`, which takes over `brief` (a verifier pass's brief) and `release` (removes the assignee the loop added) from the gatekeeper. It depends on `gatekeeper` and `github`; it gains `engineering` when `engineering` drops its dependency on `loop` (#615).
- engineering-loop: SKILL.md § Settings points at the `gatekeeper` skill's policy.md for each key, since the gatekeeper ships its own policy reference; § Approvals and proof stays. `cloud_verifier.py` and `nightly.py` stay with the loop and read the gatekeeper's `folding.py` and `events.py` through the host's install layout (#615).
- engineering-loop: the script paths engineering 0.25.0 shipped in this skill keep working for this release line: `scripts/approvals.py` and `scripts/gatekeeper.py` run the `gatekeeper` skill's gatekeeper.py (`approvals.py brief` and `release` run `scripts/loop.py`), `scripts/acceptance.py` and `scripts/events.py` the `gatekeeper` skill's, `scripts/board.py`, `scripts/labels.py` and `scripts/rulesets.py` the `github-tracker` skill's, and `scripts/browse.py` the `browsing` skill's, with the same arguments, stdin and exit code, after one deprecation line on stderr naming the new path. They go away with the release that drops `engineering`'s dependencies on the packages split out of it (#615).
- engineering-loop: `approvals.py brief` embeds the PR's title and body verbatim, each in a code fence longer than any backtick run inside it, and lists its labels, so a verifier with no GitHub access (a cloud VM) can check a criterion about the PR text without a `Not run:` line. The linked and closing issues were already in its `Spec:` line (#1697).
- engineering-loop: the repo's committed `.claude/settings.json` sets `attribution.sessionUrl` to `false`, so a cloud session stops being told to add the claude.ai session link to its commits and PR bodies. The footer the cloud GitHub proxy appends has no setting; the gatekeeper's footer regex still strips it (#1708).
- engineering-loop: the gate of record runs once, on the head the verifier is satisfied with, and again on any later head; review heads get only the narrow checks (tests and lint for what changed). A gate failure now shows after the verifier, so its fix needs a short re-verify of the delta, and a fix round runs the narrow checks only, with no gate on a review head (#1715).
