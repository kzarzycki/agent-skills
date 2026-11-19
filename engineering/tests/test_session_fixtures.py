"""The session's template repo is copied, never shared: a test's change to its copy reaches no other test (#1441)."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_approvals import TEMPLATE, committed, git_in


def test_a_copy_is_a_repo_at_the_templates_commit(tmp_path: Path) -> None:
    head = committed(tmp_path / "copy")
    assert git_in(TEMPLATE["repo"], "rev-parse", "HEAD").strip() == head
    assert (tmp_path / "copy" / "app.py").read_text() == "value = 1\n"
    assert git_in(tmp_path / "copy", "status", "--porcelain") == ""


@pytest.mark.parametrize("round", [1, 2])
def test_a_test_changing_its_copy_leaks_nothing_into_the_next(tmp_path: Path, round: int) -> None:
    """Runs twice in one session: the second copy is as clean as the first, whatever the first left behind."""
    repo = tmp_path / "copy"
    head = committed(repo)
    assert not (repo / "leak.txt").exists()
    assert git_in(repo, "rev-list", "--count", "HEAD").strip() == "1"
    (repo / "leak.txt").write_text(f"round {round}")
    (repo / "app.py").write_text("value = 2\n")
    git_in(repo, "add", "-A")
    git_in(repo, "commit", "-qm", "changed")
    assert git_in(repo, "rev-parse", "HEAD").strip() != head
    # the template itself is untouched
    assert git_in(TEMPLATE["repo"], "rev-parse", "HEAD").strip() == head
    assert not (TEMPLATE["repo"] / "leak.txt").exists()
