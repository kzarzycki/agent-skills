"""scripts/board.py: a column name resolves to the board's ids, and an unknown one names the valid columns."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "engineering-loop" / "scripts"
sys.path.insert(
    0, str(SCRIPTS)
)  # as when run: board.py reads the label names from approvals.py beside it
SPEC = importlib.util.spec_from_file_location("board", SCRIPTS / "board.py")
assert SPEC and SPEC.loader
board = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(board)

PROJECT = {
    "id": "P",
    "field": {
        "id": "F",
        "options": [{"id": "o1", "name": "Intent"}, {"id": "o2", "name": "Build"}],
    },
}


def test_a_column_resolves_to_project_field_and_option() -> None:
    assert board.target([PROJECT], "Build") == ("P", "F", "o2")


def test_an_unknown_column_names_the_valid_ones() -> None:
    with pytest.raises(ValueError, match="no column 'Review': the board has Intent, Build"):
        board.target([PROJECT], "Review")


def test_an_all_digit_id_stays_a_string() -> None:
    assert board.fields(owner="{owner}", issue=580, option="98236657") == [
        "-F",
        "owner={owner}",
        "-F",
        "issue=580",
        "-f",
        "option=98236657",
    ]


def test_a_repo_without_a_board_or_a_status_field_is_refused() -> None:
    with pytest.raises(ValueError, match="no project board is linked"):
        board.target([], "Build")
    with pytest.raises(ValueError, match="no Status field"):
        board.target([{"id": "P", "field": None}], "Build")


def _repo(
    boards: list[str], items: list[tuple[str, str | None]], labels: tuple[str, ...] = ()
) -> dict:
    return {
        "projectsV2": {"nodes": [{"id": b} for b in boards]},
        "issue": {
            "labels": {"nodes": [{"name": name} for name in labels]},
            "projectItems": {
                "nodes": [
                    {"project": {"id": p}, "fieldValueByName": None if s is None else {"name": s}}
                    for p, s in items
                ]
            },
        },
    }


def test_column_reads_the_issues_status_on_the_repos_board() -> None:
    assert board.column_of(_repo(["P"], [("Q", "Build"), ("P", "Ready")])) == "Ready"


def test_without_a_board_off_it_or_without_a_status_the_labels_give_the_column() -> None:
    assert board.column_of(_repo([], [("P", "Ready")])) == "Intent"
    assert board.column_of(_repo(["P"], [("Q", "Ready")], ("needs-owner",))) == "Needs owner"
    assert board.column_of(_repo(["P"], [("P", None)], ("approved:spec", "size:S"))) == "Ready"


def test_an_approved_spec_is_ready_whatever_earlier_column_the_board_shows() -> None:
    assert board.column_of(_repo(["P"], [("P", "Intent")], ("approved:spec", "size:S"))) == "Ready"
    assert board.column_of(_repo(["P"], [("P", "Build")], ("approved:spec",))) == "Build"


def test_the_owner_moving_a_parked_spec_to_ready_shows() -> None:
    assert board.column_of(_repo(["P"], [("P", "Ready")], ("needs-owner",))) == "Ready"


def test_a_landed_change_waiting_for_its_signoff_reads_after_verify() -> None:
    assert board.column_of(_repo(["P"], [("P", "Sign-off")], ("approved:spec",))) == "Sign-off"
    assert (
        board.COLUMNS.index("Verify")
        < board.COLUMNS.index("Sign-off")
        < board.COLUMNS.index("Done")
    )


def test_a_board_column_the_loop_does_not_name_is_printed_as_is() -> None:
    assert board.column_of(_repo(["P"], [("P", "Backlog")], ("approved:spec",))) == "Backlog"


# --- the tracker file's mapping of loop columns to the board's ---

MAPPED = """# Issue tracker

## Settings

