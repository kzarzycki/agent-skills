#!/usr/bin/env bash
# #1607: a detached command that prints `exit 0` and then sleeps is still running; wait-for does not end on its output.
set -euo pipefail
root=$(git rev-parse --show-toplevel)
dir=$(mktemp -d)
trap 'kill "$(cat "$dir/pid" 2>/dev/null)" 2>/dev/null || true; rm -rf "$dir"' EXIT
log=$dir/run.log pidf=$dir/pid
perl -MPOSIX=setsid -e 'fork and exit; setsid; exec @ARGV' sh -c \
  "echo \$\$ > $pidf; echo \"run \$\$\" > $log; sh -c 'echo exit 0; sleep 30' >> $log 2>&1; echo \"loop-exit \$\$ \$?\" >> $log" >/dev/null 2>&1
for _ in $(seq 50); do grep -q '^exit 0$' "$log" 2>/dev/null && break; sleep 0.1; done
code=0
out=$(python3 "$root/engineering/skills/orchestrating-agents/scripts/omnigent_agent.py" wait-for --log "$log" --pid "$pidf" --budget 5) || code=$?
echo "$out"
[ "$code" -eq 6 ] && [[ "$out" == *"still running"* ]]
