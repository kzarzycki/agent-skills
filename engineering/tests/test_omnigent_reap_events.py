"""``reap`` clears the loop events of a closed PR's branch (#1380), and leaves an open PR's."""

import json
import subprocess
from pathlib import Path

import pytest
import test_omnigent_agent as base
from test_omnigent_agent import no_model, no_sleep  # noqa: F401  (the fixtures apply here by name)
from test_omnigent_keep_pr_worker import og, worker  # noqa: F401  (a fixture, and the helper)

oa = base.omnigent_agent
BRANCH = "loop/x"


def refs(repo: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "for-each-ref", "refs/loop/"], capture_output=True, text=True
    ).stdout


@pytest.fixture
def clone(tmp_path: Path) -> Path:
    """A clone with a ``verifier`` event on ``loop/x``, written here and pushed to its ``origin``."""
    bare, work = tmp_path / "origin.git", tmp_path / "work"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    subprocess.run(["git", "clone", "-q", str(bare), str(work)], check=True, capture_output=True)
    oa.EVENTS.emit("verifier", BRANCH, "ok", cwd=work)
    assert "refs/loop/verifier/loop/x" in refs(work) and "refs/loop/verifier/loop/x" in refs(bare)
    return work


def reap_with(og, clone: Path, monkeypatch, tmp_path: Path, state: str) -> None:  # noqa: F811
    def gh(*args: str) -> str:
        if args[:2] == ("repo", "view"):
            return "o/r\n"
        return json.dumps({"state": state, "headRefName": BRANCH})

    monkeypatch.setattr(oa, "gh", gh)
    sid = worker(og, tmp_path)
    info = og.info
    og.info = lambda s: {**info(s), "workspace": str(clone)}  # type: ignore[method-assign]
    oa.reap(og, [sid])


@pytest.mark.parametrize("state", ["MERGED", "CLOSED"])
def test_reap_of_a_closed_pr_clears_its_branchs_events_here_and_on_origin(
    og,
    clone,
    tmp_path,
    monkeypatch,
    state,  # noqa: F811
) -> None:
    reap_with(og, clone, monkeypatch, tmp_path, state)
    assert refs(clone) == "" and refs(tmp_path / "origin.git") == ""


def test_reap_of_an_open_pr_keeps_its_events(og, clone, tmp_path, monkeypatch) -> None:  # noqa: F811
    reap_with(og, clone, monkeypatch, tmp_path, "OPEN")
    assert "refs/loop/verifier/loop/x" in refs(clone)
