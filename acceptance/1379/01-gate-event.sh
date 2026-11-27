#!/bin/sh
# #1379 Before merge lines: `local-ci` writes the `gate` event on the branch it gates: `waiting` at each beat while it
# waits for a slot or runs, then `ok` with the record's path; a failing step ends `failed`; the event's failure never
# changes the gate's exit.
set -e
exec uv run pytest -q -p no:cacheprovider gatekeeper/tests/test_approvals_gate_event.py
