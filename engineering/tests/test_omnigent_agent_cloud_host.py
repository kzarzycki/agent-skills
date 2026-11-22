"""omnigent_agent.py places a claude-cloud child on a bridge host (#838): refuses a host without
the cloud harness or a workspace without the environment pin, picks the roomiest host, maps a
launcher's local path to the bridge's launch dir when the launcher has no cloud harness (#1693),
and never duplicates a session whose create timed out. A stand-in server answers the HTTP calls only."""

import json
from email.message import Message
from pathlib import Path
from urllib.error import HTTPError

import pytest
import test_omnigent_agent as base
from test_omnigent_agent import (  # noqa: F401  (the fixtures apply here by name)
    FakeOmnigent,
    no_model,
    no_sleep,
    trusted_folders,
)

omnigent_agent = base.omnigent_agent
CLOUD = omnigent_agent.CLOUD_HARNESS
REAL_LIVE = omnigent_agent.live_sessions
WORK = "/w/repo"
SETTINGS = f"{WORK}/.claude/settings.local.json"


class Hosts(omnigent_agent.Omnigent):
    """The real client over a hosts list and host folders (path to entry names) and files."""

    def __init__(self, rows: list[dict], files: dict[str, str] | None = None) -> None:
        self.base, self.host_id, self._token, self.loops = "http://x", "here", "t", {}
        self.rows, self.files, self.gone = rows, files or {}, set()
        self.records: list[dict] = []  # the project's sessions, as the server lists them

    def call(self, method: str, path: str, body: object = None, **_: object) -> dict:
        if path == "/v1/hosts":
            return {"hosts": self.rows}
        if path == "/v1/projects":
            return {"data": [{"id": "p0", "name": "Chief of staff"}, {"id": "p1", "name": "repo"}]}
        if path.startswith("/v1/sessions?kind=default&project=repo"):
            return {"data": self.records}
        if path.startswith("/v1/hosts/"):
            folder = "/" + path.split("?")[0].split("/filesystem/")[1].strip("/") + "/"
            names = {f[len(folder) :].split("/")[0] for f in self.files if f.startswith(folder)}
            if not names:
                raise omnigent_agent.Fail("GET") from HTTPError(path, 404, "", Message(), None)
            return {"data": [{"name": n} for n in sorted(names)]}
        raise AssertionError(f"unfaked {method} {path}")

    def harness(self, name: str) -> str:
        return CLOUD if name == "claude-cloud" else "claude-native"

    def home(self, name: str) -> dict:  # the caller's session files under another project
        return {"id": "p0", "name": "Chief of staff"}

    def read_file(self, sid: str, path: str) -> str:
        if path in self.gone:
            raise omnigent_agent.Gone(path)
        if path not in self.files:  # a folder reads as its entries
            return "\n".join(f[len(path) + 1 :] for f in self.files if f.startswith(path + "/"))
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
def project(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OMNIGENT_PROJECT", raising=False)
    monkeypatch.setattr(omnigent_agent, "repo_name", lambda: "repo")


@pytest.fixture(autouse=True)
def live(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The hosts with no live session to read a file through (all have one by default)."""
    idle: list[str] = []
    monkeypatch.setattr(
        omnigent_agent, "live_sessions", lambda og, host: [] if host in idle else [{"id": "s9"}]
    )
    return idle


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
        {SETTINGS: pinned()},
    )
    assert omnigent_agent.pick_cloud_host(og, Path(WORK)) == ("big", Path(WORK))
    assert "big".upper() in capsys.readouterr().err.upper()


def test_with_no_qualifying_host_or_a_failing_hosts_call_the_start_stays_here() -> None:
    og = Hosts([row("there", 900, "claude-native")])
    assert omnigent_agent.pick_cloud_host(og, Path(WORK)) is None
    og.call = lambda *a, **k: (_ for _ in ()).throw(omnigent_agent.Fail("GET /v1/hosts: HTTP 502"))  # type: ignore[method-assign]
    assert omnigent_agent.pick_cloud_host(og, Path(WORK)) is None


def test_the_launchers_own_host_counts_when_it_has_most_memory() -> None:
    og = Hosts([row("here", 5000, CLOUD), row("there", 100, CLOUD)], {SETTINGS: pinned()})
    assert omnigent_agent.pick_cloud_host(og, Path(WORK)) == ("here", Path(WORK))


def test_a_workspace_without_the_environment_pin_is_refused_before_a_session_exists() -> None:
    rows = [row("there", 900, CLOUD)]
    for files in ({f"{WORK}/x": ""}, {SETTINGS: json.dumps({})}):  # no file, a file with no pin
        og = Hosts(rows, files)
        with pytest.raises(omnigent_agent.Fail, match="THERE.*(missing|no remote.defaultEnvi)"):
            omnigent_agent.refuse_unfit_cloud_host(og, "there", Path(WORK))
    omnigent_agent.refuse_unfit_cloud_host(Hosts(rows, {SETTINGS: pinned()}), "there", Path(WORK))


def test_a_pin_that_cannot_be_read_refuses_an_explicit_host_and_says_how_to_go_on(
    live: list[str],
) -> None:
    og = Hosts([row("there", 900, CLOUD)], {SETTINGS: pinned()})
    live.append("there")  # no live session to read through
    with pytest.raises(omnigent_agent.Fail, match="can't be read.*start any session on THERE"):
        omnigent_agent.refuse_unfit_cloud_host(og, "there", Path(WORK))
    live.clear()
    og.gone.add(SETTINGS)  # a session answered 404
    with pytest.raises(omnigent_agent.Fail, match="can't be read.*start any session"):
        omnigent_agent.refuse_unfit_cloud_host(og, "there", Path(WORK))


def test_a_pin_file_that_is_not_json_is_refused() -> None:
    og = Hosts([row("there", 900, CLOUD)], {SETTINGS: "{"})
    with pytest.raises(omnigent_agent.Fail, match="is not JSON") as e:
        omnigent_agent.refuse_unfit_cloud_host(og, "there", Path(WORK))
    assert "start any session" not in str(e.value)


def test_the_pick_skips_a_host_whose_pin_cannot_be_read_and_says_why(
    live: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    og = Hosts([row("idle", 9000, CLOUD), row("busy", 100, CLOUD)], {SETTINGS: pinned()})
    live.append("idle")
    assert omnigent_agent.pick_cloud_host(og, Path(WORK)) == ("busy", Path(WORK))
    assert "host IDLE skipped for a cloud child" in capsys.readouterr().err
    live.append("busy")  # none readable: the launcher's host
    assert omnigent_agent.pick_cloud_host(og, Path(WORK)) is None


def test_the_pick_skips_a_host_whose_pin_file_is_not_json() -> None:
    og = Hosts([row("bad", 9000, CLOUD)], {SETTINGS: "{"})
    assert omnigent_agent.pick_cloud_host(og, Path(WORK)) is None


HOME = "/home/u"
CONFIG = f"{HOME}/.claude.json"


def trust(*places: str) -> str:
    return json.dumps({"projects": {p: {"hasTrustDialogAccepted": True} for p in places}})


def trusting(config: str | None, git: str = "") -> Hosts:
    work = "/home/u/repo"
    files = {f"{work}/.claude/settings.local.json": pinned(), f"{work}/.git": git}
    if config is not None:
        files[CONFIG] = config
    return Hosts([row("there", 900, CLOUD)], files)


def test_an_untrusted_workspace_is_refused_and_a_trusted_one_or_its_main_worktree_passes() -> None:
    work = Path("/home/u/repo")
    with pytest.raises(omnigent_agent.Fail, match="not trusted by Claude Code"):
        omnigent_agent.refuse_unfit_cloud_host(trusting(trust("/other")), "there", work)
    omnigent_agent.refuse_unfit_cloud_host(trusting(trust(str(work))), "there", work)
    link = "gitdir: /home/u/main/.git/worktrees/repo"  # a linked worktree takes its main's trust
    omnigent_agent.refuse_unfit_cloud_host(trusting(trust("/home/u/main"), link), "there", work)


def test_trust_that_cannot_be_read_is_refused_and_a_home_not_found_is_not_checked() -> None:
    work = Path("/home/u/repo")
    with pytest.raises(omnigent_agent.Fail, match="can't be read|not JSON"):
        omnigent_agent.refuse_unfit_cloud_host(trusting("{"), "there", work)
    omnigent_agent.refuse_unfit_cloud_host(trusting(None), "there", work)  # no config listed
    og = trusting(None)  # no home under the workspace's path either
    og.files = {k.replace("/home/u", "/srv/u"): v for k, v in og.files.items()}
    omnigent_agent.refuse_unfit_cloud_host(og, "there", Path("/srv/u/repo"))


def cloud_far(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, rows: list[dict], work: str = "/there/repo"
) -> FakeOmnigent:
    """A launcher on host ``h`` and cloud host ``far`` with a live session and a pinned ``work``
    (a folder here too); ``rows`` is what GET /v1/hosts lists."""
    monkeypatch.setattr(omnigent_agent, "live_sessions", REAL_LIVE)
    monkeypatch.setattr(omnigent_agent, "pin_environment", lambda *_: None)
    og = base.far_host(monkeypatch, tmp_path, "far", meminfo=base.mem(9000), loadavg="1 1 1")
    monkeypatch.setattr(omnigent_agent, "capacity", lambda **_: (True, "room here"))
    og.host_rows = rows
    og.procs["far"][f"{work}/.claude/settings.local.json"] = pinned()
    return og


def started(og: FakeOmnigent, work: str, *argv: str) -> int:
    return omnigent_agent.main(
        ["start", "claude-cloud", "t", "b.md", f"{work}/r.md", "--confirm-seconds", "0"]
        + ["--workspace", work, *argv]
    )


def test_start_places_a_cloud_child_on_the_picked_host(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    rows = [row("h", 100, CLOUD), row("far", 9000, CLOUD)]
    og = cloud_far(monkeypatch, tmp_path, rows)
    assert started(og, "/there/repo") == 0
    assert og.hosts_of == {"s0": "far"}


def test_start_keeps_a_lead_where_it_is_and_a_pick_of_the_launcher_leaves_host_unset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "repo").mkdir()
    work = str(tmp_path / "repo")
    og = cloud_far(monkeypatch, tmp_path, [row("h", 100, CLOUD), row("far", 9000, CLOUD)], work)
    assert started(og, work, "--top-level") == 0  # a lead never moves
    assert og.hosts_of == {"s0": "h"}
    rows = [row("h", 9000, CLOUD), row("far", 100, CLOUD)]
    og2 = cloud_far(monkeypatch, tmp_path, rows, work)
    assert started(og2, work) == 0
    assert og2.hosts_of == {"s0": "h"}


def test_start_skips_the_pick_for_a_relative_workspace(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    og = cloud_far(monkeypatch, tmp_path, [row("far", 9000, CLOUD)])
    for path in ("repo/.claude/settings.local.json", "/repo/.claude/settings.local.json"):
        og.procs["far"][path] = pinned()  # there, were it asked
    (tmp_path / "repo").mkdir()
    assert started(og, "repo") == 0
    assert og.hosts_of == {"s0": "h"}


def test_start_refuses_an_explicit_host_without_the_cloud_harness_before_any_create(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    og = cloud_far(monkeypatch, tmp_path, [row("far", 9000, "claude-native")])
    assert started(og, "/there/repo", "--host", "far") == 1
    assert og.sessions == {} and "FAR configures no" in capsys.readouterr().err


def test_start_refuses_an_explicit_host_whose_pin_cannot_be_verified(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    og = cloud_far(monkeypatch, tmp_path, [row("far", 9000, CLOUD)])
    og.others = []  # no live session on the host to read through
    assert started(og, "/there/repo", "--host", "far") == 1
    assert og.sessions == {} and "start any session on FAR" in capsys.readouterr().err


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


LOCAL = "/Users/me/dev/repo"  # the launcher's checkout, on no bridge host
FAR_ID = "4673a77ef6ad4a169d5e86c10bafc5ee"  # how a session row names host far, as the server does
LAUNCH = "/home/a/dev/repo-cloud"  # the repository's pinned launch dir on the bridge host


def bridge(*records: dict) -> Hosts:
    """A launcher configuring no cloud harness beside bridge host ``far`` holding ``LAUNCH``."""
    og = Hosts(
        [row("here", 9000, "claude-native"), {**row("far", 500, CLOUD), "id": FAR_ID}],
        {f"{LAUNCH}/.claude/settings.local.json": pinned(), f"{LAUNCH}/.git": ""},
    )
    og.records = list(records)
    return og


def record(host: str, place: str, at: float = 1, agent: str = "claude-cloud") -> dict:
    """A session row on ``host``, which names host far by its hex id."""
    named = FAR_ID if host == "far" else host
    return {"host_id": named, "workspace": place, "agent_name": agent, "created_at": at}


def test_a_launcher_without_the_cloud_harness_maps_its_path_to_the_bridges_launch_dir() -> None:
    og = bridge(
        record("far", "/home/a/old", at=5),  # newest, but not pinned there: skipped
        record("far", LAUNCH, at=2),
        record("far", "/home/a/native", at=9, agent="claude"),  # not a cloud session
        record("elsewhere", "/x", at=9),
    )
    assert omnigent_agent.pick_cloud_host(og, Path(LOCAL)) == ("far", Path(LAUNCH))
    assert omnigent_agent.pick_cloud_host(og, None) == ("far", Path(LAUNCH))
    assert omnigent_agent.cloud_placement(og) == ("far", LAUNCH)
    assert omnigent_agent.far_launch_dirs(og, "far") == ["/home/a/old", LAUNCH]
    assert omnigent_agent.far_launch_dirs(og, "FAR") == ["/home/a/old", LAUNCH]  # by name too


def test_a_launcher_with_the_cloud_harness_never_has_its_path_mapped() -> None:
    og = bridge(record("far", LAUNCH))
    og.rows = [row("here", 100, CLOUD), row("far", 500, CLOUD)]
    assert omnigent_agent.pick_cloud_host(og, Path(LOCAL)) == ("here", Path(LOCAL))
    assert omnigent_agent.cloud_placement(og) is None


def test_a_launcher_without_the_cloud_harness_and_no_launch_dir_is_refused_not_sent_to_412(
    capsys: pytest.CaptureFixture[str],
) -> None:
    og = bridge()  # no cloud session of the project on the bridge host names its launch dir
    with pytest.raises(omnigent_agent.Fail, match=rf"configures no {CLOUD}.*FAR.*pass --host"):
        omnigent_agent.pick_cloud_host(og, Path(LOCAL))
    og.rows = [row("here", 9000, "claude-native")]
    with pytest.raises(omnigent_agent.Fail, match="no online host configures it"):
        omnigent_agent.cloud_placement(og)


class Bridged(FakeOmnigent):
    """``cloud_far``'s server, whose project lists one cloud session on ``far`` at ``LAUNCH``."""

    def home(self, name: str) -> dict:  # the caller's session files under another project
        return {"id": "p0", "name": "Chief of staff"}

    def project(self, name: str) -> dict | None:
        return {"id": "p1", "name": "repo"} if name == "repo" else None

    def call(self, method: str, path: str, body: object = None) -> dict:
        if path.startswith("/v1/sessions?kind=default&project=repo"):
            return {"data": [record("far", LAUNCH)]}
        return super().call(method, path, body)


@pytest.mark.parametrize(
    "argv",
    [
        ["start", "--workspace", LOCAL],  # the cloud gate's start: a local launch dir
        ["start"],  # no --workspace: this directory
        ["run", "--workspace", LOCAL, "--timeout", "1"],
    ],
)
def test_start_and_run_from_a_launcher_without_the_cloud_harness_land_on_the_bridge(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, argv: list[str]
) -> None:
    monkeypatch.setattr(base, "FakeOmnigent", Bridged)
    rows = [row("h", 9000, "claude-native"), {**row("far", 500, CLOUD), "id": FAR_ID}]
    og = cloud_far(monkeypatch, tmp_path, rows, LAUNCH)
    og.others = [{"id": "x1", "host_id": FAR_ID, "status": "idle", "updated_at": 1}]
    og.procs[FAR_ID] = og.procs["far"]  # read through a session the server files under the hex id
    og.procs["far"][f"{LAUNCH}/.git"] = ""
    monkeypatch.setattr(omnigent_agent, "wait", lambda *a, **k: "done")
    cmd, *rest = argv
    code = omnigent_agent.main(
        [cmd, "claude-cloud", "t", "b.md", f"{tmp_path}/r.md", "--confirm-seconds", "0", *rest]
    )
    assert (code, og.hosts_of, og.workspaces) == (0, {"s0": "far"}, [LAUNCH])
