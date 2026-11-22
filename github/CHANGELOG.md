# Changelog

## Unreleased

New entries are files in [changelog.d/](changelog.d/), one per issue, until a release moves
them here.

## 0.1.0 - 2026-11-22

- github: the first release, split out of `engineering`. The `github-tracker` skill holds `github.md` (the GitHub tracker's realization file, formerly engineering-loop's), `scripts/labels.py`, `scripts/board.py` and `scripts/rulesets.py`; it depends on `gatekeeper`, whose label names and settings reader both scripts import (#615).