```yaml
board:
  Build: In progress
  Verify: In progress
  Sign-off: In review

components:
  web: ""
```
"""


def test_the_tracker_maps_loop_columns_to_board_columns() -> None:
    assert board.mapping(MAPPED) == {
        "Build": "In progress",
        "Verify": "In progress",
        "Sign-off": "In review",
    }
    assert board.mapping(None) == board.mapping("## Settings\n\n```yaml\n```\n") == {}


def test_column_reads_a_shared_board_column_as_its_earliest_loop_column() -> None:
    mapped = board.mapping(MAPPED)
    assert board.column_of(_repo(["P"], [("P", "In progress")]), mapped) == "Build"
    # the labels still win over an earlier column, a mapped `Sign-off` reads back, and an unmapped status is printed as is
    assert board.column_of(_repo(["P"], [("P", "Intent")], ("approved:spec",)), mapped) == "Ready"
    assert board.column_of(_repo(["P"], [("P", "In review")]), mapped) == "Sign-off"
    assert board.column_of(_repo(["P"], [("P", "Backlog")]), mapped) == "Backlog"
    # without a mapping nothing changes
    assert board.column_of(_repo(["P"], [("P", "Verify")])) == "Verify"


def test_a_move_takes_the_loops_name_and_sets_the_mapped_column(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "docs" / "agents").mkdir(parents=True)
    (tmp_path / "docs" / "agents" / "issue-tracker.md").write_text(MAPPED)
    monkeypatch.setattr(board, "toplevel", lambda: tmp_path)
    moved: list[tuple[int, str]] = []
    monkeypatch.setattr(board, "move", lambda issue, column: moved.append((issue, column)))
    assert [board.main(["5", name]) for name in ("Verify", "Sign-off", "Ready", "Backlog")] == [
        0
    ] * 4
    assert moved == [(5, "In progress"), (5, "In review"), (5, "Ready"), (5, "Backlog")]


# --- `field`: another single-select field of an issue's or PR's item, such as the PR's `Risk` ---

RISKY = {
    "id": "P",
    "field": {
        "id": "R",
        "options": [
            {"id": "r1", "name": "Low"},
            {"id": "r2", "name": "Medium"},
            {"id": "r3", "name": "High"},
        ],
    },
}


def _item(on: list[tuple[str, str | None]], boards: list[dict] | None = None) -> dict:
    return {
        "projectsV2": {"nodes": [RISKY] if boards is None else boards},
        "issueOrPullRequest": {
            "id": "PR_n",
            "projectItems": {
                "nodes": [
                    {"project": {"id": p}, "fieldValueByName": None if s is None else {"name": s}}
                    for p, s in on
                ]
            },
        },
    }


def test_an_unknown_option_of_another_field_names_the_field_and_its_options() -> None:
    assert board.target([RISKY], "High", "Risk") == ("P", "R", "r3")
    with pytest.raises(ValueError, match="no Risk option 'Huge': the board has Low, Medium, High"):
        board.target([RISKY], "Huge", "Risk")
    with pytest.raises(ValueError, match="no Risk field"):
        board.target([{"id": "P", "field": None}], "High", "Risk")


def test_value_reads_the_items_option_on_the_repos_board() -> None:
    assert board.value(_item([("Q", "Low"), ("P", "High")]), "Risk") == "High"
    assert board.value(_item([("Q", "Low")]), "Risk") is None
    assert board.value(_item([("P", None)]), "Risk") is None
    with pytest.raises(ValueError, match="no project board is linked"):
        board.value(_item([], boards=[]), "Risk")
    with pytest.raises(ValueError, match="the board has no Risk field"):
        board.value(_item([], boards=[{"id": "P", "field": None}]), "Risk")


def test_set_field_looks_up_the_pr_adds_it_to_the_board_and_sets_the_option(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict]] = []

    def graphql(query: str, **values: object) -> dict:
        calls.append((query, values))
        if query == board.LOOKUP:
            return {"repository": _item([])}
        if query == board.ADD:
            return {"addProjectV2ItemById": {"item": {"id": "I"}}}
        return {}

    monkeypatch.setattr(board, "_graphql", graphql)
    board.set_field(12, "Risk", "High")
    assert calls == [
        (board.LOOKUP, {"owner": "{owner}", "name": "{repo}", "issue": 12, "field": "Risk"}),
        (board.ADD, {"project": "P", "issue": "PR_n"}),
        (board.SET, {"project": "P", "item": "I", "field": "R", "option": "r3"}),
    ]
    # the lookup reads an issue or a PR alike, the field named by the caller
    assert "issueOrPullRequest(number: $issue)" in board.LOOKUP
    assert "field(name: $field)" in board.LOOKUP


def test_set_field_with_a_lookup_already_made_reads_the_board_no_second_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def graphql(query: str, **values: object) -> dict:
        calls.append(query)
        return {"addProjectV2ItemById": {"item": {"id": "I"}}} if query == board.ADD else {}

    monkeypatch.setattr(board, "_graphql", graphql)
    board.set_field(12, "Risk", "Low", _item([]))
    assert calls == [board.ADD, board.SET]


def test_a_move_sets_the_status_field(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple] = []
    monkeypatch.setattr(board, "set_field", lambda *args: calls.append(args))
    board.move(5, "Build")
    assert calls == [(5, "Status", "Build")]


def test_the_field_verb_sets_the_option_and_a_refusal_exits_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[tuple] = []
    monkeypatch.setattr(board, "one_repo", lambda: None)
    monkeypatch.setattr(board, "set_field", lambda *args: calls.append(args))
    assert board.main(["field", "12", "Risk", "High"]) == 0
    assert calls == [(12, "Risk", "High")]

    def refused(*_args: object) -> None:
        raise ValueError("no project board is linked to this repo")

    monkeypatch.setattr(board, "set_field", refused)
    assert board.main(["field", "12", "Risk", "High"]) == 1
    assert "no project board is linked" in capsys.readouterr().err
    assert board.main(["field", "12", "Risk"]) == 2
