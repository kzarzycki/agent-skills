"""omnigent_agent.py reuse: a merged --pr worker takes the next story when its context is under the
project's threshold and the repo matches; a reused worker survives reap --merged (#1037). The
Omnigent HTTP API is faked at ``call``; gh answers PR states."""

import json
import subprocess
from pathlib import Path

import pytest
import test_omnigent_agent as base
from test_omnigent_agent import no_model, no_sleep  # noqa: F401  (the fixtures apply here by name)

omnigent_agent = base.omnigent_agent


class Server(omnigent_agent.Omnigent):
    """The real client with ``call`` answering from dicts, as the HTTP API does."""

    def __init__(self, tokens: object, label: str = "o/r#7") -> None:
        self.base, self.host_id, self._token, self.loops = "http://x", "h", "t", {}
        self.record = {
            "id": "s1",
            "status": "idle",
            "labels": {"omni.pr": label},
            "workspace": "/w",
        }
        if tokens is not None:
            self.record["last_total_tokens"] = tokens
        self.archived: list[str] = []
        self.items_: list[dict] = []

    def call(self, method: str, path: str, body: object = None, **_: object) -> dict:
        if (method, path) == ("GET", "/v1/sessions?kind=any&limit=1000"):
            return {"data": [self.record] if not self.record.get("archived") else []}
        if method == "PATCH" and path == "/v1/sessions/s1":
            patch = dict(body)  # type: ignore[arg-type]
            if patch.get("archived"):
                self.record["archived"] = True
                self.archived.append("s1")
            if "labels" in patch:
                self.record["labels"] = {**self.record["labels"], **patch["labels"]}
            return {}
        if method == "GET" and path == "/v1/sessions/s1":
            return dict(self.record)
        raise AssertionError(f"unfaked {method} {path}")


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def loop(project: Path, line: str) -> None:
    (project / "docs" / "agents").mkdir(parents=True, exist_ok=True)
    (project / "docs" / "agents" / "loop.md").write_text(f"# Loop\n{line}\n")


def prs(monkeypatch: pytest.MonkeyPatch, **states: str) -> None:
    """gh: ``pr view N --repo X`` answers the state ``states['pr<N>']``."""

    def gh(*args: str, **_: object) -> str:
        return json.dumps({"state": states[f"pr{args[2]}"]})

    monkeypatch.setattr(omnigent_agent, "gh", gh)


def decide(og: Server, project: Path, repo: str = "o/r") -> str:
    verdict, why = omnigent_agent.reuse_decision(og, "s1", repo, str(project))
    return f"{verdict}: {why}"


@pytest.mark.parametrize(
    ("line", "tokens", "repo", "state", "answer"),
    [
        ("Reuse worker context: 120k", 80_000, "o/r", "MERGED", "reuse"),
        ("Reuse worker context: 120k", 120_000, "o/r", "MERGED", "start"),  # at the threshold
        ("Reuse worker context: 120k", 300_000, "o/r", "MERGED", "start"),  # over it
        ("Reuse worker context: 120k", 80_000, "o/other", "MERGED", "start"),  # another repo
        ("Reuse worker context: 120k", 80_000, "o/r", "OPEN", "start"),  # not landed
        ("Reuse worker context: 120k", 80_000, "o/r", "CLOSED", "start"),  # closed, not merged
        ("Reuse worker context: 120k", None, "o/r", "MERGED", "start"),  # unreadable
        ("Reuse worker context: 120k", "80000", "o/r", "MERGED", "start"),  # not a number
        ("", 80_000, "o/r", "MERGED", "start"),  # no setting: no reuse
    ],
)
def test_the_helper_reuses_only_under_the_threshold_in_the_same_repo(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    line: str,
    tokens: object,
    repo: str,
    state: str,
    answer: str,
) -> None:
    loop(project, line)
    prs(monkeypatch, pr7=state)
    assert decide(Server(tokens), project, repo).split(":")[0] == answer


def test_a_bad_threshold_fails(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    loop(project, "Reuse worker context: lots")
    prs(monkeypatch, pr7="MERGED")
    with pytest.raises(omnigent_agent.Fail, match="Reuse worker context: lots"):
        decide(Server(80_000), project)


def test_the_subcommand_prints_the_verdict_and_its_reason(
    project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    loop(project, "Reuse worker context: 120k")
    prs(monkeypatch, pr7="MERGED")
    og = Server(80_000)
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    monkeypatch.setattr(omnigent_agent, "pack_behind", lambda _: None)
    assert omnigent_agent.main(["reuse", "s1", "--repo", "o/r"]) == 0
    assert capsys.readouterr().out.startswith("reuse: o/r#7 merged, same repo")


def test_reap_merged_archives_the_worker_of_a_landed_pr_but_not_a_reused_one(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prs(monkeypatch, pr7="MERGED", pr9="OPEN")
    og = Server(80_000)
    og.label("s1", {"omni.pr": "o/r#9"})  # what `send --pr 9` does to a reused worker
    lines, failed = omnigent_agent.reap(og, [], merged=True)
    assert og.archived == [] and not failed and "kept (o/r#9 is open)" in lines[0]
    prs(monkeypatch, pr7="MERGED", pr9="MERGED")  # its new PR lands: reaped as usual
    omnigent_agent.reap(og, [], merged=True)
    assert og.archived == ["s1"]


def test_send_with_a_new_pr_relabels_the_worker_before_the_message_goes(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prs(monkeypatch, pr7="MERGED", pr9="OPEN")
    og = Server(80_000)
    sent: list[dict[str, str]] = []
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    monkeypatch.setattr(omnigent_agent, "pack_behind", lambda _: None)

    def send(*_: object, **__: object) -> None:
        sent.append(dict(og.record["labels"]))  # type: ignore[arg-type]
        raise omnigent_agent.Fail("stop here")

    monkeypatch.setattr(omnigent_agent, "send", send)
    (project / "brief.md").write_text("next")
    (project / "tmp").mkdir()
    code = omnigent_agent.main(["send", "s1", "brief.md", "tmp/r.md", "--pr", "o/r#9"])
    assert code == 1 and sent == [{"omni.pr": "o/r#9"}]
