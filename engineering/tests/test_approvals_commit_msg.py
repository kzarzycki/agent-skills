"""approvals.py: `commit-msg <file>`, run as git's commit-msg hook, drops every `Claude-Session:` line from a
commit's message as land drops it from the squash body, so a cloud session's branch commits carry no link (#965)."""

from __future__ import annotations

import sys
from pathlib import Path

from approvals_harness import (
    SCRIPTS,
    approvals,
    git_in,
)

CO_AUTHOR = "Co-Authored-By: Claude <noreply@anthropic.com>"
LINKED = f"Fix the parser\n\nKeep the last field.\n\n{CO_AUTHOR}\nClaude-Session: https://example.com/s\n"


def test_the_hook_leaves_the_co_author_line_and_folds_the_blank_lines_as_land_does(
    tmp_path: Path,
) -> None:
    """A commit through git with the hook installed keeps its co-author line and loses the link; the blank lines
    fold the way land's unlinked() folds them."""
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    hook = hooks / "commit-msg"
    hook.write_text(
        f'#!/bin/sh\nexec "{sys.executable}" "{SCRIPTS / "approvals.py"}" commit-msg "$1"\n'
    )
    hook.chmod(0o755)
    repo = tmp_path / "repo"
    repo.mkdir()
    git_in(repo, "init", "-q")
    git_in(repo, "config", "user.email", "loop@example.com")
    git_in(repo, "config", "user.name", "Loop")
    git_in(repo, "config", "core.hooksPath", str(hooks))
    for message in (LINKED, f"Fix\n\n{CO_AUTHOR}\n\nClaude-Session: https://example.com/s\n"):
        git_in(repo, "commit", "-q", "--allow-empty", "-m", message)
        written = git_in(repo, "log", "-1", "--format=%B").rstrip("\n")
        assert written == approvals.unlinked(message)
        assert "Claude-Session" not in written
        assert written.endswith(f"\n\n{CO_AUTHOR}")
    assert written == f"Fix\n\n{CO_AUTHOR}"


def test_a_message_without_a_link_is_left_as_written(tmp_path: Path) -> None:
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text(f"Fix\n\n\n{CO_AUTHOR}\n\n")
    assert approvals.main(["commit-msg", str(message)]) == 0
    assert message.read_text() == f"Fix\n\n\n{CO_AUTHOR}\n\n"
    message.write_text(LINKED)
    assert approvals.main(["commit-msg", str(message)]) == 0
    assert message.read_text() == f"Fix the parser\n\nKeep the last field.\n\n{CO_AUTHOR}\n"
    # the hook folds the blank lines itself, not only through git's cleanup of the message
    message.write_text(f"Fix\n\nClaude-Session: https://example.com/s\n\n{CO_AUTHOR}\n")
    assert approvals.main(["commit-msg", str(message)]) == 0
    assert message.read_text() == f"Fix\n\n{CO_AUTHOR}\n"
