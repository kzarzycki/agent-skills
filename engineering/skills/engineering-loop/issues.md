# Issues and the board

The loop's issue conventions, the same in every project and on every tracker. How each
is done on a tracker is its realization file, read in place: [github.md](github.md) for
GitHub, with the issue-batch protocol `to-tickets` and `wayfinder` publish through. The
project's `docs/agents/issue-tracker.md` names that file in one line,
`Tracker: GitHub (engineering-loop's github.md)`, and adds only its own facts: Components,
Never on GitHub, and optionally Extra labels and Extra categories.

## States

Two labels are an issue's state; the others only classify it. Every issue starts as an
intent, whoever raises it, so each phase can run in a different session that acts on the
state it finds.

- **No state label:** an intent that needs triage: the owner's loose idea, bug or
  feedback, an agent's first write for a request, or what a PR leaves unfixed.
- **`needs-owner`:** waiting for the owner: a decision research can't settle (the
  questions are a comment), a step only they can take, or an approval loop.md §
  Approvals requires.
- **`ready-for-agent`:** specced. Only the spec step adds it, after writing the spec into
  that same issue. Where a tool owns an issue's body, the spec is a comment headed
  `## Spec`.

The `triage` skill's roles map as needs-triage = no state label, needs-info =
`needs-owner`.

## Labels

- **Category**, exactly one, set by whoever files the issue and corrected at triage:
  `bug` (something a user or the pipeline hits is wrong), `enhancement` (new or improved
  behaviour), `documentation` (only docs change), `chore` (tooling, CI, agent
  configuration; no behaviour changes), or one of the project's extra categories.
- **Component**, at least one, set with the category: where the change lands, from the
  project's list.
- **Size**, exactly one, added with `ready-for-agent`, once the code has been read. It is
  the size of the change, not a time estimate, and an intent has none: `size:XS` one line
  or one config value; `size:S` one module, the coordinator builds it; `size:M` several
  modules, one worker; `size:L` several workers or slices in one PR; `size:XL` too big
  for one spec: split it, or run it as a wayfinder map.

- **Approval**, `approved:spec` and `approved:plan` on the issue, `approved:merge` on the
  PR: added with an approval (SKILL.md, Approvals and proof), last when a person must
  approve, so adding it is how they approve.

A wayfinder map or ticket carries its `wayfinder:` label instead of a category, and no
component or size: it resolves a decision, not a change.

## Epics

An epic is an issue whose goal is an outcome the owner tracks; its work items are its
native sub-issues. It carries the `epic` label next to its category, so a board view can
filter for epics, and it closes when its outcome holds, that is when its sub-issues are
done. Prefer converting an existing issue whose spec already states the outcome over
filing a new one. An epic lands as its sub-issues' PRs, one per sub-issue, each off
main, with no epic or integration branch; a sub-issue whose work isn't usable yet lands
unexposed, and the sub-issue that exposes it comes last (SKILL.md, Land small and soon).
Two levels only: a sub-issue never has sub-issues of its own, since the
board's Parent issue field names only the direct parent and a grandchild would not show
under its epic.

## Board

The board shows every ticket in its loop stage, and every epic with its progress; the
realization file says how a ticket moves. The labels stay the state: when a move fails,
report it and carry on.

| Column | The ticket is here when | Moved by |
|---|---|---|
| `Intent` | filed, no state label | whoever files it |
| `Needs owner` | it has `needs-owner` | whoever parks it |
| `Ready` | specced, `ready-for-agent` | the spec step |
| `Build` | its draft PR is open | the coordinator |
| `Verify` | the verifier has the PR | the coordinator |
| `Done` | closed | whoever closes it |
