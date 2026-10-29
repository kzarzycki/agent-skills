# Layers, packages and contracts

The skills form a stack of layers, and the repo splits into packages a team installs by
need. This note holds the layers, the package map and the contracts the gatekeeper, the
loop and an external flow engine agree on. `tests/test_skill_layers.py` reads the layer
map below and enforces the rule.

## Layers

| Layer | Holds | May name |
|---|---|---|
| 4 supervision | one person's view over many leads and repos | layers 0 to 4 |
| 3 flow | who sequences the work and runs the roles | layers 0 to 3 |
| 2 gatekeeper | may this change take its next step: build, queue, merge | layers 0 to 2 |
| 1 craft | methods, with tool notes where a team picks the tool | layers 0 and 1 |
| 0 adapters | the code behind a port | layer 0, and the skill whose port it implements |
| tooling | the repo's own vendoring tools, outside the stack | other tooling only |

A skill names only skills of its own layer or below, so a team can take a layer and
everything under it without the layers above. An adapter also names the skill that
defines the port it implements, since an adapter depends on its port, not the other way
round; the map records that as `implements:`, not as an exception, and an `implements:`
entry no mention needs any more fails the test, as a stale exception does. Tooling serves the repo,
not a team, so it names nothing in the stack, and any skill may name it.

The test flags, in any file of a skill folder, a mention of a skill the rule forbids. A
hyphenated name counts as a whole word, which also catches a relative path into that skill
(`../engineering-loop/scripts`). A one-word name is often a plain word (`pr`, `implement`,
`research`), so it counts only as a reference to the skill: in
backticks (`retro`, or invoked as `/retro`), followed by `skill`, or as a path segment
(`skills/retro/`).

### Layer map

Every skill under a local plugin has an entry, so a new skill gets a layer when it is
added. `exceptions` lists today's upward mentions, each `skill -> named skill` with its
reason and the story that removes it; an exception that no longer matches fails the test,
so the list only shrinks.

```yaml
skills:
  chief-of-staff: {layer: 4}
  overnight-run: {layer: 4}   # the chief of staff's procedure for an unattended run
  engineering-loop: {layer: 3}
  gatekeeper: {layer: 2}
  ask-matt: {layer: 1}
  audit-third-party-software: {layer: 1}
  browsing: {layer: 1}
  claude-handoff: {layer: 1}
  code-review: {layer: 1}
  codebase-design: {layer: 1}
  context-extractor: {layer: 1}
  demo: {layer: 1}
  diagnosing-bugs: {layer: 1}
  domain-modeling: {layer: 1}
  grill-with-docs: {layer: 1}
  grilling: {layer: 1}
  handoff: {layer: 1}
  implement: {layer: 1}
  implement-spec: {layer: 1}
  improve-codebase-architecture: {layer: 1}
  loop-me: {layer: 1}
  orchestrating-agents: {layer: 1}
  pr: {layer: 1}
  prototype: {layer: 1}
  research: {layer: 1}
  retro: {layer: 1}
  tdd: {layer: 1}
  teach: {layer: 1}
  to-spec: {layer: 1}
  to-tickets: {layer: 1}
  triage: {layer: 1}
  wait-what: {layer: 1}
  wayfinder: {layer: 1}
  wizard: {layer: 1}
  chatgpt-deep-research: {layer: 1}
  claude-ai-deep-research: {layer: 1}
  deep-research: {layer: 1}
  gemini-deep-research: {layer: 1}
  voice-dna: {layer: 1}
  communicating-in-html: {layer: 1}
  communicating-in-mdx: {layer: 1}
  drawio-live: {layer: 1}
  find-conversation: {layer: 1}
  github-project-board-setup: {layer: 0, implements: [engineering-loop]}   # tracker and forge ports
  github-tracker: {layer: 0, implements: [engineering-loop, gatekeeper]}   # tracker, forge and evidence ports
  omnigent-agents: {layer: 0, implements: [orchestrating-agents]}   # runner port
  operating-omnigent: {layer: 0, implements: [orchestrating-agents]}   # runner port
  omnigent-telemetry: {layer: 0}
  update-delta-audit: {layer: tooling}
  vendoring: {layer: tooling}

exceptions:
  omnigent-agents -> engineering-loop: {reason: "the runner starts the loop's roles and reads its deny list and gate-slot directory", removed_by: "#631"}
```

## Package map

