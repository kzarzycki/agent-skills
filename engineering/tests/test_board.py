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
