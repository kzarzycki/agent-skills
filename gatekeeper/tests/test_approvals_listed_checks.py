"""#3023: `loop.required_checks` lists checks that must be green on the head though the forge requires none (a base with
no rules or protection, or a plan with no rules API); `check merge` and `land` hold the merge on a listed check that is
missing or not green, and a policy without the key behaves as before."""

from __future__ import annotations

from typing import Any

import pytest
from approvals_harness import (
    GITHUB_RULE,
    approvals,
    git_in,
    lands,  # noqa: F401  (fixture)
    required,  # noqa: F401  (fixture)
)
from test_approvals import VERDICT, approved, in_project, loop_md, pull

LISTED = loop_md("loop:\n  required_checks:\n    - ci-tests\n    - lint\n")


def merge_lines(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    loop: str | None,
    checks: tuple[tuple[str, str], ...],
) -> tuple[int, list[str]]:
    in_project(monkeypatch)
    monkeypatch.setattr(approvals, "project", lambda: (None, loop))
    pr = pull(reviews=(VERDICT,), checks=checks, files=("app.py",))
    pr["closingIssuesReferences"]["nodes"] = [approved(1, "area:web", "kind:bug")]
    monkeypatch.setattr(approvals, "pull_request", lambda _n: pr)
    code = approvals.main(["check", "merge", "7"])
    return code, [
        line
        for line in capsys.readouterr().out.splitlines()
        if "ci-tests" in line or "lint" in line
    ]


def test_a_listed_check_missing_on_the_head_holds_the_merge_and_the_message_names_it(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], required: list[str]
) -> None:
    code, lines = merge_lines(monkeypatch, capsys, LISTED, (("lint", "SUCCESS"),))
    assert code == approvals.WAITING
    assert lines == ["PR #7: no `ci-tests` on the head commit yet"]


def test_a_listed_check_that_failed_holds_the_merge(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], required: list[str]
) -> None:
    code, lines = merge_lines(
        monkeypatch, capsys, LISTED, (("ci-tests", "FAILURE"), ("lint", "SUCCESS"))
    )
    assert code != 0
    assert lines == ["PR #7: `ci-tests` is FAILURE on the head commit"]


def test_every_listed_check_green_on_the_head_clears_the_merge(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], required: list[str]
) -> None:
    code, lines = merge_lines(
        monkeypatch, capsys, LISTED, (("ci-tests", "SUCCESS"), ("lint", "SUCCESS"))
    )
    assert (code, lines) == (0, [])


def test_without_the_key_a_failed_check_the_forge_does_not_require_holds_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], required: list[str]
) -> None:
    """Today's behaviour: a forge requiring none waits for no check at all."""
    code, lines = merge_lines(monkeypatch, capsys, loop_md(), (("ci-tests", "FAILURE"),))
    assert (code, lines) == (0, [])


def test_the_list_adds_to_the_checks_the_forge_requires(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(approvals, "required_checks", lambda _base: {"check", approvals.APPROVALS})
    pr = pull(checks=(("check", "SUCCESS"), ("lint", "SUCCESS")))
    assert approvals.ran(pr, LISTED) == ["PR #7: no `ci-tests` on the head commit yet"]
    assert approvals.ran(pr, None) == []


def test_a_loop_status_in_the_list_is_never_waited_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(approvals, "required_checks", lambda _base: set())
    loop = loop_md(f"loop:\n  required_checks:\n    - {approvals.APPROVALS}\n")
    assert approvals.listed_checks(loop) == set()
    assert approvals.ran(pull(checks=()), loop) == []


def listed_policy(lands: dict[str, Any], names: str) -> None:
    """The base's loop.md with `loop.required_checks` set (or none), committed to origin's main before a PR opens."""
    work = lands["work"]
    setting = (
        f"loop:\n  required_checks:\n{names}\n" if names else "land:\n  batch_wait_seconds: 0\n"
    )
    (work / "docs" / "agents" / "loop.md").write_text(
        GITHUB_RULE.replace("```yaml\n", f"```yaml\n{setting}", 1)
    )
    git_in(work, "add", "docs")
    git_in(work, "commit", "-q", "-m", "policy")
    git_in(work, "push", "-q", "origin", "HEAD:refs/heads/main")
    git_in(work, "fetch", "-q", "origin")


def only_check(lands: dict[str, Any], number: int, name: str, conclusion: str) -> None:
    nodes = lands["pulls"][number]["commits"]["nodes"][0]["commit"]["statusCheckRollup"]
    nodes["contexts"]["nodes"] = [
        {"__typename": "CheckRun", "name": name, "status": "COMPLETED", "conclusion": conclusion}
    ]


@pytest.fixture
def no_clock_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(approvals.time, "sleep", lambda _s: None)


def test_land_holds_a_pr_whose_listed_check_is_missing_and_merges_it_once_it_is_green(
    lands: dict[str, Any], required: list[str], no_clock_wait: None
) -> None:
    listed_policy(lands, "    - ci-tests")
    lands["open"](7, {"7.txt": "7\n"})
    lands["pulls"][7]["commits"]["nodes"][0]["commit"]["statusCheckRollup"]["contexts"][
        "nodes"
    ] = []
    code, lines = lands["land"]()
    assert (code, lands["merged"]()) == (approvals.WAITING, []), lines
    assert any("no `ci-tests` on the head commit yet" in line for line in lines), lines
    only_check(lands, 7, "ci-tests", "SUCCESS")
    code, lines = lands["land"]()
    assert (code, lands["merged"]()) == (0, ["7"]), lines


def test_land_holds_a_pr_whose_listed_check_failed(
    lands: dict[str, Any], required: list[str], no_clock_wait: None
) -> None:
    listed_policy(lands, "    - ci-tests")
    lands["open"](7, {"7.txt": "7\n"})
    only_check(lands, 7, "ci-tests", "FAILURE")
    code, lines = lands["land"]()
    assert lands["merged"]() == [], (code, lines)
    assert any("`ci-tests` is FAILURE on the head commit" in line for line in lines), lines


def test_land_without_the_key_merges_a_pr_the_forge_requires_no_check_of(
    lands: dict[str, Any], required: list[str], no_clock_wait: None
) -> None:
    listed_policy(lands, "")
    lands["open"](7, {"7.txt": "7\n"})
    only_check(lands, 7, "ci-tests", "FAILURE")
    code, lines = lands["land"]()
    assert (code, lands["merged"]()) == (0, ["7"]), lines


def test_the_key_is_a_list_of_names_and_a_string_is_refused() -> None:
    assert approvals.settings(LISTED)["required_checks"] == ["ci-tests", "lint"]
    with pytest.raises(approvals.Refused, match="required_checks"):
        approvals.settings(loop_md("loop:\n  required_checks: lint\n"))
