"""approvals.py: a verdict and a go on an earlier head hold for a head with the same tree (#1019)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
from approvals_harness import (
    LOOP,
    added,  # noqa: F401
    approvals,
    approved,
    assigned,  # noqa: F401
    attached,  # noqa: F401
    board_risks,  # noqa: F401
    graphql_answers,  # noqa: F401
    hub,  # noqa: F401
    note,
    others_open,  # noqa: F401
    pull,
    pushed,  # noqa: F401
    record,
    refs,  # noqa: F401
    required,  # noqa: F401
    status,
    verdict_on,
)

ISSUES = [approved(1, "area:web")]
AFTER = "every commit after a verdict needs a verdict of its own"


def git(where: Path, *args: str) -> str:
    who = ("-c", "commit.gpgsign=false", "-c", "user.name=Lead", "-c", "user.email=l@example.com")
    return subprocess.run(
        ["git", *who, *args], cwd=where, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def heads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """A checkout with the reviewed head `reviewed`, `reworded` (the same change under another message, so the same
    tree) and `changed` (one more file changed on top of `reviewed`), and `tree`, the reviewed head's tree."""
    monkeypatch.chdir(tmp_path)
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "app.py").write_text("one\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "base")
    (tmp_path / "app.py").write_text("one, the feature\n")
    git(tmp_path, "commit", "-qam", "feature\n\nCo-authored-by: A <a@example.com>")
    reviewed = git(tmp_path, "rev-parse", "HEAD")
    git(tmp_path, "commit", "-q", "--amend", "-m", "feature\n\nCo-Authored-By: A <a@example.com>")
    reworded = git(tmp_path, "rev-parse", "HEAD")
    git(tmp_path, "switch", "-qc", "changed", reviewed)
    (tmp_path / "app.py").write_text("one, the feature, changed\n")
    git(tmp_path, "commit", "-qam", "feature, changed")
    return {
        "reviewed": reviewed,
        "reworded": reworded,
        "changed": git(tmp_path, "rev-parse", "HEAD"),
        "tree": git(tmp_path, "rev-parse", f"{reviewed}^{{tree}}"),
    }


def pr_at(
    head: str,
    reviewed: str,
    hub: dict[str, list[dict[str, Any]]],
    go: bool = True,
    threads: tuple[bool, ...] = (),
    **verdict: str,
) -> dict[str, Any]:
    """A high-risk PR now at `head`, with a verifier pass on `reviewed` and, with `go`, the owner's go there as
    `approve merge` leaves it (the record on the PR, the status on the commit)."""
    review = verdict_on(reviewed, **verdict)
    pr = pull(reviews=(review,), files=("app.py",), labels=("risk:high",), threads=threads)
    pr["headRefOid"] = reviewed
    if go:
        pr["comments"]["nodes"].append(note(record("merge", "owner", head=reviewed)))
        hub.setdefault(reviewed, []).insert(
            0, status("owner", f"The owner's go on {reviewed[:12]}")
        )
    pr["headRefOid"] = head
    return pr


def merge(pr: dict[str, Any]) -> list[str]:
    """check merge's lines: what fails, then what it waits for."""
    return approvals.proofs("merge", pr, ISSUES, LOOP) + approvals.waits(pr, ISSUES, LOOP)


def test_a_reworded_head_passes_check_merge_on_the_old_verdict_and_go(
    heads: dict[str, str], hub: dict[str, list[dict[str, Any]]], capsys: pytest.CaptureFixture[str]
) -> None:
    reviewed, reworded, tree = heads["reviewed"], heads["reworded"], heads["tree"]
    pr = pr_at(reworded, reviewed, hub)
    assert merge(pr) == []
    assert capsys.readouterr().out.splitlines() == [
        f"PR #7: verdict on {reviewed} carried: same tree {tree}"
    ]
    assert approvals.owner_waits(pr, [], LOOP) == []
    assert approvals.whose(pr, LOOP) == [
        f"PR #7: the go on {reviewed} is the owner's, carried to {reworded}: same tree {tree}"
    ]


def test_a_head_with_one_changed_file_keeps_todays_rules(
    heads: dict[str, str], hub: dict[str, list[dict[str, Any]]], capsys: pytest.CaptureFixture[str]
) -> None:
    reviewed, changed = heads["reviewed"], heads["changed"]
    pr = pr_at(changed, reviewed, hub)
    lines = merge(pr)
    assert lines[0] == (
        f"PR #7: the newest verifier review is on {reviewed}, not on the head {changed}: {AFTER}"
    )
    assert any(line.startswith("PR #7 waits for the owner's go on its head") for line in lines)
    assert approvals.whose(pr, LOOP) == []
    assert "carried" not in capsys.readouterr().out


@pytest.mark.parametrize(
    ("verdict", "threads", "why"),
    [
        (
            {"satisfied": "no"},
            (),
            "PR #7: a verifier review on {reviewed} is not satisfied: fix and verify again",
        ),
        (
            {"counts": "0 blocker, 1 major, 0 minor"},
            (),
            "PR #7: the verifier reviews on {reviewed} have 0 blocker and 1 major open: fix and verify again",
        ),
        (
            {},
            (False,),
            "PR #7: 1 review thread(s) unresolved: fix and reply, or triage, then resolve (github.md, Review trail)",
        ),
    ],
    ids=["an unsatisfied pass", "a major open", "an unresolved thread"],
)
def test_a_carried_verdict_counts_as_it_did_on_the_old_head(
    heads: dict[str, str],
    hub: dict[str, list[dict[str, Any]]],
    verdict: dict[str, str],
    threads: tuple[bool, ...],
    why: str,
) -> None:
    pr = pr_at(heads["reworded"], heads["reviewed"], hub, threads=threads, **verdict)
    lines = approvals.proofs("merge", pr, ISSUES, LOOP)
    assert why.format(**heads) in lines
    assert not any(AFTER in line for line in lines)


def test_a_carried_verdicts_risk_line_still_holds(
    heads: dict[str, str], hub: dict[str, list[dict[str, Any]]]
) -> None:
    pr = pr_at(heads["reworded"], heads["reviewed"], hub)
    pr["reviews"]["nodes"][0]["body"] += "Risk: high, it changes when a go holds\n"
    assert approvals.judged(pr, LOOP) == (
        f"the verifier's pass 1 on {heads['reviewed'][:7]} says `Risk: high, it changes when a go holds`"
    )


def test_a_reworded_head_without_a_go_on_the_old_one_waits_for_the_owner(
    heads: dict[str, str], hub: dict[str, list[dict[str, Any]]]
) -> None:
    pr = pr_at(heads["reworded"], heads["reviewed"], hub, go=False)
    assert [line[:42] for line in approvals.owner_waits(pr, [], LOOP)] == [
        "PR #7 waits for the owner's go on its head"
    ]


def test_commits_neither_the_clone_nor_origin_has_share_no_tree(
    heads: dict[str, str], hub: dict[str, list[dict[str, Any]]]
) -> None:
    """Two unreadable trees are no same tree: the head is held to today's rules."""
    pr = pr_at("c" * 40, "d" * 40, hub)
    assert approvals.same_tree("c" * 40, "d" * 40) is None
    assert (
        merge(pr)[0]
        == f"PR #7: the newest verifier review is on {'d' * 40}, not on the head {'c' * 40}: {AFTER}"
    )
