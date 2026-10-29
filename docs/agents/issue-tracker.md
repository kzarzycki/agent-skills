# Issue tracker

Tracker: GitHub (engineering-loop's github.md)

## Settings

`components` are the `area:` labels, one per plugin plus `ci`; every issue carries at least one. `board` maps the loop's `Done` to the board's `Closed` column. "Item closed" sets that column for every closed issue: completed, not planned or duplicate (github.md § Board).

```yaml
components:
  content: the content plugin, writing-voice skills (content/)
  engineering: the engineering capability pack, its owned and imported skills (engineering/)
  gatekeeper: the gatekeeper package, its CLI and GitHub adapter (gatekeeper/)
  loop: the loop package, the engineering-loop skill and its roles (loop/)
  github: the github package, the GitHub tracker conventions and scripts (github/)
  chief-of-staff: the chief-of-staff package, its skill and the cos-console mod (chief-of-staff/)
  omnigent: the omnigent package, the Omnigent runner backend and its operations (omnigent/)
  research: the research plugin, multi-source research orchestration (research/)
  experimental: the experimental plugin, skills under iteration (experimental/)
  utilities: the utilities plugin, standalone skills (utilities/)
  vendoring: the vendoring package, the capability-pack tool, its routine and the update audit (vendoring/)
  ci: CI workflows, rulesets, mise tasks and the repo's own agent configuration

board:
  Done: Closed
```
