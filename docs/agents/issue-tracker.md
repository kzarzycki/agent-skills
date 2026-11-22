# Issue tracker

Tracker: GitHub (engineering-loop's github.md)

## Settings

`components` are the `area:` labels, one per plugin plus `ci`; every issue carries at least one. `board` maps the loop's `Done` to the board's `Closed` column. "Item closed" sets that column for every closed issue: completed, not planned or duplicate (github.md § Board).

```yaml
components:
  content: the content plugin, writing-voice skills (content/)
  engineering: the engineering capability pack, its owned and imported skills (engineering/)
  research: the research plugin, multi-source research orchestration (research/)
  experimental: the experimental plugin, skills under iteration (experimental/)
  utilities: the utilities plugin, standalone skills (utilities/)
  gatekeeper: the gatekeeper package, the merge gate and its policy reader (gatekeeper/)
  loop: the loop package, the engineering loop's roles (loop/)
  github: the github package, the GitHub tracker and board setup (github/)
  chief-of-staff: the chief-of-staff package and its cos-console mod (chief-of-staff/)
  omnigent: the omnigent package, the Omnigent runner, its operation and telemetry (omnigent/)
  vendoring: the vendoring package, the capability-pack tool, its routine and the update audit (vendoring/)
  ci: CI workflows, rulesets, mise tasks and the repo's own agent configuration

board:
  Done: Closed
```
