import sys

# The engineering loop's script tests load modules from a shipped skill folder;
# a bytecode cache written there would ship with the package.
sys.dont_write_bytecode = True

import pytest


@pytest.fixture(autouse=True)
def _outside_omnigent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests run as if outside an Omnigent session; one that needs a session sets it."""
    monkeypatch.delenv("OMNIGENT_RUNNER_PRIMARY_SESSION_ID", raising=False)
