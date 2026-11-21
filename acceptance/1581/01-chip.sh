#!/bin/sh
# #1581 Before merge: a supervisor post, a console message to a lead, a relay and a follow-up carry the chip line; readers strip it.
set -e
exec uv run pytest -q -p no:cacheprovider engineering/tests/test_omnigent_agent.py -k "chip or relay_opens or a_terminal_event_is_posted_to_the_notify_session or a_second_stall_without_progress or followup_file"
