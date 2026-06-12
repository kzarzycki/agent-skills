#!/usr/bin/env python3
"""Spike 1: drive a real `claude` REPL in tmux from inside a Claude session.

Proves the eval-harness core: launch SUT pane (TMUX unset), detect an
AskUserQuestion gate from capture-pane, answer it with send-keys, observe run
residue (artifact file + session JSONL tokens), measure step timings.

Run: python3 spike.py [--keep]  -> prints JSON report, exits 0 on success.
Failure classes: harness-fail (driver breakdown) vs sut-fail (Claude misbehaved).
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time

SESSION = "eval-spike-1"
SCRATCH = "/tmp/eval-spike-1-scratch"
PANE_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pane.log")
PROMPT = (
    "Use the AskUserQuestion tool to ask me exactly one question: which color do I prefer, "
    "options Red and Blue. After I answer, write only the chosen color to answer.txt in the "
    "current directory, then end your turn. Do nothing else."
)
T0 = time.time()
TIMINGS = {}
PANES = []


def sh(cmd, **kw):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, **kw)


def pane():
    out = sh(f"tmux capture-pane -p -t {SESSION}").stdout
    PANES.append(f"--- {time.time()-T0:.1f}s ---\n{out}")
    return out


def send(keys, literal=False):
    flag = "-l " if literal else ""
    sh(f"tmux send-keys -t {SESSION} {flag}{keys}")


def wait_for(predicate, timeout, step_name, poll=1.0):
    start = time.time()
    while time.time() - start < timeout:
        content = pane()
        hit = predicate(content)
        if hit:
            TIMINGS[step_name] = round(time.time() - start, 1)
            return content, hit
        time.sleep(poll)
    TIMINGS[step_name] = f"TIMEOUT>{timeout}s"
    return None, None


def fail(cls, step, detail):
    report(status=cls, failed_step=step, detail=detail)
    sys.exit(1)


def report(**extra):
    out = {"spike": "01-tmux-driver", "timings_s": TIMINGS, "total_s": round(time.time() - T0, 1), **extra}
    with open(PANE_LOG, "w") as f:
        f.write("\n".join(PANES[-60:]))
    print(json.dumps(out, indent=2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true", help="keep tmux session and scratch dir")
    args = ap.parse_args()

    # Clean slate
    sh(f"tmux kill-session -t {SESSION} 2>/dev/null")
    shutil.rmtree(SCRATCH, ignore_errors=True)
    os.makedirs(SCRATCH, exist_ok=True)

    # 1. Launch SUT REPL: TMUX unset -> in-situ branch; pre-trust the scratch dir if supported.
    sh(f"tmux new-session -d -s {SESSION} -x 200 -y 50 -c {SCRATCH} "
       f"'env -u TMUX claude --permission-mode acceptEdits'")

    # 2. Wait for REPL ready (input box) -- handle trust dialog if it appears.
    def ready(c):
        if re.search(r"trust the files|Do you trust", c, re.I):
            return "trust-dialog"
        if re.search(r"(\? for shortcuts|>\s*$|Try \")", c, re.M):
            return "ready"
        return None

    content, hit = wait_for(ready, 60, "repl_start")
    if not hit:
        fail("harness-fail", "repl_start", "REPL never showed input box or trust dialog")
    if hit == "trust-dialog":
        send("Enter")
        content, hit = wait_for(lambda c: re.search(r"\? for shortcuts|Try \"", c), 30, "post_trust")
        if not hit:
            fail("harness-fail", "post_trust", "input box never appeared after trust dialog")

    # 3. Submit the prompt.
    send(f'"{PROMPT}"', literal=True)
    time.sleep(0.5)
    send("Enter")

    # 4. Detect the AskUserQuestion gate (option list rendering).
    def gate(c):
        if re.search(r"Red", c) and re.search(r"Blue", c) and re.search(r"[❯>]\s*1?\.?\s*Red|1\.\s*Red", c):
            return "gate"
        return None

    content, hit = wait_for(gate, 120, "gate_detect", poll=1.5)
    if not hit:
        fail("harness-fail", "gate_detect", "AskUserQuestion options never rendered in pane")
    gate_render = content

    # 5. Answer: select option 2 (Blue) -- arrow down + enter.
    send("Down")
    time.sleep(0.3)
    send("Enter")

    # 6. Observe residue: answer.txt appears with Blue.
    def artifact(_c):
        p = os.path.join(SCRATCH, "answer.txt")
        if os.path.exists(p):
            return open(p).read().strip()
        return None

    _, answer = wait_for(artifact, 120, "artifact_write", poll=1.0)
    if answer is None:
        fail("sut-fail", "artifact_write", "answer.txt never appeared after gate answer")

    # 7. Mine the session JSONL: newest transcript for the scratch project dir.
    enc = SCRATCH.replace("/", "-")
    pattern = os.path.expanduser(f"~/.claude/projects/{enc}/*.jsonl")
    files = sorted(glob.glob(pattern), key=os.path.getmtime)
    usage = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
    events = 0
    if files:
        for line in open(files[-1]):
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            u = (rec.get("message") or {}).get("usage")
            if u:
                events += 1
                for k in usage:
                    usage[k] += u.get(k, 0) or 0
    TIMINGS["jsonl_found"] = bool(files)

    if not args.keep:
        sh(f"tmux kill-session -t {SESSION}")

    report(
        status="success",
        answer_written=answer,
        answer_correct=(answer.lower() == "blue"),
        transcript=files[-1] if files else None,
        usage_events=events,
        usage=usage,
        gate_render_sample=[l for l in gate_render.splitlines() if l.strip()][-12:],
    )


if __name__ == "__main__":
    main()
