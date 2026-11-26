"""scripts/cloud_verifier.py: the usage a verifier's `codex` or `agy` prints is posted under its parent session (#2775)."""

from __future__ import annotations

import json

from test_cloud_verifier import cv


def test_codex_usage_is_read_and_posted_under_the_parent_session(monkeypatch) -> None:
    got = cv.child_usage("codex", "gpt-x", "work\ntokens used\n12,345\n")
    assert got == {"harness": "codex", "model": "gpt-x", "total_tokens": 12345}
    sent: list = []
    monkeypatch.setenv(cv.CHILD_USAGE_URL, "https://omni.example/v1/sessions/{session}/child_usage")
    monkeypatch.setattr(cv, "post_json", lambda url, body, headers: sent.append((url, body)) or {})
    assert cv.post_child_usage(got, "parent1")
    assert sent == [("https://omni.example/v1/sessions/parent1/child_usage", got)]
    json.dumps(sent)


def test_the_post_carries_a_bearer_token_and_a_key_that_repeats_for_a_retry(monkeypatch) -> None:
    sent: list = []
    monkeypatch.setenv(cv.CHILD_USAGE_URL, "https://omni.example/{session}")
    monkeypatch.setenv("OMNIGENT_RUNNER_TOKEN", "tok")
    monkeypatch.setattr(cv, "post_json", lambda url, body, headers: sent.append(headers) or {})
    usage = {"harness": "codex", "model": "m", "total_tokens": 5}
    assert cv.post_child_usage(usage, "p1") and cv.post_child_usage(usage, "p1")
    assert sent[0]["Authorization"] == "Bearer tok"
    assert sent[0]["Idempotency-Key"] == sent[1]["Idempotency-Key"]


def test_agy_usage_carries_its_cost_and_nothing_posts_unless_the_deployment_opts_in(
    monkeypatch,
) -> None:
    got = cv.child_usage("gemini", "g-4", "Total tokens: 900\nTotal cost: $0.42")
    assert got and got["cost_usd"] == 0.42 and got["harness"] == "gemini"
    monkeypatch.delenv(cv.CHILD_USAGE_URL, raising=False)
    assert not cv.post_child_usage(got, "parent1")
    assert cv.child_usage("codex", None, "no usage printed") is None


def test_the_usage_of_an_agy_json_run_is_read_and_a_plain_run_is_left_alone() -> None:
    from_json = '{"result": "SATISFIED: yes", "usage": {"total_tokens": 321}}'
    assert cv.agy_result(from_json) == ("SATISFIED: yes", {"total_tokens": 321})
    assert cv.agy_result("SATISFIED: yes\n") == ("SATISFIED: yes\n", None)
    assert cv.agy_result('{"result": "x"}') == ("x", None)
