#!/bin/sh
# #1651 Before merge line 2: on a marked host the hook refuses every heavy command, LOOP_HOST_RUN or not, without RUNNER_SERVER_URL, in any repo; an unmarked host is judged as before.
set -e
exec uv run pytest -q -p no:cacheprovider engineering/tests/test_heavy_run_guard.py -k "orchestration_only or marked or unmarked or shared_module"
