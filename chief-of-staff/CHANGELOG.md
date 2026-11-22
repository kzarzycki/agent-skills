# Changelog

## Unreleased

New entries are files in [changelog.d/](changelog.d/), one per issue, until a release moves
them here.

## 0.1.1 - 2026-11-22

- chief-of-staff: the one-writer rule names a lead that merges, not rebases, in a shared checkout (#1768).

## 0.1.0 - 2026-11-22

- chief-of-staff: the first release, split out of `engineering`. It holds the `chief-of-staff` skill and, under `cos-console/`, the cos-console mod, still its own plugin so it stays enabled only in the chief of staff's home. It depends on `loop` and `omnigent`; `cos_page.py` finds `omnigent_agent.py` in the `omnigent-agents` skill wherever the host installed it (#615).
