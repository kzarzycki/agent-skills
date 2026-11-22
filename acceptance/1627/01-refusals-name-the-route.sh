#!/bin/sh
# #1627 Before merge: `start codex … --pr 1` against a stub is refused with a message naming cloud_verifier.py and thread, and the main-checkout refusals name launch-dir.
set -e
exec uv run pytest -q -p no:cacheprovider engineering/tests/test_omnigent_agent.py -k "refusal_names_the_verifier or is_refused_in_the_main_checkout or far_pinned_main_checkout or not_a_cloud_agent"
