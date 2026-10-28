# Issue tracker

Tracker: GitHub (engineering-loop's github.md)

## Settings

`components` are the `area:` labels, one per plugin plus `ci`; every issue carries at least one. `board` maps the loop's `Done` to the board's `Closed` column. "Item closed" sets that column for every closed issue: completed, not planned or duplicate (github.md § Board).

```yaml
components:
  content: the content plugin, writing-voice skills (content/)
  engineering: the engineering capability pack, its owned and imported skills (engineering/)
  research: the research plugin, multi-source research orchestration (research/)
  playwright: the Playwright MCP plugin and its skill (playwright/)
  experimental: the experimental plugin, skills under iteration (experimental/)
  utilities: the utilities plugin, standalone skills (utilities/)
  ci: CI workflows, rulesets, mise tasks, tools/ and the repo's own agent configuration

board:
  Done: Closed
```
