#!/bin/sh
# #2266: a migration row's sub-issue is covered by its approved parent's spec (and only then: no sub-issue link, a row
# line naming another issue, a stale parent approval, a risk path each leave it to the owner), and the gatekeeper
# SKILL.md's Specs section states the rule once.
set -e
test "$(grep -c 'Part of #<parent> (row <name>)' gatekeeper/skills/gatekeeper/SKILL.md)" = 1
exec uv run pytest -q -p no:cacheprovider -n0 gatekeeper/tests/test_approvals_row_spec.py tests/test_skill_references.py
