"""One running worker or verifier per PR (waste audit, finding 9): `start` refuses a second beside a running one, and
`reap --force` on the one it names stops it, so the start can go on."""

from pathlib import Path

import pytest
import test_omnigent_agent as base
from test_omnigent_agent import no_model, no_sleep  # noqa: F401  (the fixtures apply here by name)

omnigent_agent = base.omnigent_agent
WORKER, VERIFIER = "/x/engineering-loop/worker.md", "/x/engineering-loop/verifier.md"


def listing(og, *sessions: dict) -> None:
    """The server's session list holds ``sessions`` beside whatever ``og`` would answer otherwise."""
    real = og.call

    def call(method: str, path: str, *a):
        if method == "GET" and path.startswith("/v1/sessions?kind=any"):
            return {"data": list(sessions)}
        return real(method, path, *a)

    og.call = call


def twin(role: str, pr: str = "o/r#7", **extra) -> dict:
    return {
        "id": "first",
        "status": "running",
        "labels": {"omni.role": role, "omni.pr": pr},
        **extra,
    }


@pytest.mark.parametrize(
    ("role", "kwargs"),
    [
        (WORKER, {"pr": omnigent_agent.pr_ref("o/r#7")}),
        (VERIFIER, {"about": omnigent_agent.pr_ref("o/r#7")}),
    ],
)
def test_a_second_session_of_a_pr_and_role_is_refused_while_the_first_runs(
    tmp_path: Path, role, kwargs
) -> None:
    og = base.Posting()
    listing(og, twin(Path(role).stem))
    with pytest.raises(
        omnigent_agent.Fail, match=r"PR o/r#7 already has a running .*first.*reap --force first"
    ):
        omnigent_agent.start(og, "claude-cloud", "t", "do X", tmp_path / "r.md", role, 0, **kwargs)
    assert not og.bodies  # no session was made


@pytest.mark.parametrize(
    "other",
    [
        twin("worker", status="idle"),  # a kept --pr worker between rounds: start --pr replaces it
        twin("worker", archived=True),
        twin("verifier"),  # another role
        twin("worker", pr="o/r#8"),  # another PR
    ],
)
def test_a_start_goes_on_beside_no_running_twin(tmp_path: Path, other) -> None:
    og = base.Posting()
    listing(og, other)
    sid, _ = omnigent_agent.start(
        og,
        "claude-cloud",
        "t",
        "do X",
        tmp_path / "r.md",
        WORKER,
        0,
        pr=omnigent_agent.pr_ref("o/r#7"),
    )
    assert sid and og.bodies


def test_reap_force_stops_a_named_running_worker_whose_pr_is_open(monkeypatch) -> None:
    og = base.FakeOmnigent()
    monkeypatch.setattr(omnigent_agent, "pr_hold", lambda repo, pr: "o/r#7 is open")
    og.labels["first"] = {"omni.role": "worker", "omni.pr": "o/r#7"}
    og.sessions["first"] = []
    og.info = lambda sid: {"id": sid, "status": "running", "labels": og.labels[sid]}  # type: ignore[method-assign]
    lines, failed = omnigent_agent.reap(og, ["first"], force=True)
    assert not failed and og.interrupted == ["first"] and og.archived == ["first"]
    assert "archived (stopped)" in lines[0]


def test_reap_force_keeps_an_idle_kept_worker_and_reap_alone_a_running_one(monkeypatch) -> None:
    og = base.FakeOmnigent()
    monkeypatch.setattr(omnigent_agent, "pr_hold", lambda repo, pr: "o/r#7 is open")
    og.labels["first"] = {"omni.role": "worker", "omni.pr": "o/r#7"}
    og.sessions["first"] = []
    status = {"first": "idle"}
    og.info = lambda sid: {"id": sid, "status": status[sid], "labels": og.labels[sid]}  # type: ignore[method-assign]
    assert "kept (o/r#7 is open)" in omnigent_agent.reap(og, ["first"], force=True)[0][0]
    status["first"] = "running"
    assert "kept" in omnigent_agent.reap(og, ["first"])[0][0]
    assert og.archived == [] and og.interrupted == []
