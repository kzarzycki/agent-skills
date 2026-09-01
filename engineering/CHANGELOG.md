# Changelog

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
