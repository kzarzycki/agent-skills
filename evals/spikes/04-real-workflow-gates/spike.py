#!/usr/bin/env python3
"""Spike 4: drive a real /workflow run through consecutive gates, then kill.

Path: meta-gate ("run the full workflow") -> research-bucket gate (multiSelect)
[-> interview-mode gate if asked] -> detect research workflow kickoff -> kill.
Proves: consecutive unscripted+scripted real gates, working-state detection,
partial-run cost mining. Cost guard: SUT killed the moment research starts.
"""
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time

SESSION = "eval-spike-4"
SCRATCH = "/tmp/eval-spike-4-scratch"
CONFIG = "/tmp/eval-spike-3-config"   # reuse spike-3's pinned isolated config
PANE_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pane.log")
PROMPT = ("/workflow build a tiny tic-tac-toe CLI game in python. "
          "Run the full workflow pipeline; do not shortcut it.")
T0 = time.time()
TIMINGS = {}
PANES = []
GATES = []


def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)


def pane():
    out = sh(f"tmux capture-pane -p -t {SESSION}").stdout
    PANES.append(f"--- {time.time()-T0:.1f}s ---\n{out}")
    return out


def send(keys, literal=False):
    sh(f"tmux send-keys -t {SESSION} {'-l ' if literal else ''}{keys}")


def wait_for(pred, timeout, step, poll=2.0):
    s = time.time()
    while time.time() - s < timeout:
        c = pane()
        h = pred(c)
        if h:
            TIMINGS[step] = round(time.time() - s, 1)
            return c, h
        time.sleep(poll)
    TIMINGS[step] = f"TIMEOUT>{timeout}s"
    return None, None


def question_open(c):
    has_options = re.search(r"(?m)^\s*[❯ ]\s*\d+\.", c)
    footer = re.search(r"Enter to (select|confirm)|Do you want to proceed|Esc to cancel", c)
    return bool(has_options and footer)


def is_permission_prompt(c):
    return bool(re.search(r"Do you want to proceed|Tab to amend", c))


def options_of(c):
    return re.findall(r"(?m)^\s*[❯>]?\s*(\d+)\.\s*(\[.\]\s*)?(.+)$", c)


def mine_usage():
    enc = SCRATCH.replace("/", "-")
    files = sorted(glob.glob(os.path.expanduser(f"~/.claude/projects/{enc}/*.jsonl")), key=os.path.getmtime)
    usage = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
    if files:
        for line in open(files[-1]):
            try:
                u = (json.loads(line).get("message") or {}).get("usage")
            except json.JSONDecodeError:
                continue
            if u:
                for k in usage:
                    usage[k] += u.get(k, 0) or 0
    return usage


def finish(status, **extra):
    with open(PANE_LOG, "w") as f:
        f.write("\n".join(PANES[-100:]))
    sh(f"tmux kill-session -t {SESSION} 2>/dev/null")
    print(json.dumps({"spike": "04-real-workflow-gates", "status": status, "timings_s": TIMINGS,
                      "gates_seen": GATES, "usage": mine_usage(),
                      "total_s": round(time.time() - T0, 1), **extra}, indent=2))
    sys.exit(0 if status == "success" else 1)


def main():
    sh(f"tmux kill-session -t {SESSION} 2>/dev/null")
    shutil.rmtree(SCRATCH, ignore_errors=True)
    os.makedirs(SCRATCH, exist_ok=True)
    if not os.path.exists(os.path.join(CONFIG, ".credentials.json")):
        finish("harness-fail", detail="spike-3 isolated config missing; run spike 3 first")

    # Scoped pre-authorization: the SUT reads its plugin's contracts from the repo path.
    # A narrow Read allowlist in the isolated config avoids those permission prompts
    # without disabling any gates; the driver still answers any prompt that slips through.
    json.dump({"permissions": {"allow": ["Read(/home/agent/dev/agent-skills/**)"]}},
              open(os.path.join(CONFIG, "settings.json"), "w"))

    sh(f"tmux new-session -d -s {SESSION} -x 200 -y 50 -c {SCRATCH} "
       f"\"env -u TMUX CLAUDE_CONFIG_DIR={CONFIG} claude --permission-mode acceptEdits\"")

    def ready(c):
        if re.search(r"trust this folder|Accessing workspace", c, re.I):
            return "dialog"
        if re.search(r"\? for shortcuts|Try \"", c) or re.search(r"(?m)^\s*❯\s*$", c):
            return "ready"
        return None

    c, hit = wait_for(ready, 60, "repl_start")
    if not hit:
        finish("harness-fail", failed_step="repl_start")
    if hit == "dialog":
        send("Enter")
        c, hit = wait_for(lambda x: ready(x) == "ready", 30, "post_trust")
        if not hit:
            finish("harness-fail", failed_step="post_trust")

    send(f'"{PROMPT}"', literal=True)
    time.sleep(0.5)
    send("Enter")

    # Drive up to 4 consecutive gates generically; stop when research kickoff is visible.
    research_markers = r"research-brief|Workflow launched|research agents?|Launching workflow|workflow.*running"
    for round_i in range(6):   # permission prompts consume rounds too
        def next_event(c):
            if re.search(research_markers, c, re.I):
                return "research"
            if question_open(c):
                return "gate"
            return None

        c, hit = wait_for(next_event, 240, f"event_{round_i}", poll=2.0)
        if not hit:
            finish("sut-fail", failed_step=f"event_{round_i}", detail="no gate and no research kickoff")
        if hit == "research":
            finish("success", research_detected_at_round=round_i)

        opts = options_of(c)
        labels = [o[2].strip()[:60] for o in opts]
        GATES.append(labels)

        if is_permission_prompt(c):
            # Answer like a user: prefer "allow ... during this session", else plain Yes.
            prefer = next((i for i, l in enumerate(labels) if re.search(r"allow.*session|don't ask again", l, re.I)),
                          next((i for i, l in enumerate(labels) if re.match(r"Yes\b", l)), 0))
            for _ in range(prefer):
                send("Down")
                time.sleep(0.25)
            send("Enter")
            time.sleep(2.0)
            continue

        multi = bool(re.search(r"\[.\]", c))
        # Generic policy: multiSelect -> toggle first real option, submit via Right+Enter;
        # single-select -> pick the first option matching our intent, else option 1.
        prefer = next((i for i, l in enumerate(labels)
                       if re.search(r"full workflow|approve|yes|all|in-situ|accept", l, re.I)), 0)
        if multi:
            send("Enter")            # toggle highlighted (first) option
            time.sleep(0.4)
            send("Right")
            time.sleep(0.4)
            send("Enter")
        else:
            for _ in range(prefer):
                send("Down")
                time.sleep(0.25)
            send("Enter")
        time.sleep(2.0)

    finish("sut-fail", detail="6 gates driven but research never started")


if __name__ == "__main__":
    main()
