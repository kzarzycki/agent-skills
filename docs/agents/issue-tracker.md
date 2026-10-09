Tracker: GitHub (engineering-loop's github.md)

## Components

Where a change lands: one label per local plugin, plus CI. Every issue carries at
least one. `mise run setup:github` creates each label.

- `area:workflow`: the workflow plugin, the Spec → Tech Design pipeline (`workflow/`).
- `area:research`: the research plugin, multi-source research orchestration (`research/`).
- `area:engineering`: the engineering capability pack, its owned and imported skills (`engineering/`).
- `area:content`: the content plugin, writing-voice skills (`content/`).
- `area:playwright`: the Playwright MCP plugin and its skill (`playwright/`).
- `area:experimental`: the experimental plugin, skills under iteration (`experimental/`).
- `area:utilities`: the utilities plugin, standalone skills (`utilities/`).
- `area:ci`: CI workflows, rulesets, mise tasks, `tools/` and the repo's own agent configuration.

## Never on GitHub

Credentials, keys and tokens.

## Extra labels

- `engineering-routine:blocked`: the upstream-intake routine stopped and needs a person (`engineering/ROUTINE.md`).
