#!/usr/bin/env bash
# acceptance: skip https://github.com/kzarzycki/agent-skills/issues/2817
# #1601 Acceptance line 1: lead.md has one Cloud lead section of seven points, each holding its own load-bearing terms, and its opening paragraph points to it.
# Usage: 01-cloud-lead-section.sh [lead.md]   (default: the real file)
set -euo pipefail
f=${1:-loop/skills/engineering-loop/lead.md}
fail=0
miss() { echo "$1" >&2; fail=1; }

n=$(grep -c -x -F '## Cloud lead' "$f" || true)
[ "$n" = 1 ] || miss "'## Cloud lead' must appear exactly once (found $n)"

head -n 20 "$f" | grep -q -F 'reads *Cloud lead* below first' || miss "opening paragraph: pointer to *Cloud lead* is missing"

# Each point on one line, newlines turned into spaces: a point starts at "<k>. **" in column 0 and
# runs to the next such line or the section's end (the next "**Waiting.**" or heading).
mapfile -t points < <(awk '
  /^## Cloud lead$/ { on = 1; next }
  !on { next }
  /^\*\*Waiting\.\*\*/ || /^## / { exit }
  /^[0-9]+\. \*\*/ { if (cur != "") print cur; cur = $0; next }
  cur != "" && NF { cur = cur " " $0 }
  END { if (cur != "") print cur }
' "$f" | sed 's/  */ /g')

[ "${#points[@]}" = 7 ] || miss "Cloud lead must hold exactly 7 numbered points (found ${#points[@]})"

check() { # <point number> <term>...
  local k=$1; shift
  local p=${points[$((k - 1))]:-}
  case $p in "$k. **"*) ;; *) miss "point $k is missing"; return ;; esac
  for t in "$@"; do
    printf '%s\n' "$p" | grep -q -F -- "$t" || miss "point $k: missing '$t'"
  done
}

check 1 'claude-cloud' '/root/.ccr/README.md'
check 2 'placement: same_host' 'permission_mode: auto' 'sys_session_update(archived: true)' '8,000'
check 3 'sys_session_message' 'cloud_verifier.py verify' '--harness claude'
check 4 'Waits:' 'wait-for --pr' 'supervisor' 'finished' 'sub-agent'
check 5 '## Lead state' 'created_by_session_id' 'Never write a session id' 'git fetch' "turn's start"
check 6 '#1597' 'USER NEEDED'
check 7 'sys_session_message' 'sys_session_send' 'parent'

# Point 3 sends the worker the verifier brief with sys_session_message; sys_session_send may appear
# only after a "reaches only" clause, as the reason it is not used.
p3=${points[2]:-}
before=${p3%%reaches only*}
if printf '%s\n' "$before" | grep -q -F 'sys_session_send'; then
  miss "point 3: sys_session_send named as the tool to send the worker (a sibling is not a child)"
fi
exit "$fail"
