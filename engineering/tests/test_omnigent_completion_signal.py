"""`wait-for --pr N --until gate|verdict`: a lead waits on the signal a gate or verifier run posts, not on a worker's
turn (#1002). GitHub is faked at its REST paths, the only reads these waits make."""

from __future__ import annotations

import json
from typing import Any

import pytest
from test_omnigent_agent import omnigent_agent

HEAD = "a" * 40
OLD = "b" * 40
TREE = "c" * 40
URL = "https://github.com/o/r/pull/7#issuecomment-{}"


def rest(
    monkeypatch: pytest.MonkeyPatch,
    *,
    refs: list[dict[str, Any]] | None = None,
    statuses: list[dict[str, Any]] | None = None,
    comments: list[dict[str, Any]] | None = None,
    reviews: list[dict[str, Any]] | None = None,
) -> list[tuple[str, ...]]:
    """GitHub's REST answers for PR 7 at HEAD, its tree TREE, committed at 10:00; the calls made, in order."""
    calls: list[tuple[str, ...]] = []
    paged = {
        "repos/{owner}/{repo}/issues/7/comments": comments or [],
        "repos/{owner}/{repo}/pulls/7/reviews": reviews or [],
    }
    single = {
        "repos/{owner}/{repo}/pulls/7": {"head": {"sha": HEAD}},
        f"repos/{{owner}}/{{repo}}/git/commits/{HEAD}": {
            "tree": {"sha": TREE},
            "committer": {"date": "2026-01-01T10:00:00Z"},
        },
        f"repos/{{owner}}/{{repo}}/git/matching-refs/heads/loop-gate/{TREE}-": refs or [],
        f"repos/{{owner}}/{{repo}}/commits/{HEAD}/statuses?per_page=100": statuses or [],
    }

    def gh(*args: str, timeout: float = 0) -> str:
        calls.append(args)
        assert args[0] == "api" and timeout > 0
        if "--paginate" in args:
            return "".join(json.dumps(item) + "\n" for item in paged[args[2]])
        return json.dumps(single[args[1]])

    monkeypatch.setattr(omnigent_agent, "gh", gh)
    monkeypatch.setattr(omnigent_agent, "WAIT_FOR_PR_EVERY", 0.01)
    return calls


def wait(until: str, budget: str = "30") -> int:
    return omnigent_agent.main(["wait-for", "--pr", "7", "--until", until, "--budget", budget])


def status(state: str, description: str = "d", context: str = "gate") -> dict[str, Any]:
    return {"context": context, "state": state, "description": description}


def said(body: str, at: str = "2026-01-01T11:00:00Z", n: int = 1) -> dict[str, Any]:
    return {"body": body, "created_at": at, "html_url": URL.format(n)}


def report(head: str, satisfied: str) -> str:
    return f"## Correctness\n\nHead: {head}\nVERDICT: 0 blocker, 0 major, 0 minor\nSATISFIED: {satisfied}\n"


def test_gate_passes_on_a_record_branch_for_the_heads_tree(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    ref = f"refs/heads/loop-gate/{TREE}-k"
    calls = rest(monkeypatch, refs=[{"ref": ref}], statuses=[status("failure")])
    assert wait("gate") == 0
    assert capsys.readouterr().out == f"PR #7 head {HEAD}: passed, record branch {ref}\n"
    assert all("--paginate" not in call for call in calls)  # REST alone, no checkout read


def test_gate_passes_on_a_green_gate_status(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rest(monkeypatch, statuses=[status("success", "Tree t on h: c"), status("failure")])
    assert wait("gate") == 0
    assert capsys.readouterr().out == f"PR #7 head {HEAD}: passed, gate status: Tree t on h: c\n"


@pytest.mark.parametrize("state", ["failure", "error"])
def test_gate_fails_on_a_failed_gate_status(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], state: str
) -> None:
    rest(
        monkeypatch,
        statuses=[status("success", context="ci"), status("pending"), status(state, "Failed: x")],
    )
    assert wait("gate") == 1
    assert capsys.readouterr().out == f"PR #7 head {HEAD}: gate {state}: Failed: x\n"


def test_gate_runs_to_the_budget_while_the_head_has_neither(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rest(monkeypatch, statuses=[status("success", context="ci"), status("pending")])
    assert wait("gate", "0.2") == 6
    assert capsys.readouterr().out == "still running\n"


def test_verdict_settles_on_a_satisfied_report_for_the_head(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rest(monkeypatch, comments=[said("unrelated", n=1), said(report(HEAD, "yes"), n=2)])
    assert wait("verdict") == 0
    assert capsys.readouterr().out == f"PR #7 head {HEAD}: SATISFIED: yes: {URL.format(2)}\n"


def test_verdict_reads_a_review_too_and_fails_on_an_unsatisfied_one(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    review = {
        "body": report(HEAD, "no"),
        "submitted_at": "2026-01-01T12:00:00Z",
        "html_url": "https://github.com/o/r/pull/7#pullrequestreview-9",
    }
    rest(monkeypatch, comments=[said(report(HEAD, "yes"))], reviews=[review])
    assert wait("verdict") == 1  # the newest word on the head is the review's
    assert capsys.readouterr().out == f"PR #7 head {HEAD}: SATISFIED: no: {review['html_url']}\n"


def test_verdict_ignores_a_report_naming_an_older_head(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rest(monkeypatch, comments=[said(report(OLD, "yes"))])
    assert wait("verdict", "0.2") == 6
    assert capsys.readouterr().out == "still running\n"


def test_verdict_fails_on_a_question_posted_after_the_heads_commit(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rest(monkeypatch, comments=[said("## Verifier question\n\nWhich base?", n=3)])
    assert wait("verdict") == 1
    out = capsys.readouterr().out
    assert out == f"PR #7 head {HEAD}: the verifier asked a question: {URL.format(3)}\n"


def test_verdict_ignores_a_question_older_than_the_head(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rest(monkeypatch, comments=[said("## Verifier question\n\nx", at="2026-01-01T09:00:00Z")])
    assert wait("verdict", "0.2") == 6
    assert capsys.readouterr().out == "still running\n"
