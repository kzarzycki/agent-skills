#!/usr/bin/env bash
# #1604 Acceptance: `brief --cloud` on the worker role file prints under 8,000 characters and names the role file by path.
set -euo pipefail
role=engineering/skills/engineering-loop/worker.md
out=$(python3 engineering/skills/orchestrating-agents/scripts/omnigent_agent.py brief "do the task" tmp/x.md --role "$role" --cloud 2>/dev/null)
[ "${#out}" -lt 8000 ] || { echo "message is ${#out} characters, not under 8000" >&2; exit 1; }
case $out in *"Your role file is \`$role\` in your checkout"*) ;; *) echo "role file not named by path" >&2; exit 1 ;; esac
case $out in *"<role-file>"*) echo "role file inlined" >&2; exit 1 ;; esac
echo "ok: ${#out} characters"
