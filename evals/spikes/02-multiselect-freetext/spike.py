#!/usr/bin/env python3
"""Spike 2: prove the two harder gate interactions the eval harness needs.

A) multiSelect AskUserQuestion: toggle two options with Space, confirm with Enter.
B) free-text answer: pick "Type something." and type a custom reply (the LLM
   simulated-user path for open interview questions).

Run: python3 spike.py  -> JSON report.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time

SESSION = "eval-spike-2"
SCRATCH = "/tmp/eval-spike-2-scratch"
PANE_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pane.log")
PROMPT = (
    "Two steps. Step 1: use AskUserQuestion (multiSelect: true) to ask which toppings I want, "
    "options Cheese, Mushroom, Olives. Step 2: use AskUserQuestion to ask what name to give the dish "
    "(options: Alpha, Beta). After both answers, write a JSON object "
    '{"toppings": [...], "name": "..."} to result.json in the cwd, then end your turn.'
)
T0 = time.time()
TIMINGS = {}
PANES = []


def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)


def pane():
    out = sh(f"tmux capture-pane -p -t {SESSION}").stdout
    PANES.append(f"--- {time.time()-T0:.1f}s ---\n{out}")
    return out


def send(keys, literal=False):
    sh(f"tmux send-keys -t {SESSION} {'-l ' if literal else ''}{keys}")


def wait_for(pred, timeout, step, poll=1.0):
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


def fail(cls, step, detail):
    finish(status=cls, failed_step=step, detail=detail)
    sys.exit(1)


def finish(**extra):
    with open(PANE_LOG, "w") as f:
        f.write("\n".join(PANES[-80:]))
    sh(f"tmux kill-session -t {SESSION} 2>/dev/null")
    print(json.dumps({"spike": "02-multiselect-freetext", "timings_s": TIMINGS,
                      "total_s": round(time.time() - T0, 1), **extra}, indent=2))


def main():
    sh(f"tmux kill-session -t {SESSION} 2>/dev/null")
    shutil.rmtree(SCRATCH, ignore_errors=True)
    os.makedirs(SCRATCH, exist_ok=True)

    sh(f"tmux new-session -d -s {SESSION} -x 200 -y 50 -c {SCRATCH} "
       f"'env -u TMUX claude --permission-mode acceptEdits'")
    _, hit = wait_for(lambda c: re.search(r"\? for shortcuts|Try \"", c) and "Do you trust" not in c, 60, "repl_start")
    if not hit:
        fail("harness-fail", "repl_start", "REPL not ready")

    send(f'"{PROMPT}"', literal=True)
    time.sleep(0.5)
    send("Enter")

    # A) multiSelect gate. Structural detection only: numbered option line + question-UI
    # footer ("Enter to ... navigate/toggle"). Content words alone match the prompt echo.
    def question_ui(c, option_word):
        return (re.search(rf"\d+\.\s*(\[.\]\s*)?{option_word}", c)
                and re.search(r"Enter to .*(select|confirm|submit)|to navigate|to toggle", c, re.I))

    _, hit = wait_for(lambda c: question_ui(c, "Cheese"), 120, "multiselect_detect", poll=1.5)
    if not hit:
        fail("harness-fail", "multiselect_detect", "multiSelect gate never rendered")
    nav_hint = [l for l in pane().splitlines() if re.search(r"Enter to|navigate|toggle|Tab", l)][:2]

    # multiSelect UI: checkboxes `[ ]` per option, header tabs `← ☐ <Q> ✔ Submit →`.
    # Enter toggles the highlighted option; Submit = Right (to the Submit tab) + Enter.
    send("Enter")          # toggle option 1 (Cheese)
    time.sleep(0.4)
    send("Down")
    time.sleep(0.3)
    send("Down")
    time.sleep(0.3)
    send("Enter")          # toggle option 3 (Olives)
    time.sleep(0.4)
    c = pane()
    toggles = re.findall(r"\[[^\] ]\]\s*(Cheese|Olives|Mushroom)", c)
    TIMINGS["toggled"] = toggles
    send("Right")          # move to ✔ Submit tab
    time.sleep(0.4)
    send("Enter")          # submit selection

    # B) second gate -> choose free-text path and type a custom name.
    _, hit = wait_for(lambda c: question_ui(c, "Alpha"), 120, "second_gate_detect", poll=1.5)
    if not hit:
        fail("harness-fail", "second_gate_detect", "second gate never rendered (multiSelect answer may have failed)")

    # Find the "Type something." style option index by reading the pane.
    c = pane()
    m = re.search(r"(\d)\.\s*Type something", c)
    if not m:
        fail("harness-fail", "freetext_option", "no free-text option offered on single-select gate")
    idx = int(m.group(1))
    for _ in range(idx - 1):
        send("Down")
        time.sleep(0.2)
    send("Enter")
    time.sleep(0.8)
    send('"Gamma-Custom"', literal=True)
    time.sleep(0.3)
    send("Enter")

    # Residue: result.json
    def artifact(_c):
        p = os.path.join(SCRATCH, "result.json")
        if os.path.exists(p):
            try:
                return json.load(open(p))
            except json.JSONDecodeError:
                return None
        return None

    _, result = wait_for(artifact, 120, "artifact_write", poll=1.0)
    if result is None:
        fail("sut-fail", "artifact_write", "result.json never appeared/parsed")

    toppings_ok = sorted(result.get("toppings", [])) == ["Cheese", "Olives"]
    name_ok = "Gamma" in str(result.get("name", ""))
    finish(status="success" if (toppings_ok and name_ok) else "sut-fail",
           result=result, multiselect_correct=toppings_ok, freetext_correct=name_ok,
           nav_hints_seen=nav_hint)


if __name__ == "__main__":
    main()
