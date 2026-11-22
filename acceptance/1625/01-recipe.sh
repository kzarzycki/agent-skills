#!/bin/sh
# #1625 Before merge (with its addendum): SKILL.md's Cloud worker section holds the recipe bullet, with each command in
# its full form (launch-dir, run --pr ... --workspace, start ... --top-level --host <host> --workspace ... --pr, wait
# <session> <report> --pr), the host sources (host.md, Placement:), the verifier routes (cloud_verifier.py verify and
# thread, the start codex refusal) and the brief; lead.md's step 4 and verifier step point to it; omnigent.md points
# back; the bullet fixes no hostname and no absolute path.
set -e
cd "$(git rev-parse --show-toplevel)/engineering/skills"
python3 - <<'PY'
import re, sys
skill = open("engineering-loop/SKILL.md").read()
lead = open("engineering-loop/lead.md").read()
back = open("orchestrating-agents/backends/omnigent.md").read()
sec = skill[skill.index("\n## Cloud worker\n") + 1:]
nxt = re.search(r"\n## ", sec)
sec = sec[: nxt.start()] if nxt else sec
m = re.search(r"^- \*\*Starting a PR's cloud worker\.\*\*.*?(?=^- \*\*|\Z)", sec, re.S | re.M)
fails = []
if not m:
    fails.append("SKILL.md Cloud worker has no 'Starting a PR's cloud worker' bullet")
else:
    b = m.group(0)
    need = {
        "launch-dir": r"launch-dir <remote> <branch> <path>",
        "worktrees convention": r"\.worktrees/",
        "environment pin": r"Cloud worker:[^`]*env <name>",
        "run form": r"run --pr <n> <agent> \"<title>\" <brief> <report> --workspace <launch dir>",
        "start form": r"start <agent> \"<title>\" <brief> <report> --top-level --host <host> --workspace <launch dir on that host> --pr <n>",
        "wait form": r"wait <session> <report> --pr <n>",
        "host note": r"~/\.agents/host\.md",
        "placement": r"`Placement:`",
        "verify route": r"cloud_verifier\.py verify --pr <n> --brief <file>",
        "thread route": r"cloud_verifier\.py thread --pr <n> --brief <file>",
        "worker-VM pointer": r"Verifier in the worker's VM",
        "thread pointer": r"Verifier on a Codex Cloud thread",
        "brief": r"brief `approvals\.py brief <pr>` writes",
        "codex refusal": r"start codex … --pr` is refused by design, since Codex has no cloud bridge",
    }
    for name, pat in need.items():
        if not re.search(pat, b):
            fails.append(f"recipe bullet lacks {name}")
    for flag in re.findall(r"--host (\S+)", b):
        if not flag.startswith("<"):
            fails.append(f"--host names {flag}, not a placeholder")
    for flag in re.findall(r"--workspace (\S+)", b):
        if not flag.startswith("<"):
            fails.append(f"--workspace names {flag}, not a placeholder")
    for word in re.findall(r"(?<![^\s`\"(])/\S*", b):
        fails.append(f"recipe bullet holds an absolute path: {word}")
    for host in re.findall(r"\b[\w-]+(?:\.[\w-]+)+\b", b):
        if host.rsplit(".", 1)[1] not in ("py", "md", "sh", "yml", "json"):
            fails.append(f"recipe bullet holds a hostname: {host}")
ref = "Starting a PR's cloud worker"
s4 = lead[lead.index("\n4. **Build.**"):lead.index("\n5. **After each merge")]
s7 = lead[lead.index("\n7. **Verify**"):lead.index("\n8. **Land**")]
if ref not in s4: fails.append("lead.md step 4 has no pointer")
if ref not in s7: fails.append("lead.md verifier step has no pointer")
if ref not in back: fails.append("omnigent.md has no pointer back")
print("\n".join(fails) or "ok")
sys.exit(1 if fails else 0)
PY
