#!/usr/bin/env python3
"""Probe the Claude cloud platform's limits that the engineering loop works around.

Run it inside a cloud session of this repo's environment. Each probe makes one real call and
records an `answer` (`allowed`, `refused`, `absent` ...) and the `detail` that proves it. The
answers are compared with `tools/platform-limits.json`; with `--comment` a changed answer is
posted on the tracking issue (#809), so a workaround is dropped once the platform lifts the limit.

    python3 tools/platform_probe.py [--comment] [--update-baseline] [--issue 809]

Exit 0 when every answer matches the baseline, 1 when one changed, 2 when a probe was
`inconclusive` (a network, auth or registry failure, not a platform answer: rerun it). The probes leave nothing
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


REFUSED = (
    "not permitted through this proxy",
    "not available from claude code",
    "returned error: 403",  # git push through the proxy
    "must authenticate via a github app",
)
AUTH_ERRORS = (
    "bad credentials",
    "authentication failed",
    "invalid credentials",
    "could not read username",
)


def classify(rc, out, ok=True):
    """`allowed` when the call worked, `refused` only when the platform's refusal text is in the
    output, else `inconclusive`: a network, auth or registry failure says nothing about policy."""
    if ok and rc == 0:
        return "allowed"
    low = out.lower()
    if any(t in low for t in AUTH_ERRORS):  # a credential failure is not a policy answer
        return "inconclusive"
    return "refused" if any(t in low for t in REFUSED) else "inconclusive"


def api(method, path, *fields):
    f = " ".join(f"-f {k}={v}" for k, v in fields)
    rc, out = sh(f"gh api -X {method} {path} {f} 2>&1")
    return classify(rc, out), out[-200:].replace("\n", " ")


def probe_graphql():
    rc, out = sh("gh api graphql -f query='{viewer{login}}' 2>&1")
    return classify(rc, out), out[:200]


def probe_status_write():
    return api(
        "POST",
        f"repos/{repo()}/statuses/{head()}",
        ("state", "pending"),
        ("context", "platform-probe"),
    )


def probe_checkrun_write():
    # ponytail: a check run cannot be deleted, so once this answer turns `allowed` each run adds
    # one neutral check run on its HEAD. That turn is itself the change the probe reports; update
    # the baseline then and drop this probe.
    return api(
        "POST",
        f"repos/{repo()}/check-runs",
        ("name", "platform-probe"),
        ("head_sha", head()),
        ("status", "completed"),
        ("conclusion", "neutral"),
    )


def probe_refs():
    br, ref = "claude/probe-platform", "refs/probe/platform"
    rc, out = sh(f"git push --force origin HEAD:refs/heads/{br} 2>&1")
    res = {"branch_push": (classify(rc, out), "pushed" if rc == 0 else out[-160:])}
    rc_ref, out_ref = sh(f"git push --force origin HEAD:{ref} 2>&1")
    detail = out_ref[-160:]
    if rc_ref == 0:
        rc_rm, out_rm = sh(f"git push origin :{ref} 2>&1")
        detail = (
            "pushed"
            if rc_rm == 0
            else f"pushed, and the cleanup failed so {ref} remains: {out_rm[-120:]}"
        )
    answer = classify(rc_ref, out_ref)
    if answer == "allowed" and "remains" in detail:
        answer = "allowed-ref-left-behind"  # differs from any baseline, so it is reported
    res["non_branch_ref"] = (answer, detail)
    if rc != 0:
        res["ref_delete"] = ("inconclusive", "no probe branch to delete: the branch push failed")
        return res
    rc_del, out_del = sh(f"git push origin --delete {br} 2>&1")
    if rc_del != 0:
        rc_rest, out_rest = sh(f"gh api -X DELETE repos/{repo()}/git/refs/heads/{br} 2>&1")
        res["ref_delete"] = (
            classify(rc_rest, out_rest),
            f"git: {out_del[-80:]}; REST: {out_rest[-80:]}",
        )
    else:
        res["ref_delete"] = ("allowed", "git push --delete worked")
    return res


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
    tried = []
    for tool in ("docker", "podman"):
        if not shutil.which(tool):
            continue
        for _ in range(3):  # a registry pull can fail on its own
            _rc, out = sh(f"{tool} run --rm hello-world 2>&1 | head -5", 120)
            if "Hello" in out:
                return "allowed", f"{tool} run hello-world works"
            time.sleep(5)
        tried.append(f"{tool}: {out[-120:]}")
    if not tried:
        return "absent", "no docker or podman on PATH"
    # ponytail: a failed run is `refused` only on an "operation not permitted" error; a pull or daemon failure
    # stays `inconclusive`, since it says nothing about whether the VM may run containers.
    refused = all("operation not permitted" in t.lower() for t in tried)
    return ("refused" if refused else "inconclusive"), "; ".join(tried)


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
    inconclusive = [k for k, v in res.items() if v["answer"] == "inconclusive"]
    changed = {
        k: (base.get(k), v["answer"])
        for k, v in res.items()
        if v["answer"] != "inconclusive" and base.get(k) != v["answer"]
    }
    print(json.dumps({"results": res, "changed": changed, "inconclusive": inconclusive}, indent=2))
    if a.update_baseline:
        # an inconclusive answer keeps the last known one
        new = {
            k: v["answer"]
            for k, v in res.items()
            if v["answer"] != "inconclusive" and not v["answer"].startswith("allowed-")
        }
        BASELINE.write_text(json.dumps({**base, **new}, indent=2) + "\n")
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
    return 1 if changed else 2 if inconclusive else 0


if __name__ == "__main__":
    sys.exit(main())
