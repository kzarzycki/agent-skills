"""`project_line` reads docs/agents/loop.md on the host the session will run on (#1084): through
the file API of a host that isn't this one, once per start, and a start whose loop.md can't be
read there fails before any session exists. The Omnigent API is stubbed."""

from pathlib import Path

import pytest
from test_omnigent_agent import (  # noqa: F401  (the fixtures apply here by name)
    FakeOmnigent,
    no_model,
    no_sleep,
    omnigent_agent,
    trusted_folders,
)

Gone, Fail = omnigent_agent.Gone, omnigent_agent.Fail
REAL = omnigent_agent.Omnigent  # `main` is given a stub in its place
WS = "/there/repo"
LOOP = f"{WS}/docs/agents/loop.md"


class RemoteOg(FakeOmnigent):
    """A FakeOmnigent whose creates are the real ones, with the POSTed bodies kept, and whose
    host ``far`` (called ``other``) serves ``files`` through its live session ``x1``."""

    def __init__(self, files: dict[str, str | Exception]) -> None:
        super().__init__()
        self.files = files
        self.bodies: list[dict] = []
        self.reads: list[str] = []
        self.host_names = {"far": "other"}
        self.others = [{"id": "x1", "host_id": "far", "status": "idle", "updated_at": 1}]
        self.procs = {"far": {"/proc/meminfo": "MemAvailable: 99999999 kB\n", "/proc/loadavg": "0.1 0 0"}}

    def agent_id(self, name: str) -> str:
        return name

    def home(self, name: str) -> dict:
        return {"id": "p1"}

    def read_file(self, sid: str, path: str) -> str:
        if path.startswith("/proc/"):
            return super().read_file(sid, path)
        self.reads.append(path)
        out = self.files.get(path, Gone(f"{path}: not found"))
        if isinstance(out, Exception):
            raise out
        return out

    def create(self, *args, **kw) -> str:  # type: ignore[no-untyped-def]
        REAL.create(self, *args, **kw)  # the real one first: its failure makes no session
        return FakeOmnigent.create(self, *args, **kw)

    def call(self, method: str, path: str, body: object = None) -> dict:
        if (method, path) == ("POST", "/v1/sessions"):
            self.bodies.append(body)  # type: ignore[arg-type]
            return {"id": "sx"}
        return super().call(method, path, body)


def remote(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, files: dict[str, str | Exception]
) -> RemoteOg:
    og = RemoteOg(files)
    og.host = lambda n: {"other": "far"}[n]  # type: ignore[method-assign]
    monkeypatch.setattr(omnigent_agent, "capacity", lambda **_: (True, ""))
    monkeypatch.setattr(omnigent_agent, "parent_id", lambda: "")
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    monkeypatch.delenv("OMNIGENT_PERMISSION_MODE", raising=False)
    monkeypatch.setattr(omnigent_agent.Path, "home", lambda: tmp_path / "home")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "b.md").write_text("do X")
    return og


def argv(host: str = "other", workspace: str = WS) -> list[str]:
    return ["start", "claude", "t", "b.md", f"{WS}/r.md", "--top-level", "--host", host,
            "--workspace", workspace]  # fmt: skip


def launch_args(og: RemoteOg) -> list[str]:
    return og.bodies[-1].get("terminal_launch_args", [])


def test_a_start_on_another_host_reads_that_host_s_loop_md(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    og = remote(monkeypatch, tmp_path, {LOOP: "# Loop\n\nLead autocompact: 150k\n"})
    assert omnigent_agent.main(argv()) == 0
    assert launch_args(og) == ["--autocompact", "150k"]


def test_the_remote_loop_md_is_read_once_for_every_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    og = remote(monkeypatch, tmp_path, {LOOP: "Worker tools: full\nLead autocompact: 150k\n"})
    omnigent_agent.loop_text(WS, og, "far")
    for key in ("Lead autocompact", "Worker tools", "Placement", "Verifier tools"):
        omnigent_agent.project_line(WS, key, og, "far")
    assert og.reads == [LOOP]


def test_a_checkout_there_without_a_loop_md_reads_as_no_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    og = remote(monkeypatch, tmp_path, {WS: ".git/\nREADME.md"})
    assert omnigent_agent.main(argv()) == 0
    assert launch_args(og) == []


@pytest.mark.parametrize(
    "files",
    [
        {LOOP: Fail("GET filesystem: HTTP 502 Bad Gateway")},  # an API error
        {},  # the workspace itself is absent
    ],
)
def test_an_unreadable_remote_loop_md_fails_the_start_before_any_session(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    files: dict[str, str | Exception],
) -> None:
    og = remote(monkeypatch, tmp_path, files)
    assert omnigent_agent.main(argv()) == 1
    err = capsys.readouterr().err
    assert "other" in err and LOOP in err
    assert og.bodies == [] and og.sessions == {}


def test_a_host_with_no_live_session_to_read_through_fails_naming_host_and_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    og = remote(monkeypatch, tmp_path, {LOOP: "Lead autocompact: 150k\n"})
    og.others = []
    assert omnigent_agent.main(argv()) == 1
    err = capsys.readouterr().err
    assert "other" in err and LOOP in err and og.bodies == []


def test_a_local_workspace_still_reads_its_own_loop_md(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import subprocess

    og = remote(monkeypatch, tmp_path, {LOOP: "Lead autocompact: 300k\n"})
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "docs" / "agents").mkdir(parents=True)
    (repo / "docs" / "agents" / "loop.md").write_text("Lead autocompact: 150k\n")
    for host in (None, og.host_id):  # no host, and this host named
        REAL.create(og, "claude", "t", top_level=True, workspace=str(repo), host_id=host)
        assert og.bodies[-1]["terminal_launch_args"] == ["--autocompact", "150k"]
    assert og.reads == []
