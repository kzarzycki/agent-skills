#!/bin/sh
# #1375 Before merge lines 1 to 4: an event emitted in one clone is read in another through a bare remote with the
# same state, url and question; two beats leave one commit on the ref; `wait` exits 0, 1, 2, 3 and 4; an emit to an
# unreachable origin exits 0 with one warning and the local ref written.
set -e
exec uv run pytest -q -p no:cacheprovider gatekeeper/tests/test_events.py
