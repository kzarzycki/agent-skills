#!/usr/bin/env bash
set -euo pipefail
# A test call writes and deletes a key through os.environb, serial and under xdist: the conftest's environment hook
# sits on the class os.environb shares with os.environ, so its name check must not run on a bytes key.

root=$(git rev-parse --show-toplevel)
probe=$(mktemp -d)
trap 'rm -rf "$probe"' EXIT
ln -s "$root/engineering/tests/conftest.py" "$probe/conftest.py"

cat > "$probe/test_bytes_probe.py" <<'PY'
import os


def test_bytes_write_and_delete(monkeypatch):
    os.environb[b"PROBE_1553"] = b"value"
    assert os.environ["PROBE_1553"] == "value"
    del os.environb[b"PROBE_1553"]
    assert "PROBE_1553" not in os.environ
PY

cd "$root"
export PYTHONPATH="$root/engineering/tests${PYTHONPATH:+:$PYTHONPATH}" PYTEST_ADDOPTS=
pytest=(uv run python -m pytest -q --tb=short -p no:cacheprovider --rootdir "$probe")
"${pytest[@]}" -p no:xdist "$probe/test_bytes_probe.py"
"${pytest[@]}" -n 2 "$probe/test_bytes_probe.py"
