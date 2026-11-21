#!/bin/sh
# #1651 Before merge line 3: a failed GitHub read in a cloud session names the REST fallback and says the verb runs in this session.
set -e
exec uv run pytest -q -p no:cacheprovider engineering/tests/test_approvals_cloud_read_note.py
