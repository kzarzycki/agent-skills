"""scripts/cloud_verifier.py: a Codex pass with no model or effort named runs Terra at medium effort, and a second Codex
pass on a head that already has one is refused, naming it (#2870). `gh` and `codex` are the checkout fixture's stand-ins."""

from __future__ import annotations

import json

import pytest
from test_cloud_verifier import checkout, cv  # noqa: F401 - `checkout` is a fixture


@pytest.fixture(autouse=True)
def who_can_write(monkeypatch):
    """GitHub's answer: `writer` writes, `reader` is an org member who reads, and the PR's author and the runner are
    `author` and `runner`."""
    monkeypatch.setattr(cv, "can_write", lambda login: login == "writer")
    monkeypatch.setattr(cv, "pass_logins", lambda pr: {"author", "runner"})


REPORT = "# Report\n\nHead: x\nVERDICT: 0 blocker\nSATISFIED: yes\nRisk: low\n"


def test_a_codex_pass_with_no_model_or_effort_runs_terra_at_medium(checkout) -> None:  # noqa: F811
    _, _, brief, _, seen = checkout
    seen["report"] = REPORT
    assert cv.verify(7, brief, None, None) == 0
    assert seen["cmd"][-5:] == ["-m", "gpt-6.1-terra", "-c", "model_reasoning_effort=medium", "-"]
    assert seen["brief"].startswith("AGENT_SIGNATURE=codex/terra-6.1/med\n")


def test_a_start_that_names_sol_and_an_effort_keeps_them(checkout) -> None:  # noqa: F811
    _, _, brief, _, seen = checkout
    seen["report"] = REPORT
    assert cv.verify(7, brief, "gpt-6.1-sol", "high") == 0
    assert seen["cmd"][-5:] == ["-m", "gpt-6.1-sol", "-c", "model_reasoning_effort=high", "-"]


def test_a_second_codex_pass_on_an_unchanged_head_is_refused_naming_the_first(
    checkout,  # noqa: F811
    monkeypatch,
) -> None:
    _, head, brief, posted, seen = checkout
    seen["report"] = REPORT
    first = {
        "user": {"login": "writer"},
        "commit_id": head,
        "body": "Verifier (codex/terra-6.1/med), pass 1 on abc",
    }
    monkeypatch.setattr(cv, "pass_history", lambda pr: ([first], []))
    with pytest.raises(
        cv.Refused, match=r"already has a Codex verifier pass \(codex/terra-6.1/med, pass 1\)"
    ):
        cv.verify(7, brief, None, None)
    assert "cmd" not in seen and posted == []  # Codex never started


def test_a_pass_comment_of_this_script_counts_and_another_head_or_family_does_not(checkout) -> None:  # noqa: F811
    head = checkout[1]
    comment = {
        "user": {"login": "writer"},
        "body": f"Head: {head}\nVERDICT: 0 blocker\n\nVerifier: codex/sol-6.1/high, pass 2\n",
    }
    assert cv.earlier_codex_pass([], [comment], head) == ("codex/sol-6.1/high", "2")
    assert cv.earlier_codex_pass([], [comment], "f" * 40) is None  # a new head: a fix was pushed
    other = {"commit_id": head, "body": "Verifier (claude, same-family), pass 1"}
    assert cv.earlier_codex_pass([other], [], head) is None  # another route's pass is no Codex pass


def test_paginated_pages_are_read_back_to_back_and_a_bad_answer_is_none() -> None:
    pages = json.dumps([{"a": "] ["}]) + json.dumps([{"b": 2}])
    assert cv.json_arrays(pages) == [{"a": "] ["}, {"b": 2}]
    assert cv.json_arrays("not json") == []


def test_a_thread_pass_on_an_unchanged_head_is_refused_before_a_thread_is_made(
    monkeypatch, tmp_path
) -> None:
    head = "a" * 40
    monkeypatch.setattr(cv, "host_token", lambda: "t")
    monkeypatch.setattr(cv, "quota", lambda token: "ok")
    monkeypatch.setattr(cv, "Rpc", lambda token: object())
    monkeypatch.setattr(
        cv,
        "run",
        lambda *cmd, **kw: cv.subprocess.CompletedProcess(cmd, 0, "abc o/r feat/pr\n", ""),
    )
    first = {
        "user": {"login": "writer"},
        "commit_id": "abc",
        "body": "Verifier (codex/terra-6.1/med), pass 1",
    }
    monkeypatch.setattr(cv, "pass_history", lambda pr: ([first], []))

    def no_thread(*args):
        raise AssertionError("a thread was started")

    monkeypatch.setattr(cv, "thread_start", no_thread)
    brief = tmp_path / "brief.md"
    brief.write_text("Review.\n")
    with pytest.raises(cv.Refused, match=r"codex/terra-6.1/med, pass 1"):
        cv.thread_verify(7, brief, None, None, None, "env")
    assert head  # a later head is another pass: see earlier_codex_pass's test


def by(login: str, body: str, head: str) -> dict:
    return {"user": {"login": login}, "commit_id": head, "body": body}


def test_a_review_quoting_a_verdict_or_an_untrusted_heading_does_not_refuse_a_pass_3003(
    checkout,  # noqa: F811
    monkeypatch,
) -> None:
    head = checkout[1]
    heading = "Verifier (codex/terra-6.1/med), pass 1"
    reviews = [
        by("author", f"Re the earlier run:\n\n{heading}\n", head),  # after other text
        by("author", f"> {heading}\n", head),  # a blockquote of one
        by("reader", heading, head),  # an org member who only reads
        by("stranger", heading, head),
    ]
    monkeypatch.setattr(cv, "pass_history", lambda pr: (reviews, []))
    cv.refuse_repeat_codex_pass(7, head)  # no refusal
    monkeypatch.setattr(cv, "pass_history", lambda pr: ([by("writer", heading, head)], []))
    with pytest.raises(cv.Refused, match=r"pass 1"):
        cv.refuse_repeat_codex_pass(7, head)


def test_the_report_this_script_posts_is_found_as_a_pass_3003(checkout) -> None:  # noqa: F811
    head = checkout[1]
    report = (
        f"Head: {head}\nVERDICT: 0 blocker\nSATISFIED: yes\nRisk: low\n\n"
        "Verifier: codex/terra-6.1/med, pass 1\n\nThe criteria...\n"
    )
    posted = {"user": {"login": "author"}, "body": cv.folded_report(report)}
    assert posted["body"].startswith("## Verifier report")
    assert cv.earlier_codex_pass([], [posted], head, {"author"}) == ("codex/terra-6.1/med", "1")
    chatter = {"user": {"login": "author"}, "body": f"As posted:\n\n{posted['body']}"}
    assert cv.earlier_codex_pass([], [chatter], head, {"author"}) is None


def test_the_guard_uses_the_shared_predicate_3003(checkout, monkeypatch) -> None:  # noqa: F811
    head = checkout[1]
    seen = []

    def shared(reviews, comments, head, logins=(), writer=None):
        seen.append(head)
        return ("codex/shared", "9")

    monkeypatch.setattr(cv.verifier_pass, "earlier_codex_pass", shared)
    monkeypatch.setattr(cv, "pass_history", lambda pr: ([], []))
    with pytest.raises(cv.Refused, match=r"codex/shared, pass 9"):
        cv.refuse_repeat_codex_pass(7, head)
    assert seen == [head]
