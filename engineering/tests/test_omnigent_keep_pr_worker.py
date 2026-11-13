"""omnigent_agent.py: a --pr worker is kept by default and finished when its PR is done (#943)."""

import json
from pathlib import Path

import pytest
import test_omnigent_agent as base  # the faked server and gh

omnigent_agent = base.omnigent_agent
LINK = "https://github.com/o/r/pull/7#issuecomment-42"


def worker(og: base.FakeOmnigent, tmp_path: Path, pr: int = 7) -> str:
    sid, _ = omnigent_agent.start(
        og, "claude-cloud", f"t{pr}", "do X", tmp_path / "r", None, 0, pr=pr
    )
    return sid


def pulls(monkeypatch: pytest.MonkeyPatch, states: dict[int, dict]) -> None:
    """gh faked: `pr view N` answers states[N] (state, headRefOid, reviews)."""

    def gh(*args: str) -> str:
        assert args[:2] == ("pr", "view"), args
        return json.dumps(states[int(args[2])])

    monkeypatch.setattr(omnigent_agent, "gh", gh)


def review(head: str, verdict: str) -> dict:
    body = f"Verifier (claude), pass 1\nSATISFIED: {verdict}\n"
    return {"body": body, "commit": {"oid": head}}


@pytest.fixture
def og(monkeypatch: pytest.MonkeyPatch) -> base.FakeOmnigent:
    fake = base.FakeOmnigent(reply=LINK)
    fake.others = []
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: fake)
    return fake


def listed(og: base.FakeOmnigent) -> None:
    """The server's session list carries each worker's labels."""
    call = og.call
    og.call = lambda m, p, b=None: (  # type: ignore[method-assign]
        {"data": [{"id": s, "labels": l} for s, l in og.labels.items() if s not in og.archived]}
        if p.startswith("/v1/sessions?kind=any&limit=1000")
        else call(m, p, b)
    )


def test_wait_with_pr_makes_no_archive_call_and_no_keep_makes_one(
    og: base.FakeOmnigent, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base.fake_gh(monkeypatch, {"42": base.on_pr(7, "done")})
    monkeypatch.chdir(tmp_path)
    for title, flags, archived in (
        ("a", [], []),
        ("b", ["--no-keep"], ["s1"]),
        ("c", ["--keep"], ["s1"]),
    ):
        sid = worker(og, tmp_path, 7)
        assert omnigent_agent.main(["wait", sid, f"{title}.md", "--pr", "7", *flags]) == 0
        assert og.archived == archived
    assert og.labels["s0"] == {"omni.pr": "7"}


def test_reap_keeps_an_open_pr_worker_until_a_verdict_on_its_head_is_satisfied(
    og: base.FakeOmnigent, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sid = worker(og, tmp_path)
    state = {"state": "OPEN", "headRefOid": "h2", "reviews": [review("h1", "yes")]}
    pulls(monkeypatch, {7: state})
    lines, failed = omnigent_agent.reap(og, [sid])
    assert not failed and og.archived == []
    assert "kept (PR #7 is open with no satisfied verdict on its head)" in lines[0]
    state["reviews"] = [review("h2", "yes"), review("h2", "no")]  # the newest one decides
    omnigent_agent.reap(og, [sid])
    assert og.archived == []
    state["reviews"] = [review("h2", "no"), review("h2", "yes")]
    assert omnigent_agent.reap(og, [sid])[0][0].endswith("archived (idle)")
    assert og.archived == [sid]


@pytest.mark.parametrize("state", ["MERGED", "CLOSED"])
def test_reap_finishes_a_worker_whose_pr_is_done(
    og: base.FakeOmnigent, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    sid = worker(og, tmp_path)
    pulls(monkeypatch, {7: {"state": state, "headRefOid": "h", "reviews": []}})
    omnigent_agent.reap(og, [sid])
    assert og.archived == [sid]


def test_reap_merged_archives_kept_workers_of_done_prs_and_leaves_open_ones(
    og: base.FakeOmnigent, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    done, closed, open_ = (worker(og, tmp_path, n) for n in (7, 8, 9))
    listed(og)
    pulls(
        monkeypatch,
        {
            7: {"state": "MERGED", "headRefOid": "h", "reviews": []},
            8: {"state": "CLOSED", "headRefOid": "h", "reviews": []},
            9: {"state": "OPEN", "headRefOid": "h", "reviews": [review("h", "yes")]},
        },
    )
    lines, failed = omnigent_agent.reap(og, [], merged=True)
    assert not failed and og.archived == [done, closed]  # an open PR's stays, even satisfied
    assert any(line.startswith(open_) and "kept (PR #9 is open)" in line for line in lines)
    assert omnigent_agent.main(["reap", "--merged", "--pr", "9"]) == 0
    assert og.archived == [done, closed]


def test_reap_merged_with_a_pr_takes_only_that_prs_workers(
    og: base.FakeOmnigent, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first, second = worker(og, tmp_path, 7), worker(og, tmp_path, 8)
    listed(og)
    merged = {"state": "MERGED", "headRefOid": "h", "reviews": []}
    pulls(monkeypatch, {7: merged, 8: merged})
    omnigent_agent.reap(og, [], merged=True, pr=8)
    assert og.archived == [second] and first not in og.archived


def test_reap_without_a_target_or_merged_is_refused(og: base.FakeOmnigent) -> None:
    assert omnigent_agent.main(["reap"]) != 0
