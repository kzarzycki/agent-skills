#!/bin/sh
# #1376 Before merge lines: `wait-on` and `end-on` write the lead event, the supervisor reads it before the prose,
# a needs-owner question reaches the owner whole and only with the message it was written for, and only the
# followed lead's own branch is read.
set -e
exec uv run pytest -q -p no:cacheprovider omnigent/tests/test_lead_event.py
