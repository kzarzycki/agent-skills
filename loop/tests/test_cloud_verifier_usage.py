"""scripts/cloud_verifier.py: the usage a verifier's `codex` or `agy` prints is posted under its parent session (#2775)."""

from __future__ import annotations

import json

from test_cloud_verifier import cv


def test_the_post_matches_the_child_usage_contract(monkeypatch) -> None:
    got = cv.child_usage("codex", "gpt-x", "work\ntokens used\n12,345\n")
    assert got == {"harness": "codex", "model": "gpt-x", "total_tokens": 12345}
    sent: list = []
    monkeypatch.setenv(cv.SERVER_URL, "https://omni.example/")
    monkeypatch.delenv("OMNIGENT_RUNNER_TOKEN", raising=False)
    monkeypatch.setattr(
        cv, "post_json", lambda url, body, headers: sent.append((url, body, headers)) or {}
    )
    assert cv.post_child_usage({**got, "cost_usd": 0.5}, "parent1", "codex/1")
    [(url, body, headers)] = sent
    assert url == "https://omni.example/v1/sessions/parent1/child-usage"
    assert set(body) == {"key", "harness", "model", "total_tokens", "cost_usd"}
    assert (body["harness"], body["model"], body["total_tokens"]) == ("codex", "gpt-x", 12345)
    assert headers == {"X-Omnigent-Orchestration-Source": "parent1"}
    json.dumps(sent)


def test_an_unknown_model_and_missing_numbers_are_left_out_of_the_body(monkeypatch) -> None:
    sent: list = []
    monkeypatch.setenv(cv.SERVER_URL, "https://omni.example")
    monkeypatch.setattr(cv, "post_json", lambda url, body, headers: sent.append(body) or {})
    assert cv.post_child_usage({"harness": "gemini", "model": "?", "total_tokens": 9}, "p1", "r")
    assert set(sent[0]) == {"key", "harness", "total_tokens"}


def test_the_key_is_stable_per_child_run_and_differs_between_runs(monkeypatch) -> None:
    sent: list = []
    monkeypatch.setenv(cv.SERVER_URL, "https://omni.example")
    monkeypatch.setenv("OMNIGENT_RUNNER_TOKEN", "tok")
    monkeypatch.setattr(
        cv, "post_json", lambda url, body, headers: sent.append((body, headers)) or {}
    )
    usage = {"harness": "codex", "model": "m", "total_tokens": 5}
    # a retry of one run, its numbers changed, replaces the entry; another run adds one
    assert cv.post_child_usage(usage, "p1", "codex/1")
    assert cv.post_child_usage({**usage, "total_tokens": 6}, "p1", "codex/1")
    assert cv.post_child_usage(usage, "p1", "codex/2")
    assert sent[0][0]["key"] == sent[1][0]["key"] != sent[2][0]["key"]
    assert sent[0][1]["Authorization"] == "Bearer tok"


def test_agy_usage_carries_its_cost_and_nothing_posts_unless_the_deployment_opts_in(
    monkeypatch,
) -> None:
    got = cv.child_usage("gemini", "g-4", "Total tokens: 900\nTotal cost: $0.42")
    assert got and got["cost_usd"] == 0.42 and got["harness"] == "gemini"
    monkeypatch.delenv(cv.SERVER_URL, raising=False)
    assert not cv.post_child_usage(got, "parent1")
    assert cv.child_usage("codex", None, "no usage printed") is None


def test_the_usage_of_an_agy_json_run_is_read_and_a_plain_run_is_left_alone() -> None:
    from_json = '{"result": "SATISFIED: yes", "usage": {"total_tokens": 321}}'
    assert cv.agy_result(from_json) == ("SATISFIED: yes", {"total_tokens": 321})
    assert cv.agy_result("SATISFIED: yes\n") == ("SATISFIED: yes\n", None)
    assert cv.agy_result('{"result": "x"}') == ("x", None)


def test_an_entry_with_no_count_and_no_cost_is_not_posted(monkeypatch) -> None:
    monkeypatch.setenv(cv.SERVER_URL, "https://omni.example")
    monkeypatch.setattr(cv, "post_json", lambda *a: (_ for _ in ()).throw(AssertionError("posted")))
    assert not cv.post_child_usage({"harness": "codex", "model": "m"}, "p1", "r")
