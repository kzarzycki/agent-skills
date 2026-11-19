#!/bin/sh
# #1380 Before merge lines: a verifier pass emits `waiting`, beats, and ends `ok` or `failed` by the report's
# `SATISFIED:` line with the posted review as `url`; every supervisor wait the existing tests cover is still read
# correctly with the prose rules deleted.
set -e
exec uv run pytest -q -p no:cacheprovider engineering/tests/test_cloud_verifier_events.py engineering/tests/test_omnigent_agent.py engineering/tests/test_lead_event.py
