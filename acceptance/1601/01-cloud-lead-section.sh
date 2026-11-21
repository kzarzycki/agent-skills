#!/usr/bin/env bash
# #1601 Acceptance line 1: lead.md has one Cloud lead section with each point's load-bearing terms, and its opening paragraph points to it.
set -euo pipefail
f=engineering/skills/engineering-loop/lead.md
fail=0
miss() { echo "missing: $1" >&2; fail=1; }

n=$(grep -c -x -F '## Cloud lead' "$f" || true)
[ "$n" = 1 ] || miss "'## Cloud lead' exactly once (found $n)"

body=$(awk '/^## Cloud lead$/{on=1;next} on&&/^\*\*Waiting\.\*\*/{exit} on' "$f")
for t in 'placement: same_host' 'permission_mode: auto' 'sys_session_update(archived: true)' \
  'sys_session_message' '--harness claude' 'Waits:' 'wait-for --pr' '## Lead state' \
  'created_by_session_id' '#1597' 'USER NEEDED'; do
  printf '%s\n' "$body" | grep -q -F -- "$t" || miss "$t"
done

head -n 20 "$f" | grep -q -F 'reads *Cloud lead* below first' || miss "opening pointer to *Cloud lead*"

if printf '%s\n' "$body" | grep -q -F 'worker the `approvals.py brief` text with `sys_session_send`'; then
  echo "present but forbidden: sys_session_send to the worker" >&2; fail=1
fi
exit "$fail"
