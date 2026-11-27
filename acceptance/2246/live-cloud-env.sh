#!/bin/sh
# acceptance: live
# #2246 live proof, run by hand on a host with an Omnigent server and a claude login holding <base> and
# <base>-code-mode: one `start claude-cloud --cloud-env <base>-code-mode` from a launch dir of its own, in a project
# whose loop.md names `env <base>`, runs in the variant; the next plain start from the project's checkout gets <base>.
# Usage: acceptance/2246/live-cloud-env.sh <base> [<log>]   (from a checkout of the project, on a pushed branch)
set -eu
base=$1
log=${2:-tmp/loop/2246-live.log}
script=omnigent/skills/omnigent-agents/scripts/omnigent_agent.py
here=$(git rev-parse --show-toplevel)
branch=$(git rev-parse --abbrev-ref HEAD)
remote=$(git remote get-url origin)
mkdir -p "$(dirname "$log")"
git rev-parse HEAD > "$log"
grep -q "^Cloud worker:.*env $base" docs/agents/loop.md || { echo "loop.md names no env $base" >> "$log"; exit 2; }
id=$(python3 - "$script" "$base-code-mode" <<'PY'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("oa", sys.argv[1]); m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m); print(m.cloud_env_id(sys.argv[2]))
PY
)
launch="$here/.worktrees/cloud-env-$base-code-mode"
[ -d "$launch" ] || python3 "$script" launch-dir --clone "$remote" "$branch" "$id" "$launch" >> "$log" 2>&1
pin() { python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["remote"]["defaultEnvironmentId"])' "$1/.claude/settings.local.json"; }
ask="Report the names and values of the environment variables whose names start with CLAUDE_CODE_REMOTE or CCR, and the name of this cloud environment if anything in the VM shows it. Nothing else."
echo "== --cloud-env $base-code-mode from $launch (pin $(pin "$launch"))" >> "$log"
code=0
python3 "$script" run claude-cloud "cloud-env-2246-variant" "$ask" "$launch/tmp/loop/2246-variant.md" \
  --workspace "$launch" --cloud-env "$base-code-mode" --no-keep >> "$log" 2>&1 || code=$?
echo "variant exit $code; launch dir pin after: $(pin "$launch") (want $id)" >> "$log"
echo "== plain start from $here" >> "$log"
code=0
python3 "$script" run claude-cloud "cloud-env-2246-plain" "$ask" "$here/tmp/loop/2246-plain.md" \
  --workspace "$here" --no-keep >> "$log" 2>&1 || code=$?
echo "plain exit $code; checkout pin after: $(pin "$here")" >> "$log"
echo "Check each session's environment on claude.ai/code (the [cloud] link in each transcript): the first runs in $base-code-mode, the second in $base." >> "$log"
cat "$log"
