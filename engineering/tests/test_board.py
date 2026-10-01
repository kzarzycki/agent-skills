"""scripts/board.py: a column name resolves to the board's ids, and an unknown one names the valid columns."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "board",
    Path(__file__).resolve().parents[1] / "skills" / "engineering-loop" / "scripts" / "board.py",
)
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
