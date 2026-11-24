# Changelog

## Unreleased

New entries are files in [changelog.d/](changelog.d/), one per issue, until a release moves
them here.

## 0.1.4 - 2026-11-24

- chief-of-staff: the `USER NEEDED` row covers only a lead with no card open: a lead's own question goes back to it to ask on its card, and one that spans projects goes on the chief of staff's own card (#2170).
- chief-of-staff: a `card-waiting` event (a lead's card unanswered past 4 hours) is answered only under the owner's standing decision to act in their name; otherwise nothing is sent (#2170).
- chief-of-staff: Authority says a lead records an approval the owner gave on its own card, and a brief never tells a lead not to run `approve` (#2170).

## 0.1.3 - 2026-11-23

- `chief-of-staff`: owner-approval delegation is an optional mode the owner turns on and off on the root board, under which each project manager answers its own project's question cards and the chief of staff its own leads' and cross-project ones, through the card, logged with its undo, with the owner-only kinds left on the card and `loop.delegate_spec: false` as a project's opt-out; and a tree of coordinators (nodes, one writer per board, cards as the owner channel, asks down and reports up, the decision log) is described once in the skill, with the board's dated archive (#2044).

## 0.1.2 - 2026-11-22

- chief-of-staff: a lead takes one request or epic; a new, unrelated item goes to a fresh lead, never to one that is running or done (#1830).

## 0.1.1 - 2026-11-22

- chief-of-staff: the one-writer rule names a lead that merges, not rebases, in a shared checkout (#1768).

## 0.1.0 - 2026-11-22

- chief-of-staff: the first release, split out of `engineering`. It holds the `chief-of-staff` skill and, under `cos-console/`, the cos-console mod, still its own plugin so it stays enabled only in the chief of staff's home. It depends on `loop` and `omnigent`; `cos_page.py` finds `omnigent_agent.py` in the `omnigent-agents` skill wherever the host installed it (#615).
