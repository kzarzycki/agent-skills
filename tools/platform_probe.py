#!/usr/bin/env python3
"""Probe the Claude cloud platform's limits that the engineering loop works around.

Run it inside a cloud session of this repo's environment. Each probe makes one real call and
records an `answer` (`allowed`, `refused`, `absent` ...) and the `detail` that proves it. The
answers are compared with `tools/platform-limits.json`; with `--comment` a changed answer is
posted on the tracking issue (#809), so a workaround is dropped once the platform lifts the limit.

    python3 tools/platform_probe.py [--comment] [--update-baseline] [--issue 809]

Exit 0 when every answer matches the baseline, 1 when one changed. The probes leave nothing
behind: a pending status, the one branch `claude/probe-platform` (its deletion is refused in a cloud session, so it stays and
is force-pushed again each run: delete it from a host when you like), and a ref that is refused or removed.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE = Path(__file__).with_name("platform-limits.json")


def sh(cmd, timeout=60):
    try:
        p = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout, cwd=ROOT, check=False
        )
        return p.returncode, (p.stdout + p.stderr).strip()
    except subprocess.TimeoutExpired:
        return 124, f"timeout after {timeout}s"


def repo():
    # Read it from the remote: `gh repo view` is GraphQL, which the cloud refuses.
    url = sh("git remote get-url origin")[1].splitlines()[-1]
    return url.removesuffix(".git").split("github.com", 1)[-1].lstrip(":/")


def head():
    return sh("git rev-parse HEAD")[1]


def api(method, path, *fields):
    f = " ".join(f"-f {k}={v}" for k, v in fields)
    _rc, out = sh(f"gh api -X {method} {path} {f} -i 2>&1 | head -20")
    status = next(
        (l for l in out.splitlines() if l.startswith("HTTP/")),
        out.splitlines()[0] if out else "no output",
    )
    return status.strip(), out


def probe_graphql():
    rc, out = sh("gh api graphql -f query='{viewer{login}}'")
    return ("allowed" if rc == 0 else "refused"), out[:200]


def probe_status_write():
    st, out = api(
        "POST",
        f"repos/{repo()}/statuses/{head()}",
        ("state", "pending"),
        ("context", "platform-probe"),
    )
    return ("allowed" if " 201" in st else "refused"), st + " " + out[-160:].replace("\n", " ")


def probe_checkrun_write():
    st, out = api(
        "POST",
        f"repos/{repo()}/check-runs",
        ("name", "platform-probe"),
        ("head_sha", head()),
        ("status", "completed"),
        ("conclusion", "neutral"),
    )
    return ("allowed" if " 201" in st else "refused"), st + " " + out[-160:].replace("\n", " ")


def probe_refs():
    br, ref = "claude/probe-platform", "refs/probe/platform"
    rc, out = sh(f"git push --force origin HEAD:refs/heads/{br}")
    out_branch = "pushed" if rc == 0 else out[-160:]
    rc_ref, out_ref = sh(f"git push origin HEAD:{ref}")
    if rc_ref == 0:
        sh(f"git push origin :{ref}")
    rc_del, out_del = sh(f"git push origin --delete {br}") if rc == 0 else (1, "branch not pushed")
    if rc_del != 0 and rc == 0:
        sh(f"gh api -X DELETE repos/{repo()}/git/refs/heads/{br}")
    return {
        "branch_push": ("allowed" if rc == 0 else "refused", out_branch),
        "non_branch_ref": ("allowed" if rc_ref == 0 else "refused", out_ref[-160:]),
        "ref_delete": ("allowed" if rc_del == 0 else "refused", out_del[-160:]),
    }


def start_dockerd():
    """The image ships docker without a running daemon: start one, as the setup script does."""
    if shutil.which("dockerd") and sh("docker info")[0] != 0:
        subprocess.Popen("exec dockerd >/tmp/dockerd.log 2>&1", shell=True, start_new_session=True)
        for _ in range(30):
            if sh("docker info")[0] == 0:
                break
            time.sleep(1)


def probe_container():
    start_dockerd()
    for tool in ("docker", "podman"):
        if shutil.which(tool):
            for _ in range(
                3
            ):  # a registry pull can fail on its own; only three failures in a row count
                _rc, out = sh(f"{tool} run --rm hello-world 2>&1 | head -5", 120)
                if "Hello" in out:
                    break
                time.sleep(5)
            if "Hello" in out:
                return "allowed", f"{tool} run hello-world works"
            return "refused", f"{tool} present, run failed: {out[-200:]}"
    return "absent", "no docker or podman on PATH"


def probe_nested_virt():
    kvm = os.path.exists("/dev/kvm")
    vmx = sh("grep -cE 'vmx|svm' /proc/cpuinfo")[1]
    return (
        "allowed" if kvm else "absent"
    ), f"/dev/kvm {'present' if kvm else 'missing'}, vmx/svm cpu flags: {vmx}"


def run():
    res = {
        "graphql": probe_graphql(),
        "status_write": probe_status_write(),
        "check_run_write": probe_checkrun_write(),
    }
    res.update(probe_refs())
    res["container_runtime"] = probe_container()
    res["nested_virtualisation"] = probe_nested_virt()
    return {k: {"answer": a, "detail": d} for k, (a, d) in res.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--comment", action="store_true", help="comment a changed answer on the issue")
    ap.add_argument("--update-baseline", action="store_true")
    ap.add_argument("--issue", default="809")
    a = ap.parse_args()
    res = run()
    base = json.loads(BASELINE.read_text()) if BASELINE.exists() else {}
    changed = {k: (base.get(k), v["answer"]) for k, v in res.items() if base.get(k) != v["answer"]}
    print(json.dumps({"results": res, "changed": changed}, indent=2))
    if a.update_baseline:
        BASELINE.write_text(json.dumps({k: v["answer"] for k, v in res.items()}, indent=2) + "\n")
    if changed and a.comment:
        lines = [
            f"- `{k}`: {o} → {n} (`{res[k]['detail'][:120]}`)" for k, (o, n) in changed.items()
        ]
        body = "> 🤖 AI\n\nWeekly platform-limit probe: a changed answer.\n\n" + "\n".join(lines)
        p = subprocess.run(
            ["gh", "issue", "comment", a.issue, "--body", body],
            capture_output=True,
            text=True,
            cwd=ROOT,
            check=False,
        )
        print(p.stdout + p.stderr)
    return 1 if changed else 0


if __name__ == "__main__":
    sys.exit(main())
