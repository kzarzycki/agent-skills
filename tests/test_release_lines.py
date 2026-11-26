"""#2678: the decisions of `release.yml`'s `next` and `stable` lines, one test per case."""

from __future__ import annotations

import io
import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

from capability_pack import release_lines as lines
from capability_pack.release_lines import (
    Decision,
    full_suite_ran,
    gate,
    open_release_pr,
    plan_promotions,
)

REPO = "o/r"


def run(**over) -> dict:
    base = {
        "id": 10,
        "conclusion": "success",
        "event": "push",
        "head_branch": "main",
        "head_sha": "abc",
        "head_repository": {"full_name": REPO},
    }
    return base | over


def test_next_goes_on_a_green_main_push_run_a_batch_tested():
    assert gate(run(), REPO, "next", tested=True) == Decision(True, "go")


def test_next_releases_nothing_for_a_tree_no_batch_tested():
    decision = gate(run(), REPO, "next", tested=False)
    assert not decision.ok and "no merge-queue batch" in decision.reason


@pytest.mark.parametrize("conclusion", ["failure", "cancelled", "skipped", None])
def test_next_releases_nothing_for_a_run_that_is_not_green(conclusion):
    decision = gate(run(conclusion=conclusion), REPO, "next", tested=True)
    assert not decision.ok and "not success" in decision.reason


@pytest.mark.parametrize(
    ("over", "why"),
    [
        ({"head_repository": {"full_name": "fork/r"}}, "fork/r"),
        ({"head_repository": None}, "unknown repository"),
        ({"head_branch": "feature"}, "not main"),
        ({"event": "pull_request"}, "event"),
        ({"event": "schedule"}, "event"),
    ],
)
def test_next_refuses_a_fork_a_branch_or_another_event(over, why):
    decision = gate(run(**over), REPO, "next", tested=True)
    assert not decision.ok and why in decision.reason


def test_stable_goes_on_a_green_nightly_that_ran_the_suite():
    assert gate(run(event="schedule"), REPO, "stable", full_suite=True).ok


def test_stable_promotes_nothing_for_a_nightly_that_skipped():
    decision = gate(run(event="schedule"), REPO, "stable", full_suite=False)
    assert not decision.ok and "skipped" in decision.reason


@pytest.mark.parametrize(
    "over",
    [
        {"conclusion": "failure"},
        {"event": "push"},
        {"head_branch": "x"},
        {"head_repository": {"full_name": "f/r"}},
    ],
)
def test_stable_refuses_a_red_run_another_event_branch_or_fork(over):
    assert not gate(run(**({"event": "schedule"} | over)), REPO, "stable", full_suite=True).ok


def test_a_nightly_skips_when_an_earlier_green_one_ran_the_same_commit():
    earlier = {"id": 5, "head_sha": "abc"}
    assert not full_suite_ran(10, "abc", [earlier])
    assert full_suite_ran(
        10, "abc", [{"id": 5, "head_sha": "other"}, {"id": 10, "head_sha": "abc"}]
    )
    assert full_suite_ran(
        10, "abc", [{"id": 12, "head_sha": "abc"}]
    )  # a later one does not make this a skip
    assert full_suite_ran(10, "abc", [])


def test_open_release_pr_names_an_open_release_branch_only():
    pulls = [
        {"state": "open", "html_url": "u1", "head": {"ref": "feature"}},
        {"state": "closed", "html_url": "u2", "head": {"ref": "release/1"}},
        {"state": "open", "html_url": "u3", "head": {"ref": "release/2"}},
    ]
    assert open_release_pr(pulls) == "u3"
    assert open_release_pr(pulls[:2]) is None
    assert open_release_pr([]) is None


def test_open_pr_command_reads_paginated_arrays(monkeypatch, capsys):
    page = json.dumps([{"state": "open", "html_url": "u", "head": {"ref": "release/9"}}])
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps([]) + "\n" + page + "\n"))
    assert lines.main(["open-pr"]) == 0
    assert capsys.readouterr().out.strip() == "u"


TAGS = {
    "a-v1.0.0": "c0",
    "a-v1.0.0-next": "c0",
    "a-v1.0.1-next": "c1",
    "a-v1.0.2-next": "c2",
    "a-v1.0.3-next": "c3",
    "b-v0.1.0-next": "c2",
    "c-v2.0.0": "c1",
    "c-v2.0.0-next": "c1",
    "c-v2.0.1-next": "c3",
    "unrelated": "c9",
}


def test_promotion_tags_the_newest_covered_next_commit_and_skips_older_versions():
    covered = {"c0", "c1", "c2"}.__contains__  # the nightly ran c2; c3 is newer
    assert plan_promotions(TAGS, covered) == [("a-v1.0.2", "c2"), ("b-v0.1.0", "c2")]


def test_a_next_commit_newer_than_the_nightly_is_not_promoted():
    assert plan_promotions(TAGS, {"c0", "c1"}.__contains__) == [("a-v1.0.1", "c1")]


def test_nothing_is_promoted_when_stable_already_has_that_version_or_later():
    assert plan_promotions({"a-v1.0.1-next": "c1", "a-v1.0.1": "c1"}, lambda _: True) == []
    assert plan_promotions({"a-v1.0.1-next": "c1", "a-v1.0.5": "c0"}, lambda _: True) == []
    assert plan_promotions({}, lambda _: True) == []


def _git(repo: Path, *args: str) -> str:
    env = os.environ | {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@e.invalid",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@e.invalid",
    }
    return subprocess.run(
        ["git", *args], cwd=repo, env=env, check=True, capture_output=True, text=True
    ).stdout.strip()


def test_promote_command_on_a_real_repository(tmp_path, capsys):
    """Annotated next tags resolve to their commit; the head and its ancestors are covered, a later commit is not."""
    _git(tmp_path, "init", "-b", "main")
    shas = []
    for n in range(3):
        _git(tmp_path, "commit", "--allow-empty", "-m", f"c{n}")
        shas.append(_git(tmp_path, "rev-parse", "HEAD"))
    _git(tmp_path, "tag", "-a", "p-v0.0.1-next", "-m", "t", shas[0])
    _git(tmp_path, "tag", "-a", "p-v0.0.2-next", "-m", "t", shas[1])
    _git(tmp_path, "tag", "-a", "p-v0.0.3-next", "-m", "t", shas[2])
    assert lines.main(["promote", "--head", shas[1], "--root", str(tmp_path)]) == 0
    assert capsys.readouterr().out.split() == ["p-v0.0.2", shas[1]]


def test_workflow_wires_the_guards():
    doc = yaml.safe_load(Path(".github/workflows/release.yml").read_text())
    on = doc.get(True) or doc["on"]
    assert on["workflow_run"] == {
        "workflows": ["Engineering capability pack"],
        "types": ["completed"],
    }
    jobs = doc["jobs"]
    assert jobs["cut"]["needs"] == "gate"
    assert jobs["cut"]["concurrency"] == {"group": "release", "cancel-in-progress": False}
    assert "schedule" in jobs["promote"]["if"]
    text = Path(".github/workflows/release.yml").read_text()
    assert (
        "needs.gate.outputs.sha" in text
        and "ref: main\n          fetch-depth: 0 # the tags" not in text.split("promote:")[0]
    )


def test_a_workflow_run_cut_defaults_the_magnitude_to_patch():
    """The verifier's F1: `inputs.magnitude` is empty off `workflow_dispatch`, which `cut-release` refuses."""
    text = Path(".github/workflows/release.yml").read_text()
    assert "MAGNITUDE: ${{ inputs.magnitude || 'patch' }}" in text
