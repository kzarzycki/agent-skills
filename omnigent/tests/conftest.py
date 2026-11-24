import sys

import pytest


@pytest.fixture(autouse=True)
def no_loop_events(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """No loop events on origin for any supervisor test: `read_loop_events` is a real `ls-remote` and fetch against
    the checkout's origin, which moves the tests' clocks (#1377) and can hang to the 60 s timeout on a slow network.
    It lives here, not in test_omnigent_agent.py, because an autouse fixture applies only to the module that defines
    or imports it. A module that reads a real bare remote sets `READS_LOOP_EVENTS = True`."""
    agent = sys.modules.get("omnigent_agent")
    if agent is not None and not getattr(request.module, "READS_LOOP_EVENTS", False):
        monkeypatch.setattr(agent, "read_loop_events", lambda cwd=None: None)
