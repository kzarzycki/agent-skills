#!/usr/bin/env python3
"""Spike 3: config isolation + plugin variant pinning + real /workflow first gate.

Proves:
A) An isolated CLAUDE_CONFIG_DIR (copied credentials, minimal settings, no user
   hooks) gives a clean SUT env — variant pinning becomes config-dir-per-variant.
B) The workflow plugin installs into the isolated config from a local marketplace
   path (the pinning mechanism for version A vs B).
C) A real `/workflow <item>` run reaches its first gate (research buckets) and
   renders detectably; the run can be killed cleanly at that point.

Run: python3 spike.py  -> JSON report. Kills the SUT at first gate (cost guard).
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time

SESSION = "eval-spike-3"
SCRATCH = "/tmp/eval-spike-3-scratch"
CONFIG = "/tmp/eval-spike-3-config"
REPO = "/home/agent/dev/agent-skills"
PANE_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pane.log")
PROMPT = "/workflow build a tiny tic-tac-toe CLI game in python"
T0 = time.time()
TIMINGS = {}
PANES = []
FINDINGS = {}


def sh(cmd, env=None):
    e = dict(os.environ, **(env or {}))
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, env=e)


def pane():
    out = sh(f"tmux capture-pane -p -t {SESSION}").stdout
    PANES.append(f"--- {time.time()-T0:.1f}s ---\n{out}")
    return out


def send(keys, literal=False):
    sh(f"tmux send-keys -t {SESSION} {'-l ' if literal else ''}{keys}")


def wait_for(pred, timeout, step, poll=1.5):
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


def finish(status, **extra):
    with open(PANE_LOG, "w") as f:
        f.write("\n".join(PANES[-80:]))
    sh(f"tmux kill-session -t {SESSION} 2>/dev/null")
    print(json.dumps({"spike": "03-isolation-workflow-gate", "status": status,
                      "timings_s": TIMINGS, "findings": FINDINGS,
                      "total_s": round(time.time() - T0, 1), **extra}, indent=2))
    sys.exit(0 if status == "success" else 1)


def main():
    sh(f"tmux kill-session -t {SESSION} 2>/dev/null")
    for d in (SCRATCH, CONFIG):
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d, exist_ok=True)

    # A) isolated config: credentials copied, minimal settings, onboarding pre-done.
    shutil.copy(os.path.expanduser("~/.claude/.credentials.json"), os.path.join(CONFIG, ".credentials.json"))
    json.dump({"hasCompletedOnboarding": True, "theme": "dark"}, open(os.path.join(CONFIG, ".claude.json"), "w"))
    json.dump({}, open(os.path.join(CONFIG, "settings.json"), "w"))
    env = {"CLAUDE_CONFIG_DIR": CONFIG}

    # B) marketplace add + plugin install into the isolated config (CLI, no session).
    r1 = sh(f"claude plugin marketplace add {REPO}", env=env)
    r2 = sh("claude plugin install workflow@kzarzycki-agent-skills", env=env)
    FINDINGS["marketplace_add"] = (r1.returncode, (r1.stdout + r1.stderr).strip()[-200:])
    FINDINGS["plugin_install"] = (r2.returncode, (r2.stdout + r2.stderr).strip()[-200:])
    if r2.returncode != 0:
        finish("harness-fail", failed_step="plugin_install")

    # C) launch the SUT with the isolated config.
    sh(f"tmux new-session -d -s {SESSION} -x 200 -y 50 -c {SCRATCH} "
       f"\"env -u TMUX CLAUDE_CONFIG_DIR={CONFIG} claude --permission-mode acceptEdits\"")

    def ready(c):
        if re.search(r"Do you trust|trust this folder|Accessing workspace|press Enter to continue|Choose the text style", c, re.I):
            return "dialog"
        if re.search(r"\? for shortcuts|Try \"", c) or re.search(r"(?m)^\s*❯\s*$", c):
            return "ready"
        return None

    content, hit = wait_for(ready, 60, "repl_start")
    if not hit:
        finish("harness-fail", failed_step="repl_start")
    dialogs = 0
    while hit == "dialog" and dialogs < 4:
        send("Enter")
        dialogs += 1
        time.sleep(1.5)
        content, hit = wait_for(ready, 30, f"dialog_{dialogs}")
        if not hit:
            finish("harness-fail", failed_step=f"dialog_{dialogs}")
    FINDINGS["startup_dialogs"] = dialogs
    FINDINGS["user_hooks_leaked"] = bool(re.search(r"memsearch|preload-skills", content or ""))

    send(f'"{PROMPT}"', literal=True)
    time.sleep(0.5)
    send("Enter")

    # First /workflow gate: research buckets (AskUserQuestion). Structural detection.
    def gate(c):
        return (re.search(r"\d+\.\s*(\[.\]\s*)?\S", c)
                and re.search(r"Enter to .*(select|confirm)|to navigate", c, re.I)
                and re.search(r"research|bucket|interview", c, re.I))

    content, hit = wait_for(gate, 300, "workflow_gate_detect", poll=2.0)
    if not hit:
        # distinguish: did /workflow even resolve?
        FINDINGS["workflow_resolved"] = not re.search(r"Unknown (slash )?command|No such (command|skill)", "\n".join(PANES[-5:]), re.I)
        finish("sut-fail", failed_step="workflow_gate_detect")

    gate_lines = [l for l in content.splitlines() if l.strip()][-16:]
    finish("success", workflow_gate_sample=gate_lines)


if __name__ == "__main__":
    main()
