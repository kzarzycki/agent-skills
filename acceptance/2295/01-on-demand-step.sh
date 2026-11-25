#!/bin/sh
# #2295: a `gate_steps` step marked `on_demand: true` is skipped by the gate with one line saying so, runs only when
# named (`local-ci --record --step <name>`), and its pass is keyed by its inputs, recorded and reused.
set -e
exec uv run pytest -q -p no:cacheprovider -n0 gatekeeper/tests/test_approvals_gate_step_on_demand.py
