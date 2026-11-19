#!/bin/sh
# #1380 Before merge lines: a verifier pass emits `waiting`, beats, and ends `ok` or `failed` by the report's
# `SATISFIED:` line with the posted review as `url`; `reap` of a closed PR clears its branch's events.
set -e
exec uv run pytest -q -p no:cacheprovider engineering/tests/test_cloud_verifier_events.py engineering/tests/test_omnigent_reap_events.py
