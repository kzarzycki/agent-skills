#!/bin/sh
# #1551 Before merge line 2: supervise flags a USER NEEDED turn end with no open question card, and reports one with a card as before.
set -e
exec uv run pytest -q -p no:cacheprovider engineering/tests/test_omnigent_lead_delegation.py -k "user_needed or unasked"
