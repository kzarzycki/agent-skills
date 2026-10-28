# Engineering maintenance values

This repository keeps `engineering/` current by running the `vendoring` skill's
[ROUTINE.md](../vendoring/skills/vendoring/ROUTINE.md) with `<pack>` = `engineering`,
upstream `mattpocock/skills`, default branch `main`, and these values for its slots. The
tuning contract is in [CLAUDE.md](CLAUDE.md).

- **Setup:** `git fetch origin --tags`, then `uv sync --frozen`. The tools in `mise.toml`
  must be on `PATH` at their pinned versions; run `mise install` only for those missing
  (a host setup script may provide them). The credentials must be able to push branches
  and tags to `kzarzycki/agent-skills`, merge its PRs and open issues. A tag pushed with
  GitHub Actions' own `GITHUB_TOKEN` starts no workflow, so push with a user or App
  credential.
- **Blocked marker:** an open issue labelled `engineering-routine:blocked`, creating the
  label if it's missing. Closing the issue clears it.
- **Earlier work**, in order:
  - **Unreleased version on main:** if `engineering/apm.yml` on `origin/main` is newer
    than the newest `engineering-v*` tag, tag the main commit that set it as the release
    value below says, and stop. Find it with
    `git log -1 --first-parent --format=%H -G'^version:' origin/main -- engineering/apm.yml`.
  - **Tag check:** the newest tag's `Engineering tag check` run
    (`gh run list --workflow engineering-tag-check.yml`) still running means stop until
    the next run; failed, or missing for a tag older than an hour, means blocked.
  - **Open consumer sync:** if the `automation/engineering-consumer-sync` PR (the tag
    check's bump of this repository's own APM ref) is open, bring it up to date with
    main, wait for its checks, mark it ready and squash-merge it. Its checklist commands
    already ran in its CI.
- **Intake:** `mise run vendor-engineering`.
- **Branch:** `engineering-upstream/<new upstream short sha>`.
- **Gates:** `mise run vendor-engineering-check`, `mise run test`,
  `mise run test-engineering-package` and `git diff --check origin/main...HEAD`.
- **Landing:** the required `qualify` check passes; then
  `gh pr merge --squash --delete-branch`.
- **Release:**
  - Give the version an `engineering/CHANGELOG.md` entry, or extend its entry if one
    exists, and move the `engineering/changelog.d/` entries under it
    ([its README](changelog.d/README.md)).
  - Tag: `git tag -a engineering-vX.Y.Z -m engineering-vX.Y.Z <merge sha> && git push origin engineering-vX.Y.Z`.
    The tag check re-qualifies the release and opens the consumer-sync PR, which the
    next run's earlier work merges.
  - Version files: `engineering/apm.yml`, `engineering/.claude-plugin/plugin.json` and
    `engineering/tests/consumer/apm.yml`.
