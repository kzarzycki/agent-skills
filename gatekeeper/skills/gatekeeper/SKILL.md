---
name: gatekeeper
description: Decide whether a change may take its next step - be built, enter a batching merge queue, or merge - from proof on the forge and the team's policy in docs/agents/gatekeeper.md, and record the proofs (an approval, a verifier verdict, a check pass). Use when running a merge gate or required check, recording an approval, a verdict or a check pass, or landing a PR on its proofs.
metadata:
  requires: "gh uv"
---

# Gatekeeper

The gatekeeper answers one question: may this change take its next step? It reads the
proof on the forge (approval records, verifier reviews, check passes) and the team's policy,
and never decides on an agent's word, so its answer on a laptop is CI's answer.

Run `uv run <this skill's folder>/scripts/gatekeeper.py <verb>` anywhere in the checkout: it
reads `docs/agents/` at the checkout's root. `uv run` installs PyYAML, the one package it
needs beyond the standard library, from the script's inline header; a bare `python3` without
it exits with one line saying so. It needs Python 3.9 or later and `gh`, logged in, for GitHub.

| Verb | Does |
|---|---|
| `check build\|queue\|merge` | whether the change may be built, enter a batching merge queue, or merge |
| `record approval\|verdict\|checks` | records a person's approval, a verifier report as a review, or a check pass on the head |
| `land [--wait]` | every merge proof, then marks the PR ready and merges it, pinned to the head |
| `report [--json]` | reads a verifier report as the gatekeeper does; `--json` prints its facts |
| `batch` | the batching queue's proof for one PR in a batch |
| `delegate` | the delegated approver's `approved:merge`, feature branch only |

Exit codes, for every verb: `0` allowed or done; `1` refused, with one line per missing
proof; `3` waiting (pending checks, a forge state not computed yet): run it again. The
script's docstring is the manual: every proof each verb checks and every record it writes.

## Files

- `scripts/gatekeeper.py`: the CLI, the policy reader and the gate.
- `scripts/github_adapter.py`: the GitHub adapter. The gatekeeper reaches the tracker, the
  forge and the evidence store only through ports, each served by the adapter the policy's
  `adapters` section names; GitHub's is the only one, and `gatekeeper.py` loads it from
  beside itself.
- [policy.md](policy.md): every policy key, its type and default, the rules the policy
  states, the batching queue, carry-over of a merge of main, the opt-out, and
  issue-tracker.md's settings block. Read it when writing or changing a project's policy, or
  when a refusal names a key.
- `scripts/approvals.py`: the gatekeeper's former name, kept for one release line. It runs
  `gatekeeper.py` with today's verbs (`approve`, `verdict`, `local-ci`), so a project's
  `approvals.py` command keeps working.

## Policy

The policy is the fenced `yaml` block under `## Policy` in the project's
`docs/agents/gatekeeper.md`, and only the gatekeeper reads it. Without that file it reads the
same block under `docs/agents/loop.md`'s `## Settings`, with a deprecation line, and it
refuses a project with both, since two sources of the bar would drift. It refuses, naming
the key, a section or key it doesn't know and a value of the wrong type, so a mistyped
setting is never read as a rule nobody wrote. [policy.md](policy.md) has every key, with an
example block, and `SCHEMA` in `gatekeeper.py` is the same list as code. Label names come
from `docs/agents/issue-tracker.md`'s settings block (policy.md, Tracker settings).

## Verifier report

`record verdict` posts a verifier's report as one PR review on the commit it names, and
`report [--json]` reads it the same way, so a report is written once, for people, in this
shape (anything else in it is prose the review carries):

- near the top, `Verifier: <family>, pass <n>`, such as `Verifier: codex/terra-6.1/med, pass
  5`. A lower tier (`mid` or `small`) is a word of its own after the family, `Verifier:
  codex/terra-6.1/med mid, pass 1`: `check merge` refuses a high-risk change whose newest
  verdict names one, and reads a line without one as the default tier. Text after the pass
  number (`(merge of main)`) goes into the review's first line;
- per finding, a heading `### <id> (<blocker|major|minor>) <path>:<line>: <title>`, its body
  up to the next heading outside a code fence. Any other `### ` heading is a sub-heading;
- at the end, `Head: <sha>`, the full commit reviewed, then `VERDICT: <n> blocker, <n>
  major, <n> minor`, `SATISFIED: yes|no` and `Risk: low — <reason>` or `Risk: high —
  <reason>`.

It refuses a report without the `Head:`, `Verifier:` or `Risk:` line, a `### ` heading with a
`(<severity>)` it can't read, and finding headings that don't add up to the `VERDICT:`
counts. A question for the owner goes in `<report>.question` beside it, which `report --json`
prints.

## The cap

The cap is 5 passes, unless the project's gatekeeper.md sets its own with `cap` under `loop`
in its policy. It is the last verifier pass that runs on its own: a blocker or major still
open after it makes the change `risk:high`, so its merge waits for the owner.
`gatekeeper.py` reads the default from this line, so this is the one place to change it.
