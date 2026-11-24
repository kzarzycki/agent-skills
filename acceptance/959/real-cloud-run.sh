#!/bin/sh
# #959: a claude-cloud-run whose command outlasts a check-in interval (420 s > CLOUD_CHECK_IN_SECONDS) exits with
# the command's own code, where main exits 125 on the child's idle turn. The log's first line is the head it ran
# on, bare, as loop.py brief checks it; run it on a pushed head. Usage: real-cloud-run.sh [log path]
set -u
root=$(git rev-parse --show-toplevel)
log=${1:-$root/tmp/loop/959-real-cloud-run.log}
mkdir -p "$(dirname "$log")"
{
  git -C "$root" rev-parse HEAD
  python3 "$root/omnigent/skills/omnigent-agents/scripts/omnigent_agent.py" claude-cloud-run --checkout "$root" \
    -- "python3 -c \"import time; time.sleep(420); print('ok')\"" 2>&1
  echo "exit: $?"
} | tee "$log"
grep -qx "exit: 0" "$log"
