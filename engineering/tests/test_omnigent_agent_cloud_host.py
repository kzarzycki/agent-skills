"""omnigent_agent.py places a claude-cloud child on a bridge host (#838): refuses a host without
the cloud harness or a workspace without the environment pin, picks the roomiest host, and never
duplicates a session whose create timed out. A stand-in server answers the HTTP calls only."""

import json
from email.message import Message
from pathlib import Path
from urllib.error import HTTPError

import pytest
import test_omnigent_agent as base
from test_omnigent_agent import FakeOmnigent, no_model, no_sleep  # noqa: F401  (fixtures by name)

omnigent_agent = base.omnigent_agent
CLOUD = omnigent_agent.CLOUD_HARNESS
WORK = "/w/repo"
SETTINGS = f"{WORK}/.claude/settings.local.json"


class Hosts(omnigent_agent.Omnigent):
    """The real client over a hosts list and host folders (path to entry names) and files."""

    def __init__(self, rows: list[dict], files: dict[str, str] | None = None) -> None:
        self.base, self.host_id, self._token, self.loops = "http://x", "here", "t", {}
        self.rows, self.files = rows, files or {}

    def call(self, method: str, path: str, body: object = None, **_: object) -> dict:
        if path == "/v1/hosts":
            return {"hosts": self.rows}
        if path.startswith("/v1/hosts/"):
            folder = "/" + path.split("?")[0].split("/filesystem/")[1].strip("/") + "/"
            names = {f[len(folder) :].split("/")[0] for f in self.files if f.startswith(folder)}
            if not names:
                raise omnigent_agent.Fail("GET") from HTTPError(path, 404, "", Message(), None)
            return {"data": [{"name": n} for n in sorted(names)]}
        raise AssertionError(f"unfaked {method} {path}")

    def read_file(self, sid: str, path: str) -> str:
        return self.files[path]


def row(host: str, mb: float, *harnesses: str, status: str = "online") -> dict:
    return {
        "host_id": host,
        "name": host.upper(),
        "status": status,
        "configured_harnesses": {h: True for h in harnesses},
        "memory_available_mb": mb,
    }


@pytest.fixture(autouse=True)
def live(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(omnigent_agent, "live_sessions", lambda og, host: [{"id": "s9"}])


def pinned(env: str = "env_1") -> str:
    return json.dumps({"remote": {"defaultEnvironmentId": env}})


def test_a_host_without_the_cloud_harness_is_refused_naming_it_and_what_it_has() -> None:
    og = Hosts([row("there", 900, "claude-native")], {SETTINGS: pinned()})
    with pytest.raises(omnigent_agent.Fail, match=rf"THERE configures no {CLOUD}.*claude-native"):
        omnigent_agent.refuse_unfit_cloud_host(og, "there", Path(WORK))


def test_the_roomiest_online_host_with_the_cloud_harness_is_picked(
    capsys: pytest.CaptureFixture[str],
) -> None:
    og = Hosts(
        [
            row("small", 100, CLOUD),
            row("big", 900, CLOUD),
            row("bigger", 9000, "claude-native"),  # no cloud harness
            row("off", 9999, CLOUD, status="offline"),
        ],
        {f"{WORK}/x": ""},
    )
    assert omnigent_agent.pick_cloud_host(og, Path(WORK)) == "big"
    assert "big".upper() in capsys.readouterr().err.upper()


def test_with_no_qualifying_host_or_a_failing_hosts_call_the_start_stays_here() -> None:
    og = Hosts([row("there", 900, "claude-native")])
    assert omnigent_agent.pick_cloud_host(og, Path(WORK)) is None
    og.call = lambda *a, **k: (_ for _ in ()).throw(omnigent_agent.Fail("GET /v1/hosts: HTTP 502"))  # type: ignore[method-assign]
    assert omnigent_agent.pick_cloud_host(og, Path(WORK)) is None


def test_the_launchers_own_host_counts_when_it_has_most_memory() -> None:
    og = Hosts([row("here", 5000, CLOUD), row("there", 100, CLOUD)], {f"{WORK}/x": ""})
    assert omnigent_agent.pick_cloud_host(og, Path(WORK)) == "here"


def test_a_workspace_without_the_environment_pin_is_refused_before_a_session_exists() -> None:
    rows = [row("there", 900, CLOUD)]
    for files in ({f"{WORK}/x": ""}, {SETTINGS: json.dumps({})}):  # no file, a file with no pin
        og = Hosts(rows, files)
        with pytest.raises(
            omnigent_agent.Fail, match="THERE.*(missing|no remote.defaultEnvironmentId)"
        ):
            omnigent_agent.refuse_unfit_cloud_host(og, "there", Path(WORK))
    omnigent_agent.refuse_unfit_cloud_host(Hosts(rows, {SETTINGS: pinned()}), "there", Path(WORK))


class Timeout(FakeOmnigent):
    """A create the server completes while the answer times out; the lookup sees it late."""

    def __init__(self) -> None:
        super().__init__()
        self.harnesses["claude-cloud"] = CLOUD
        self.lookups = 0

    def create(self, *args: object, **kwargs: object) -> str:
        super().create(*args, **kwargs)  # type: ignore[arg-type]
        raise omnigent_agent.Fail("POST /v1/sessions: timed out") from TimeoutError("timed out")

    def find(self, title: str, after: float, top_level: bool = False) -> str | None:
        self.lookups += 1
        return super().find(title, after, top_level) if self.lookups > 2 else None


def test_a_create_that_timed_out_is_looked_up_by_title_and_reused_not_duplicated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(omnigent_agent, "pin_environment", lambda *_: None)
    og = Timeout()
    sid, _ = omnigent_agent.start(og, "claude-cloud", "t", "do X", tmp_path / "r.md", None, 0)
    assert sid == "s0" and list(og.sessions) == ["s0"] and og.lookups == 3
