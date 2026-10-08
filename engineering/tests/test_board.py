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


def test_a_board_column_the_loop_does_not_name_is_printed_as_is() -> None:
    assert board.column_of(_repo(["P"], [("P", "Backlog")], ("approved:spec",))) == "Backlog"
