#!/usr/bin/env bash
# #1604 Acceptance: a role or brief file the child's clone lacks is inlined, one over the cap exits 2 with one stderr line, and the cap is inclusive at 8,000.
set -euo pipefail
agent=$PWD/engineering/skills/orchestrating-agents/scripts/omnigent_agent.py
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cd "$work"
git init -q repo && git init -q other
git -C other -c user.name=t -c user.email=t@t commit -q --allow-empty -m init
echo "FOREIGN" > other/f.md
git -C other add f.md && git -C other -c user.name=t -c user.email=t@t commit -qm f
cd repo
git -c user.name=t -c user.email=t@t commit -q --allow-empty -m init
echo "LOOSE" > loose.md
echo "TASK[1]" > 'task[1].md'
has() { grep -q -- "$2" <<<"$1" || { echo "missing: $2" >&2; exit 1; }; }
for role in "$work/other/f.md" loose.md 'task[1].md'; do
  out=$(python3 "$agent" brief "do it" r.md --cloud --role "$role" 2>/dev/null)
  has "$out" "<role-file>"
done
out=$(python3 "$agent" brief loose.md r.md --cloud 2>/dev/null)
has "$out" LOOSE
pad() { head -c "$1" < /dev/zero | tr '\0' x; }
base=$(python3 "$agent" brief "$(pad 4400)" r.md --cloud 2>&1 >/dev/null | sed -n 's/^brief: \([0-9]*\) characters$/\1/p'); base=$((base - 4400))
python3 "$agent" brief "$(pad $((8000 - base)))" r.md --cloud >/dev/null 2>&1
rc=0
python3 "$agent" brief "$(pad $((8001 - base)))" r.md --cloud >out.txt 2>err.txt || rc=$?
[ "$rc" = 2 ] && [ ! -s out.txt ] && [ "$(wc -l < err.txt)" = 1 ] || { echo "over cap: rc=$rc $(cat err.txt)" >&2; exit 1; }
echo ok
