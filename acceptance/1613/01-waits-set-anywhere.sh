#!/usr/bin/env bash
# #1613 Acceptance: a Waits: set before the STILL WORKING line reads both sessions, in trailer_items and wait_of.
set -euo pipefail
cd "$(dirname "$0")/../.."
uv run --quiet python - <<'PY'
import importlib.util
spec = importlib.util.spec_from_file_location("oa", "omnigent/skills/omnigent-agents/scripts/omnigent_agent.py")
oa = importlib.util.module_from_spec(spec)
import sys; sys.modules["oa"] = oa
spec.loader.exec_module(oa)
a, b = "a" * 32, "b" * 32
t = f"x\n\nWaits: session {a} and session {b}\nSTILL WORKING: waiting on {a} (x) and {b} (y). Report: /r.md"
assert oa.trailer_items(t) == [("session", a), ("session", b)], oa.trailer_items(t)
assert oa.wait_of(t) == f"{a}, {b}", oa.wait_of(t)
print("ok")
PY
