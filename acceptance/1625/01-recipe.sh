#!/bin/sh
# #1625 Before merge: SKILL.md's Cloud worker section holds the recipe bullet naming launch-dir, --pr, --workspace,
# --host and host.md; lead.md's step 4 and verifier step point to it; omnigent.md points back; none names a
# hostname or an absolute path.
set -e
cd "$(git rev-parse --show-toplevel)/engineering/skills"
python3 - <<'PY'
import re, sys
skill = open("engineering-loop/SKILL.md").read()
lead = open("engineering-loop/lead.md").read()
back = open("orchestrating-agents/backends/omnigent.md").read()
sec = skill[skill.index("\n## Cloud worker\n"):]
sec = sec[1:]
nxt = re.search(r"\n## ", sec)
sec = sec[: nxt.start()] if nxt else sec
m = re.search(r"^- \*\*Starting a PR's cloud worker\.\*\*.*?(?=^- \*\*|\Z)", sec, re.S | re.M)
fails = []
if not m:
    fails.append("SKILL.md Cloud worker has no 'Starting a PR's cloud worker' bullet")
else:
    for t in ("launch-dir", "--pr", "--workspace", "--host", "host.md"):
        if t not in m.group(0):
            fails.append(f"recipe bullet lacks {t}")
    for pat in (r"(?<![\w.])/(?:home|Users|tmp|opt|var)/", r"\b[\w-]+\.(?:local|lan|internal|com)\b"):
        if re.search(pat, m.group(0)):
            fails.append(f"recipe bullet matches {pat}")
ref = "Starting a PR's cloud worker"
s4 = lead[lead.index("\n4. **Build.**"):lead.index("\n5. **After each merge")]
s7 = lead[lead.index("\n7. **Verify**"):lead.index("\n8. **Land**")]
if ref not in s4: fails.append("lead.md step 4 has no pointer")
if ref not in s7: fails.append("lead.md verifier step has no pointer")
if ref not in back: fails.append("omnigent.md has no pointer back")
print("\n".join(fails) or "ok")
sys.exit(1 if fails else 0)
PY
