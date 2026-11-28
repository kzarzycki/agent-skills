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
  loop: the loop plugin, the engineering-loop skill (loop/)
  gatekeeper: the gatekeeper plugin, the merge gate and its proofs (gatekeeper/)
  github: the github plugin, the GitHub tracker and forge conventions (github/)
  omnigent: the omnigent plugin, Omnigent as the agent runner (omnigent/)
  chief-of-staff: the chief-of-staff plugin, supervision over many leads, and its cos-console mod (chief-of-staff/)
  vendoring: the vendoring package, the capability-pack tool, its routine and the update audit (vendoring/)
  ci: CI workflows, rulesets, mise tasks, tools/ and the repo's own agent configuration

board:
  Done: Closed
```
