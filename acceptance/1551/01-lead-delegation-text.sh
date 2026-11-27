#!/bin/sh
# #1551 Before merge line 1: a lead on a repo whose base policy sets loop.delegate: all gets the delegation text, any other keeps today's wording.
set -e
exec uv run pytest -q -p no:cacheprovider omnigent/tests/test_omnigent_lead_delegation.py -k "delegation_text or top_level_lead_start or another_host or policy_reader or cloud_swaps or the_text_names or origin or gh_call or outside_a_checkout or this_host_named"
