"""approvals.py: a line that is only a cloud session's link, which its harness ends each PR body with, is a session
link line as a `Claude-Session:` line is, so `land` drops it from the squash body, and from the PR's own body on
GitHub before the merge (#1059)."""

from __future__ import annotations

from typing import Any

import pytest
from approvals_harness import (
    added,  # noqa: F401
    approvals,
    assigned,  # noqa: F401
    attached,  # noqa: F401
    board_risks,  # noqa: F401
    graphql_answers,  # noqa: F401
    hub,  # noqa: F401
    lands,  # noqa: F401
    others_open,  # noqa: F401
    pushed,  # noqa: F401
    refs,  # noqa: F401
    required,  # noqa: F401
)

LINK = "https://claude.ai/code/session_01AbCdEf"
# a body land accepts: it has an Evidence section with content
BODY = "## Summary\n\nFix it.\n\n## Evidence\n\nlog line"


def test_unlinked_drops_a_bare_session_link_line_and_folds_its_blank_lines() -> None:
    """A bare link line, or one in <...>, goes and its blank lines fold as a `Claude-Session:` line's do."""
    for line in (LINK, f"<{LINK}>", f"{LINK}  "):
        assert approvals.unlinked(f"## Summary\n\nFix it.\n\n{line}\n") == "## Summary\n\nFix it."
        assert approvals.unlinked(f"a\n{line}\nb") == "a\nb"
        assert approvals.unlinked(f"a\n\n{line}\n\nb") == "a\n\nb"
    # a line that only mentions such a link inside other text stays
    for kept in (
        f"See {LINK} for the run.",
        f"- {LINK}",
        f"[run]({LINK})",
        f"{LINK} ran it",
        "https://example.com/code/session_01AbCdEf",
    ):
        assert approvals.unlinked(f"a\n\n{kept}\n") == f"a\n\n{kept}"


def test_land_body_under_pr_body_returns_the_body_without_the_link_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        approvals,
        "gh",
        lambda *args: (
            '{"squash_merge_commit_message": "PR_BODY"}'
            if args == ("api", "repos/{owner}/{repo}")
            else ""
        ),
    )
    body = f"## Summary\n\nFix it.\n\n## Evidence\n\nlog line\n\n{LINK}\n"
    assert approvals.land_body({"number": 7, "body": body}) == (
        "## Summary\n\nFix it.\n\n## Evidence\n\nlog line"
    )


def test_land_edits_a_pr_body_that_carries_the_link_and_leaves_a_clean_one_untouched(
    lands: dict[str, Any], hub: dict[str, list[dict[str, Any]]]
) -> None:
    lands["open"](7, {"7.txt": "7\n"}, body=f"{BODY}\n\n{LINK}\n")
    lands["open"](8, {"8.txt": "8\n"}, body=f"{BODY}\n")
    code, lines = lands["land"]()
    assert code == 0, lines
    edits = [args for args in lands["calls"] if args[:2] == ("pr", "edit")]
    assert edits == [("pr", "edit", "7", "--body", BODY)]
    assert lands["pulls"][7]["body"] == BODY
    assert lands["pulls"][8]["body"] == f"{BODY}\n"
    assert "PR #7: dropped the session link from its body" in lines
    assert not any(line.startswith("PR #8: dropped") for line in lines)
    assert sorted(lands["merged"]()) == ["7", "8"]
    # the body is edited before its PR merges
    order = [args[:3] for args in lands["calls"] if args[:2] in (("pr", "edit"), ("pr", "merge"))]
    assert order.index(("pr", "edit", "7")) < order.index(("pr", "merge", "7"))
