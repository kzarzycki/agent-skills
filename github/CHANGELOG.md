# Changelog

## Unreleased

New entries are files in [changelog.d/](changelog.d/), one per issue, until a release moves
them here.

## 0.1.5 - 2026-11-26

- github-tracker: its forwarders resolve the installed copy of the pack's skills, never a developer checkout: a checkout (a git tree holding the marketplace file) is searched only where `AGENT_SKILLS_CHECKOUT` is set, as the pack's own tests set it (#2485).
- github: the pack's own CI finds its scripts in the checkout it runs in: a checkout counts when it is the `GITHUB_WORKSPACE` of the job running there, so main's push run, the nightly and the tag check run `nightly.py moved` again (#2560).

## 0.1.4 - 2026-11-25

- github-tracker: github.md, Assignee says the claim's record also names the lead's Omnigent session and sets the issue's optional `Session` field (#2324).

## 0.1.3 - 2026-11-24

- github-tracker: `labels.py` knows `loop:hold`, so label sync creates it and no longer deletes it when nothing carries it (#2162).

## 0.1.2 - 2026-11-23

- gh-quota: a cloud environment's setup script can install the shim for all its sessions; this repo's `.claude/cloud-setup.sh` does, from a pinned commit with both files' sums checked (#2049).

## 0.1.1 - 2026-11-23

- gh-quota (new): a logging `gh` shim that records one line per call (time, host, session, cwd, parent command, masked arguments) without changing gh's output or exit code, `gh_quota.py report` ranking callers over the last N minutes, `counts` to post a tally from a machine nobody else reads, and `rate`, the account's calls/min from the free `gh api rate_limit` (#1994).
- gh-quota: the report reads a flag value with a space (`-H 'Accept: x'`) as one value, the shim masks a joined `secret set -bVALUE` and a token in its parent command, and `rate` no longer counts a reply from another bucket as a whole bucket spent (#2001).

## 0.1.0 - 2026-11-22

- github: the first release, split out of `engineering`. The `github-tracker` skill holds `github.md` (the GitHub tracker's realization file, formerly engineering-loop's), `scripts/labels.py`, `scripts/board.py` and `scripts/rulesets.py`; it depends on `gatekeeper`, whose label names and settings reader both scripts import (#615).
