import sys
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def no_origin_reads(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """No supervisor test reads the checkout's origin, since a real read can hang to the 60 s timeout on a slow
    network and makes a test's result depend on the checkout it runs in (#2384):
    - `read_loop_events` is a real `ls-remote` and fetch, which also moves the tests' clocks (#1377): it reads none.
      A module that reads a real bare remote sets `READS_LOOP_EVENTS = True`.
    - `lead_delegation` fetches origin's main for its base policy, with no timeout: it gives the plain wording, `""`.
      A module that tests the reader itself sets `READS_LEAD_DELEGATION = True`.
    - `lead_emit` writes the lead's event on its branch (a real `ls-remote` and push): it writes none. A module that
      tests the writer sets `WRITES_LEAD_EVENTS = True`.
    It lives here, not in test_omnigent_agent.py, because an autouse fixture applies only to the module that defines
    or imports it."""
    agent = sys.modules.get("omnigent_agent")
    if agent is None:
        return
    if not getattr(request.module, "READS_LOOP_EVENTS", False):
        monkeypatch.setattr(agent, "read_loop_events", lambda cwd=None: None)
    if not getattr(request.module, "WRITES_LEAD_EVENTS", False):
        # `wait-on` and the `end-on` lines write the lead's event on its branch: a real `ls-remote` and push (#1386)
        monkeypatch.setattr(agent, "lead_emit", lambda *_, **__: None)
    if not getattr(request.module, "READS_LEAD_DELEGATION", False):
        monkeypatch.setattr(agent, "lead_delegation", lambda *_, **__: "")


@pytest.fixture(autouse=True)
def harness_config_home(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The effort a session signs with comes from the harness's own config when a start names none (#2838), so a
    test must not read the developer's: HOME is a folder holding a Codex config at medium effort and
    Claude Code settings at high (a verifier start is refused without a resolvable effort), and the effort variables are unset."""
    for var in ("CODEX_HOME", "CLAUDE_CONFIG_DIR", "CLAUDE_EFFORT", "CLAUDE_CODE_EFFORT_LEVEL"):
        monkeypatch.delenv(var, raising=False)
    home = tmp_path_factory.mktemp("home")
    (home / ".codex").mkdir()
    (home / ".codex/config.toml").write_text('model_reasoning_effort = "medium"\n')
    (home / ".claude").mkdir()
    (home / ".claude/settings.json").write_text('{"effortLevel": "high"}')
    monkeypatch.setenv("HOME", str(home))


@pytest.fixture(autouse=True)
def cloud_model(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """A claude-cloud start is refused with no model (#2979), so a test of the cloud path that is not about that
    names one, as an agents.yml would. A module that tests the refusal sets `REFUSES_NO_CLOUD_MODEL = True`."""
    agent = sys.modules.get("omnigent_agent")
    if agent is None or getattr(request.module, "REFUSES_NO_CLOUD_MODEL", False):
        return
    real = agent.start

    def start(og, agent_name, *args, **kw):  # type: ignore[no-untyped-def]
        harness = agent_name if agent_name in agent.AGENTS else og.harness(agent_name)
        if (
            harness == agent.CLOUD_HARNESS
            and not kw.get("model")
            and not Path.home().joinpath(".agents/agents.yml").is_file()
        ):
            kw["model"] = "sonnet"
        return real(og, agent_name, *args, **kw)

    monkeypatch.setattr(agent, "start", start)
