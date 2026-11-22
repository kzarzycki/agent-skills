# Changelog

## Unreleased

New entries are files in [changelog.d/](changelog.d/), one per issue, until a release moves
them here.

## 0.1.0 - 2026-11-22

- omnigent: the first release, split out of `engineering`. It holds `omnigent-agents` (the Omnigent backend, formerly orchestrating-agents' `backends/omnigent.md`, and its driver `scripts/omnigent_agent.py`), `operating-omnigent` and `omnigent-telemetry`, with the cloud launcher `claude_cloud.py` and its client `claude_environments.py`, which `orchestrating-agents` held. It gains its `engineering` dependency when `engineering` drops its dependency on `omnigent` (#615).
- The full test suite is green again after 0.34.1: the remote-loop fake answers `GET /v1/hosts`, the cloud-floor start pins its launch dir, the picked-host start writes its report under a local folder, and the installed-pack settings test skips a setting the pinned release predates (#1701).
