#!/bin/sh
# #1377 Before merge lines: the supervisor reads `refs/loop/*` events. A wait whose event changed within twice its beat is
# live and raises no deadline; a silent one raises it, naming the kind; a pending required check keeps a wait live; an end
# is told to the lead once and a `needs-owner` question goes to the owner ahead of news; a branch with no events behaves
# as before.
set -e
exec uv run pytest -q -p no:cacheprovider omnigent/tests/test_omnigent_agent_events.py