| Package | Layer | Holds |
|---|---|---|
| `chief-of-staff` | 4 | `chief-of-staff`, the cos-console mod |
| `loop` | 3 | `engineering-loop` with its lead, worker and verifier roles and `loop.py` (`brief`, `release`); the skill keeps its name, so every `AGENTS.md` line and brief naming it keeps working |
| `gatekeeper` | 2 | `gatekeeper`: the gatekeeper CLI and its GitHub adapter |
| `engineering` | 1 | every craft skill above at layer 1 under `engineering/`, `orchestrating-agents` with its native backend, `browsing` |
| `omnigent` | 0 | `omnigent-agents` (the runner backend and its driver), `operating-omnigent`, `omnigent-telemetry` |
| `github` | 0 | `github-tracker` (`github.md`, `board.py`, `labels.py`), `github-project-board-setup` |
| `vendoring` | tooling | `vendoring` (the capability-pack tool and `ROUTINE.md`), `update-delta-audit` |
| `research`, `utilities`, `content`, `experimental` | 1 (`overnight-run` 4) | unchanged |

A package declares the packages it uses, and installing it installs them:

- Claude Code: `plugin.json` `dependencies` lists each by plugin name, which resolves in
  this marketplace.
- APM: `apm.yml` lists each as `git: kzarzycki/agent-skills/<package>` with a range of its
  own tags (`ref: ^0.1.0` matches `<package>-v0.1.x`). A `path: ../<package>` entry would
  read the sibling folder, but `apm pack` refuses a package with one, and a consumer's
  `apm install --frozen` resolves it with the parent's range, which fails once the packages
  version apart. The git form needs each package's tag on the forge before a release that
  depends on it.

For one release line `engineering` keeps pulling the others in, so a project pinned to it
keeps working. A script that needs another package's skill finds it where the host
installed it (a sibling skill folder, a sibling plugin, or Claude Code's plugin cache) and
exits naming the skill to install when it is missing.

## Gatekeeper CLI

The gatekeeper answers one question, may this change take its next step, from proof on the
forge and the team's policy.

| Verb | Does |
|---|---|
| `check build\|queue\|merge` | whether the change may be built, enter a batching merge queue, or merge |
| `record approval\|verdict\|checks` | records a person's approval, a verifier report as a review, or a check pass on the head |
| `land [--wait]` | every merge proof, then marks the PR ready and merges it, pinned to the head |
| `report [--json]` | reads a verifier report as the gatekeeper does; `--json` prints its facts |
| `batch` | the batching queue's proof for one PR in a batch (today's verb) |
| `delegate` | the delegated approver's `approved:merge`, feature branch only (today's verb) |

Exit codes, for every verb:

- `0`: allowed, or done.
- `1`: refused, with one line per missing proof.
- `3`: waiting (pending checks, a forge state not computed yet): run it again.

`brief` (a verifier pass's brief) and `release` (removes the assignee the loop added) are
flow operations, not gate decisions, so they are the loop's own script, `loop.py`, which
reads the PR and the issue through the gatekeeper's ports.

## Verifier report

The verifier writes its report once, for people to read. Its facts:

- the head SHA it reviewed;
- verdict counts (`VERDICT: <n> blocker, <n> major, <n> minor`);
- whether the spec is satisfied (`SATISFIED: yes|no`);
- the risk (`Risk: low|high — <reason>`);
- the findings, each under a heading with its severity;
- a question for the owner, when there is one.

`report --json` derives the JSON from that text; the agent never writes the JSON, so the
readable report and the machine one cannot disagree.

## Ports

The gatekeeper and the loop reach outside tools only through ports. An adapter implements
a port for one tool.

| Port | Asked |
|---|---|
| tracker | read an item, comment, set a label or state, its parent, its children, create one |
| forge | the PR for a branch, its head SHA, reviews on the head, checks, mark ready, merge pinned to the head |
| evidence | approvals, verdicts and check passes, keyed by head SHA |
| checks | run `changed`, `check`, `all`: an exit code and a log; no adapter, the commands themselves |
| runner | start, message, wait, watch, list, close an agent |

GitHub implements tracker, forge and evidence (`github`); Omnigent implements runner
(`omnigent`), and `orchestrating-agents`' native backend is the runner with no adapter.

## Policy keys

The gatekeeper's policy is the settings block of today's loop.md, which #613 moves to
`docs/agents/gatekeeper.md`:

- today's sections: `spec`, `loop`, `practice`, `risk`, `plan`, `signoff`, `bot`, `land`,
  `carry_over_main`;
- `checks: {changed, check, all}`: the command for each check;
- `adapters: {tracker, forge, evidence}`: the adapter for each port.

Only the gatekeeper reads the policy, and only the team's file, so a local answer and CI's
agree. Agents read prose instructions, where a person's `CLAUDE.local.md` overrides the
team's: a person who skips a step through their agent skips it on their machine, and CI
still refuses the merge.

## Split manifest

A split stage turns one spec into child items. Its manifest lists each child item with:

- a title;
- its spec;
- what blocks it (the other items it waits for).
