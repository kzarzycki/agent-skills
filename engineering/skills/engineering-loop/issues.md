# Issues and the board

The loop's issue conventions, the same in every project. The project's
`docs/agents/issue-tracker.md` adds only its own facts: Repo, Components, Never on GitHub,
Extra labels, and optionally Extra categories. [issue-tracker-github.md](issue-tracker-github.md)
is a starting point for that file on GitHub, with the issue-batch protocol `to-tickets`
and `wayfinder` publish through.

## States

Two labels are an issue's state; the others only classify it. Every issue starts as an
intent, whoever raises it, so each phase can run in a different session that acts on the
state it finds.

- **No state label:** an intent that needs triage: the owner's loose idea, bug or
  feedback, an agent's first write for a request, or what a PR leaves unfixed.
- **`needs-owner`:** waiting for the owner: a decision research can't settle (the
  questions are a comment), or a step only they can take.
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

A wayfinder map or ticket carries its `wayfinder:` label instead of a category, and no
component or size: it resolves a decision, not a change.

## Board

A GitHub Projects board linked to the repo shows every ticket in its loop stage (the
`github-project-board-setup` skill of the `utilities` plugin creates one).
`python3 scripts/board.py <issue> <column>` adds the issue when it is missing and sets
its column. The labels stay the state: when a
move fails, report it and carry on. Only this command moves a ticket: the board's own
"Item closed" and "Auto-add" workflows stay off, as they are on a board created through
the API.

| Column | The ticket is here when | Moved by |
|---|---|---|
| `Intent` | filed, no state label | whoever files it |
| `Needs owner` | it has `needs-owner` | whoever parks it |
| `Ready` | specced, `ready-for-agent` | the spec step |
| `Build` | its draft PR is open | the coordinator |
| `Verify` | the verifier has the PR | the coordinator |
| `Done` | closed | whoever closes it |
