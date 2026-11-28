"""`hold <n>` sets the `loop:hold` label with a comment, `--release` removes it (#2998): the manager's stop or hold
command, so the label the pre-push hook and PR-create check read needs no separate step."""

from __future__ import annotations

import pytest
from approvals_harness import approvals, approved
from test_approvals import TRACKER, in_project, loop_md


@pytest.fixture
def labelled(monkeypatch: pytest.MonkeyPatch):
    in_project(monkeypatch)
    monkeypatch.setattr(approvals, "project", lambda: (TRACKER, loop_md()))
    monkeypatch.setattr(approvals, "viewer", lambda: "boss")
    state: dict = {"labels": set(), "comments": []}
    monkeypatch.setattr(approvals, "issue_node", lambda n: approved(n, *state["labels"]))
    monkeypatch.setattr(
        approvals,
        "label",
        lambda n, name, add: state["labels"].add(name) if add else state["labels"].discard(name),
    )
    monkeypatch.setattr(approvals, "comment", lambda n, body: state["comments"].append(body))
    return state


def test_hold_puts_the_label_on_with_a_comment_naming_who_and_why_and_release_lifts_it(
    labelled, capsys
):
    assert approvals.main(["hold", "9", "--why", "spec replaced"]) == 0
    assert "loop:hold" in labelled["labels"]
    assert "@boss" in labelled["comments"][0] and "spec replaced" in labelled["comments"][0]
    assert approvals.main(["hold", "9", "--release"]) == 0
    assert "loop:hold" not in labelled["labels"]
    assert "lifted" in labelled["comments"][1]
    assert capsys.readouterr().out.splitlines()[-1] == "#9: hold lifted"
