#!/bin/sh
# #2085: a merge-queue dequeue reaches the lead that owns its PR, rejections and flakes are counted, and the
# gatekeeper docs' queue-only variant keeps the skill references, layers and mergify template tests green.
set -e
exec uv run pytest -q -p no:cacheprovider -n0 \
  "omnigent/tests/test_omnigent_queue_rejects.py::test_queue_comment_parses" \
  "omnigent/tests/test_omnigent_queue_rejects.py::test_dequeue_relays_to_labelled_lead" \
  "omnigent/tests/test_omnigent_queue_rejects.py::test_dequeue_relays_to_worker_parent_lead" \
  "omnigent/tests/test_omnigent_queue_rejects.py::test_dequeue_unarchives_lead" \
  "omnigent/tests/test_omnigent_queue_rejects.py::test_dequeue_without_lead_acts" \
  "omnigent/tests/test_omnigent_queue_rejects.py::test_dequeue_host_offline_retries" \
  "omnigent/tests/test_omnigent_queue_rejects.py::test_rejection_share_threshold" \
  "omnigent/tests/test_omnigent_queue_rejects.py::test_flake_told_apart" \
  "omnigent/tests/test_omnigent_queue_rejects.py::test_window_prunes" \
  tests/test_skill_references.py tests/test_skill_layers.py tests/test_mergify_config.py
