"""approvals.py: a PR's risk as the board's single-select `Risk` field beside the `risk:high` label (#929).

flag() sets the field to `High` when it adds the label, adds the label when the field already says `High`, never
takes the label off for a lower field, and sets the field to the verifier's `Risk:` word. Board access is best
effort: no board or no `project` scope is a line, never a failure. The board answers through board.py's GraphQL
calls, stubbed by the `board_risks` fixture.
"""

from __future__ import annotations

from typing import Any

import pytest
from approvals_harness import (
    HELD,
    added,  # noqa: F401
    approvals,
    approved,
    assigned,  # noqa: F401
    attached,  # noqa: F401
    board_risks,  # noqa: F401
    gating,  # noqa: F401
    graphql_answers,  # noqa: F401
    hub,  # noqa: F401
    issue,
    judged_pr,
    judging,
    others_open,  # noqa: F401
    pull,
    pushed,  # noqa: F401
    refs,  # noqa: F401
    required,  # noqa: F401
)


@pytest.fixture
def comments(monkeypatch: pytest.MonkeyPatch) -> list[tuple[int, str]]:
    """Every comment approvals.py posts, instead of posting it."""
    sent: list[tuple[int, str]] = []
    monkeypatch.setattr(approvals, "comment", lambda number, body: sent.append((number, body)))
    return sent


def test_adding_risk_high_sets_the_board_field_to_high(
    board_risks: dict[str, Any],
    added: list[tuple[int, str, bool]],
    comments: list[tuple[int, str]],
) -> None:
    board_risks["values"][7] = "Low"
    assert approvals.flag(pull(), [approved(1), issue(3, "risk:high")], None) == []
    assert added == [(7, "risk:high", True)]
    assert board_risks["set"] == [(7, "High")]


def test_a_pr_off_the_board_is_added_with_the_field_at_high(
    board_risks: dict[str, Any],
    added: list[tuple[int, str, bool]],
    comments: list[tuple[int, str]],
) -> None:
    assert approvals.flag(pull(), [issue(3, "risk:high")], None) == []
    assert board_risks["set"] == [(7, "High")]


def test_a_field_at_high_adds_the_label_names_the_board_and_holds_the_merge(
    board_risks: dict[str, Any],
    added: list[tuple[int, str, bool]],
    comments: list[tuple[int, str]],
) -> None:
    board_risks["values"][7] = "High"
    pr = pull(labels=("risk:low",))
    assert approvals.risk(pr, [approved(1)], None) is None
    assert approvals.flag(pr, [approved(1)], None) == []
    assert added == [(7, "risk:high", True), (7, "risk:low", False)]
    assert comments == [(7, "`risk:high` added, since the board's `Risk` field says `High`.\n")]
    # the checks after flag() read the label it added, so the merge holds in this run too
    assert approvals.risk(pr, [approved(1)], None) == "`risk:high` is on PR #7"
    assert board_risks["set"] == []


