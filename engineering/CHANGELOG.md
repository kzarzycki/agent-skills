# Changelog

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
