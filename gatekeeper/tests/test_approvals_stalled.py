"""approvals.py: `check stalled` judges every base, not only Mergify's, and a PR it can't judge stops no other (#1746).

On a base `land` merges itself, a PR `landable` accepts that is still open was never landed; where GitHub's merge
queue holds the base, one not in that queue is listed. A PR stacked on another PR's branch, whose code differs from
what runs here, gets one `not judged` line and the PRs after it are still judged. Driven through main() against the
fixtures of test_approvals_github_queue.py.
"""

from __future__ import annotations

import subprocess
from typing import Any

import pytest
from approvals_harness import approvals, git_in, lands  # noqa: F401
from test_approvals_github_queue import queue  # noqa: F401


@pytest.fixture
def direct(queue: dict[str, Any]) -> dict[str, Any]:
    """`queue` on a base whose rules require `qualify` and no merge queue, with no Mergify in the policy: `land`
    merges each PR itself."""
    queue["rules"] = approvals.github.Required({"qualify"})
    return queue


def stalled(capsys: pytest.CaptureFixture[str]) -> tuple[int, list[str]]:
    capsys.readouterr()
    code = approvals.main(["check", "stalled"])
    return code, capsys.readouterr().out.splitlines()


def test_a_landable_pr_on_a_direct_land_base_is_listed_until_it_lands(
    direct: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    head = direct["opened"](7)
    code, lines = stalled(capsys)
    assert (code, lines) == (
        1,
        [f"PR #7 has its go and a satisfied verdict at {head} and is not landed"],
    )
    assert direct["land"]("7", "--only")[0] == 0
    assert direct["merged"]() == ["7"]
    assert stalled(capsys) == (0, [])


def test_a_pr_land_would_refuse_is_not_listed(
    direct: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    """A required check that is red holds the PR: `land` would not take it, so it is not stalled."""
    direct["opened"](7)
    direct["pulls"][7]["commits"]["nodes"][0]["commit"]["statusCheckRollup"]["contexts"]["nodes"][
        0
    ]["conclusion"] = "FAILURE"
    assert stalled(capsys) == (0, [])


def test_a_pr_in_github_s_merge_queue_is_not_listed(
    queue: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    head = queue["opened"](7)
    code, lines = stalled(capsys)
    assert (code, lines) == (
        1,
        [f"PR #7 has its go and a satisfied verdict at {head} and is not in the merge queue"],
    )
    assert queue["land"]("7", "--only")[0] == 0 and queue["enqueued"] == [(7, head)]
    assert stalled(capsys) == (0, [])


def test_a_stacked_pr_is_skipped_with_a_line_and_the_prs_after_it_are_still_judged(
    direct: dict[str, Any], capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """#7's base is another PR's branch, whose gatekeeper differs from the one running here: it is not judged, and #8
    and #9 after it are."""
    git_in(direct["work"], "push", "-q", "origin", "origin/main:refs/heads/pr-base")
    direct["opened"](7)
    direct["pulls"][7]["baseRefName"] = "pr-base"
    eight = direct["opened"](8)
    nine = direct["opened"](9)
    stub = approvals.judge_with_base  # the harness's: every base's code is what runs here

    def judge(base: str, fetch: bool = False) -> None:
        if base == "pr-base":  # as judge_with_base words it, from base_drift's list
            raise approvals.Drifted(
                "gatekeeper/skills/gatekeeper/scripts/gatekeeper.py differs from origin/pr-base's: a PR's own copy"
                " would judge it; run from the base's code (a checkout of origin/pr-base)",
                base,
            )
        stub(base, fetch)

    monkeypatch.setattr(approvals, "judge_with_base", judge)
    code, lines = stalled(capsys)
    assert code == 1
    assert lines == [
        (
            "PR #7 into pr-base is not judged here: gatekeeper/skills/gatekeeper/scripts/gatekeeper.py differs from"
            " origin/pr-base's: a PR's own copy would judge it; run from the base's code (a checkout of origin/pr-base)"
        ),
        f"PR #8 has its go and a satisfied verdict at {eight} and is not landed",
        f"PR #9 has its go and a satisfied verdict at {nine} and is not landed",
    ]


def test_a_base_that_can_t_be_fetched_skips_its_prs_alone(
    direct: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    """A base origin no longer has: each PR into it gets its line, a skip alone exits 0."""
    direct["opened"](7)
    direct["pulls"][7]["baseRefName"] = "gone"
    code, lines = stalled(capsys)
    assert code == 0
    assert len(lines) == 1 and lines[0].startswith(
        "PR #7 into gone is not judged here: could not fetch or read gone"
    )


def test_a_refused_pr_read_skips_that_pr_alone(
    direct: dict[str, Any], capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    direct["opened"](7)
    eight = direct["opened"](8)
    pulls = direct["pulls"]

    def read(number: int) -> dict[str, Any]:
        if number == 7:
            raise subprocess.CalledProcessError(1, "gh", stderr="gh: timed out")
        return pulls[number]

    monkeypatch.setattr(approvals, "pull_request", read)
    code, lines = stalled(capsys)
    assert (code, lines) == (
        1,
        [
            "PR #7 into main is not judged here: gh: timed out",
            f"PR #8 has its go and a satisfied verdict at {eight} and is not landed",
        ],
    )
