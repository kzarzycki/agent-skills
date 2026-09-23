---
name: setup-engineering-workflow-for-apm
description: Configure repository-owned APM instruction sources for the engineering workflow, then compile and audit them with agent-sync. Run before first use of the other engineering skills.
disable-model-invocation: true
---

# Setup Engineering Workflow for APM

Write only the two repository-owned sources below and let `mise run agent-sync` compile
them. Never write `AGENTS.md`, `CLAUDE.md` or another compiled target; the compiler owns
them.

| Source | Template |
|---|---|
| `.apm/instructions/engineering-workflow.md` | [templates/project-guidance.md](./templates/project-guidance.md) |
| `docs/agents/issue-tracker.md` | [templates/issue-tracker-github.md](./templates/issue-tracker-github.md) |

The tracker defaults to GitHub Issues. When repository evidence (remotes, tracker
references) or the user points to another tracker, adapt the marked section of
`docs/agents/issue-tracker.md` to that tracker's real commands and conventions. Read the
existing sources, the domain docs (`CONTEXT.md`, `CONTEXT-MAP.md`, `docs/adr/`), and the
root agent files as compiled output only.

## Marked sections

The skill owns only the text between these markers:

```markdown
<!-- engineering-workflow:start -->
<!-- engineering-workflow:end -->
```

- A file with only one marker, or with either marker more than once, is malformed:
  report it and stop before writing anything.
- Markers present: replace only the content between them.
- Markers absent: append one marked section without trimming or reformatting the
  existing content.
- File absent: create it with one marked section.

Every byte outside the markers is preserved.

## Proposal and approval

Before writing, show every proposed source path, a unified diff for each (new files
included), and a note that approval writes exactly these changes and then runs
`mise run agent-sync`. Ask the user to approve or edit. A rejection or an edit request
writes nothing and runs nothing.

After approval, write exactly the displayed marked-section changes, touch no other
path, and run exactly this, never an underlying APM command or a second compile step:

```sh
mise run agent-sync
```

If compilation or its audit fails, report the output and leave the sources for the user
to inspect; don't repair, replace or delete compiled targets. If it succeeds, report the
two source paths and the compiler result.

A second run with the same choices proposes no diff and rewrites nothing. It runs
`mise run agent-sync` to recheck compiled output only after a fresh, explicit
confirmation for that recheck; approval from a prior run or from a source-change
proposal does not carry over.

<!-- setup-fixture-protocol
version: 1
fixture: tests/fixtures/setup-project
markers:
  start: "<!-- engineering-workflow:start -->"
  end: "<!-- engineering-workflow:end -->"
confirmations:
  source_changes: required
  no_diff_recheck: fresh
source_files:
  - template: templates/project-guidance.md
    destination: .apm/instructions/engineering-workflow.md
  - template: templates/issue-tracker-github.md
    destination: docs/agents/issue-tracker.md
sync_command:
  - mise
  - run
  - agent-sync
-->
