# Changelog

## 0.6.0 - 2026-09-23

- Tuned all 26 imported skills, the setup overlay and the owned skills
  (`audit-third-party-software`, `context-extractor`, `operating-omnigent`)
  for current models:
  generic advice, pressure language and step choreography removed, delegation
  left to judgment, harness- and tracker-neutral wording. Formats, gates and
  cross-references are kept. Supporting files that only repeated their skill
  were merged into it.
- Tuned skills are now owned overlays. The GitHub issue-batch patch is folded
  into `to-tickets` and `wayfinder`, and the patch series is gone.
- Upstream intake is now semantic: an upstream change under a tuned skill stops
  the refresh with its delta saved until a port or decline is recorded in
  `upstream-intake.yml`. The first intake ports upstream `c55ee46` (Merge
  Danger template in `pr`).
- `upstream-intake.yml` is validated on every check, and the package-test
  hang guard is 600 s (the APM install tests take about 110 s).
- Refreshed upstream from `74ca5fe` to `c55ee46` (`v1.2.3-54-gc55ee46`).
- Behaviour changes: `to-spec` publishes through the tracker document's issue-batch rules;
  `code-review` diffs against the merge-base and includes uncommitted and
  untracked files; `tdd` treats seams agreed in the spec as confirmed;
  `context-extractor` proposes edits to the sources when agent files are
  compiled (for example through APM); the third-party audit drafts the vendor issue and never files it.

## 0.4.0 - 2026-09-01

- Imported four skills from the upstream `in-progress` bucket at
  `6654f6b60cd9d5be8b54c6fafe44346dabeb3b76`: `claude-handoff`,
  `implement-spec`, `loop-me`, and `retro`.
- These are upstream beta: that bucket is excluded from the upstream plugin and
  its skills may change or disappear without warning. A disappearance fails the
  refresh rather than silently dropping a skill, because the removal check
  compares the committed inventory against what vendir produced.
- No change to the eighteen previously imported skills or to the source commit.
- Replaced the `/setup-matt-pocock-skills` rename patch with a literal
  substitution rule in `upstream.yml`, applied before the ordered patches. The
  shipped output is unchanged; the rule survives upstream rewording that a
  context diff did not.

## 0.3.1 - 2026-09-01

- Refreshed the reviewed Matt Pocock skill inventory from
  `84fdeffd12f2ee307994d1eb6feb48173b6e0502` to
  `6654f6b60cd9d5be8b54c6fafe44346dabeb3b76` (`v1.2.3-39-g6654f6b`).
- Adopted an untagged upstream snapshot: upstream has published no stable tag
  since `v1.2.3`, so `stable_baseline_tag` stays `v1.2.3` and the package
  version magnitude comes from the inventory delta (no skills added or
  removed, so a patch bump).
- Rebased both downstream patches onto the upstream rewording (repo-wide
  em-dash removal and the "tell the user to run" setup phrasing).
- No inventory change: the same eighteen imported skills, all seventeen
  changed in content.

## 0.3.0 — 2026-08-09

- Refreshed the reviewed Matt Pocock skill inventory from
  `2ab958093e83e0ec752e6c1c5932da465bf23e0c` to
  `84fdeffd12f2ee307994d1eb6feb48173b6e0502` (`v1.2.3-2-g84fdeff`).
- Added the upstream `wizard` skill and adopted upstream updates across the
  existing engineering inventory.
- Rebased the downstream APM setup patch while preserving the package's
  repository-owned compilation and audit contract.

## 0.2.0 — 2026-07-30

- Added an independent APM manifest targeting Claude Code and Codex.
- Added the `engineering-v0.2.0` package tag contract and `^0.2.0` consumer
  dependency.
- Preserved native Claude marketplace installation through
  `engineering@kzarzycki-agent-skills`.
- Removed the floating `mattpocock-skills` marketplace entry in favor of the
  reviewed, pinned inventory shipped by this package.
