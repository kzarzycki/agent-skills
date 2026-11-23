# Changelog

## Unreleased

New entries are files in [changelog.d/](changelog.d/), one per issue, until a release moves
them here.

## 0.1.2 - 2026-11-22

- omnigent-agents: the cloud brief waits on a run with one tracked `wait-for --budget <the run's expected length>` instead of a `--budget 480` loop, and `wait-for --budget`'s help says its default is for a foreground call (#1790).
- omnigent-agents: `supervise --console` wakes a followed lead quiet an hour whose PR has a verdict on its current head over an hour old with no push or go since, with one `news` line per PR and head naming the step it owes (#1802).
- omnigent-agents: `start` refuses a second worker or verifier of a PR while one with the same role and PR runs, and `reap --force <id>` stops and finishes that running one, its open PR included (#1806).
- omnigent-agents: `relay` and `send` to a lead print a warning, and still deliver, when the message names an issue outside the lead's request, its epic or the epic's sub-issues (#1830).

## 0.1.1 - 2026-11-22

- orchestrating-agents: a session whose result is taken is archived at one shared point, `finish_delivered`: `run`, `wait`, `reap`, the supervisor's relay of a child's `DONE` report or failure and of a followed lead's `DONE` all call it, and a kept session (`--keep`, an open card, a PR hold, background work) stays open; `start --keep` labels a session so the supervisor leaves it open; a run that ended failed, cancelled or errored is finished too, a stale `omnigent.keep` label holds nothing, and archiving a parent finishes its idle children (#1579).
- omnigent-agents: `supervise --console` acts on a `STILL WORKING` that nothing wakes or that hands work back (#1753). A wait on a process the harness does not track ("waiting on pid 4242", "its pid is 4242", a pid file or a log or output file, with no `--notify`, `LOOP_NOTIFY`, child, CI or `Waits:` line), or in a cloud session on a background subagent, gets one nudge (`LEAD_UNTRACKED`) saying why nothing wakes it and how to wait instead, then act if the lead ends that way again; it used to record the turn as a named wait and leave the lead idle until the no-progress deadline. A hand-back, a `Handback: #<n> <what>` line or prose such as `#12 READY` or `#12 ... is yours`, goes to the session it notifies at once.
- omnigent-agents: `ssh` runs only short read-only checks and setup steps (#1754).
- omnigent-agents: a cloud worker's preamble no longer tells it to leave the session link out of its commit messages (#1764).
- omnigent-agents: Host steps over SSH points to orchestrating-agents' rule *Host work* instead of repeating it (#1765).
- omnigent-agents: a follow-up run updates a PR branch by a merge of the base, not a rebase (#1768).

## 0.1.0 - 2026-11-22

- omnigent: the first release, split out of `engineering`. It holds `omnigent-agents` (the Omnigent backend, formerly orchestrating-agents' `backends/omnigent.md`, and its driver `scripts/omnigent_agent.py`), `operating-omnigent` and `omnigent-telemetry`, with the cloud launcher `claude_cloud.py` and its client `claude_environments.py`, which `orchestrating-agents` held. It gains its `engineering` dependency when `engineering` drops its dependency on `omnigent` (#615).
- The full test suite is green again after 0.34.1: the remote-loop fake answers `GET /v1/hosts`, the cloud-floor start pins its launch dir, the picked-host start writes its report under a local folder, and the installed-pack settings test skips a setting the pinned release predates (#1701).
