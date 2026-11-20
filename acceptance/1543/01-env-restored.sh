#!/usr/bin/env bash
# The drift tests' fake vendir runs `python3` from PATH: put one without yaml behind the venv, as CI's mise Python is,
# then run the test whose in-process cli() dropped the venv from PATH before them.
set -euo pipefail
bin=$(mktemp -d)
trap 'rm -rf "$bin"' EXIT
py=$(command -v /usr/bin/python3 python3 | head -1)
cat > "$bin/python3" <<SH
#!/bin/sh
exec "$py" -I -c 'import sys; sys.modules["yaml"] = None; sys.argv = sys.argv[1:]; import runpy; runpy.run_path(sys.argv[0], run_name="__main__")' "\$@"
SH
chmod +x "$bin/python3"
# one process, whatever the caller's PYTEST_ADDOPTS: split across xdist workers, the drift tests would never see the leak
PATH="$bin:$PATH" PYTEST_ADDOPTS= uv run pytest -q -p no:cacheprovider -p no:xdist \
  engineering/tests/test_approvals_gate_event.py::test_a_detached_run_that_wrote_its_end_is_not_ended_twice \
  tests/capability_pack/test_drift.py