def test_a_field_at_high_holds_check_merge_for_the_owner(
    gating: tuple[dict[str, Any], list[tuple[int, str]]],
    board_risks: dict[str, Any],
    added: list[tuple[int, str, bool]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    state, sent = gating
    state["pull"] = judged_pr(judging("low — a flag on two test commands"))
    board_risks["values"][7] = "High"
    assert approvals.main(["check", "merge", "7"]) == approvals.WAITING
    assert capsys.readouterr().out.splitlines() == [HELD + "`risk:high` is on PR #7"]
    assert added == [(7, "risk:high", True)]
    assert [body for _, body in sent] == [
        "`risk:high` added, since the board's `Risk` field says `High`.\n"
    ]


@pytest.mark.parametrize("field", ["Low", "Medium", None])
def test_a_lower_field_leaves_an_existing_risk_high_and_rises_to_it(
    board_risks: dict[str, Any],
    added: list[tuple[int, str, bool]],
    comments: list[tuple[int, str]],
    field: str | None,
) -> None:
    if field:
        board_risks["values"][7] = field
    assert approvals.flag(pull(labels=("risk:high",)), [approved(1)], None) == []
    assert (added, comments) == ([], [])
    assert board_risks["set"] == [(7, "High")]


def test_a_field_already_at_high_beside_the_label_is_not_set_again(
    board_risks: dict[str, Any], added: list[tuple[int, str, bool]]
) -> None:
    board_risks["values"][7] = "High"
    assert approvals.flag(pull(labels=("risk:high",)), [approved(1)], None) == []
    assert (added, board_risks["set"]) == ([], [])


@pytest.mark.parametrize(
    ("said", "option"),
    [
        ("low — a doc fix", "Low"),
        ("high — it narrows the gate", "High"),
        ("medium — unsure", "High"),
    ],
    ids=["low", "high", "another-word"],
)
def test_the_verifiers_risk_line_sets_the_field(
    gating: tuple[dict[str, Any], list[tuple[int, str]]],
    board_risks: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
    said: str,
    option: str,
) -> None:
    state, _ = gating
    state["pull"] = judged_pr(judging(said))
    approvals.main(["check", "merge", "7"])
    assert board_risks["set"] == [(7, option)]
    assert "board" not in capsys.readouterr().out


def test_without_a_verifier_pass_on_the_head_a_low_pr_leaves_the_field(
    board_risks: dict[str, Any],
) -> None:
    assert approvals.flag(pull(), [approved(1)], None) == []
    assert board_risks["set"] == []


@pytest.mark.parametrize(
    ("setup", "why"),
    [
        ({"linked": False}, "no project board is linked to this repo"),
        (
            {"refused": "gh: Your token has not been granted the required scopes: project\n"},
            "gh: Your token has not been granted the required scopes: project",
        ),
    ],
    ids=["no-board", "no-scope"],
)
def test_without_a_board_or_its_scope_the_label_is_added_with_one_line_about_the_board(
    board_risks: dict[str, Any],
    added: list[tuple[int, str, bool]],
    comments: list[tuple[int, str]],
    setup: dict[str, Any],
    why: str,
) -> None:
    board_risks.update(setup)
    assert approvals.flag(pull(), [issue(3, "risk:high")], None) == [
        f"PR #7: could not set the board's `Risk` field to `High` ({why}); the `risk:high` label alone shows the risk"
    ]
    assert added == [(7, "risk:high", True)]
    assert [number for number, _ in comments] == [7]


def test_a_board_without_the_risk_field_is_a_line(
    board_risks: dict[str, Any],
    added: list[tuple[int, str, bool]],
    comments: list[tuple[int, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real = approvals.board()._graphql

    def fieldless(query: str, **values: Any) -> Any:
        found = real(query, **values)
        if query == approvals.board().LOOKUP:
            found["repository"]["projectsV2"]["nodes"][0]["field"] = None
        return found

    monkeypatch.setattr(approvals.board(), "_graphql", fieldless)
    assert approvals.flag(pull(), [issue(3, "risk:high")], None) == [
        (
            "PR #7: could not set the board's `Risk` field to `High` (the board has no Risk field); the `risk:high`"
            " label alone shows the risk"
        )
    ]
    assert added == [(7, "risk:high", True)]


def test_a_refused_set_is_a_line_not_a_failure(
    board_risks: dict[str, Any],
    added: list[tuple[int, str, bool]],
    comments: list[tuple[int, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refused(*_args: Any, **_kwargs: Any) -> None:
        raise approvals.subprocess.CalledProcessError(1, "gh", stderr="HTTP 502\n")

    monkeypatch.setattr(approvals.board(), "set_field", refused)
    assert approvals.flag(pull(), [issue(3, "risk:high")], None) == [
        "PR #7: could not set the board's `Risk` field to `High` (HTTP 502); the `risk:high` label alone shows the risk"
    ]


def test_a_run_refused_graphql_reads_no_board(
    board_risks: dict[str, Any],
    added: list[tuple[int, str, bool]],
    comments: list[tuple[int, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    board_risks["values"][7] = "High"
    monkeypatch.setattr(approvals, "_rest_only", True)
    assert approvals.flag(pull(), [approved(1)], None) == []
    assert (added, board_risks["set"]) == ([], [])
