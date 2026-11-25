"""A Mergify dequeue leaves a ``Queue failure`` record on its PR, and the supervisor reads the same code (#2497).

The seam: the two real dequeue comments of two PRs and their jobs' pytest summary lines
(``queue_failure_fixtures.json``, copied from the PRs' comments and job logs), ``gh`` faked as a PR's comments, its job
logs and its comment post, and the supervisor's own ``dequeue_message`` over the same entries."""

from __future__ import annotations

import io
import json
import re
from pathlib import Path

import pytest
from test_omnigent_agent import omnigent_agent

CASES = json.loads(Path(__file__).with_name("queue_failure_fixtures.json").read_text())
QF = omnigent_agent.QUEUE_FAILURE

FIRST = {
    "checks": ["qualify"],
    "tests": ["tests/test_skill_layers.py::test_no_skill_names_a_layer_above_its_own"],
}
SECOND = {
    "checks": ["qualify", "rerun"],
    "tests": [
        "tests/test_affected_tests.py::test_a_build_input_runs_the_whole_suite[pyproject.toml]",
        "tests/test_affected_tests.py::test_a_build_input_runs_the_whole_suite[uv.lock]",
        "tests/test_affected_tests.py::test_a_build_input_runs_the_whole_suite[mise.toml]",
        "tests/test_affected_tests.py::test_a_build_input_runs_the_whole_suite[conftest.py]",
        "tests/test_affected_tests_floor.py::test_the_queue_reads_the_policy_and_defaults_to_floor_outside_it_full",
    ],
}
EXPECTED = {"2446": FIRST, "2449": SECOND}


class FakeGh:
    """``gh`` as the script calls it: a PR's comments (``existing`` bodies), a job's log (``logs`` by job id, a missing
    one failing) and the comment post, whose body is kept in ``posted``."""

    def __init__(
        self, logs: dict[str, str], existing: tuple[str, ...] = (), post_fails: bool = False
    ):
        self.logs, self.existing, self.post_fails = logs, existing, post_fails
        self.posted: list[str] = []

    def __call__(self, *args: str, stdin: str | None = None) -> str:
        path = next(a for a in args if a.startswith("repos/"))
        if "POST" in args:
            if self.post_fails:
                raise RuntimeError("gh api failed: 403")
            self.posted.append(stdin or "")
            return ""
        if path.endswith("/comments"):
            return json.dumps([[{"body": b} for b in self.existing]])
        job = path.split("/jobs/")[1].split("/")[0]
        if job not in self.logs:
            raise RuntimeError("gh api failed: 404")
        return self.logs[job]


def env_of(pr: str, **over: str) -> dict[str, str]:
    c = CASES[pr]["comment"]
    return {
        "REPO": "o/r",
        "PR": pr,
        "COMMENT_ID": str(c["id"]),
        "COMMENT_URL": c["html_url"],
        "AUTHOR": c["user"]["login"],
        "BODY": c["body"],
    } | over


def run(env: dict[str, str], gh: FakeGh) -> tuple[int, str]:
    out = io.StringIO()
    code = QF.write(env, gh, out)
    return code, out.getvalue()


@pytest.mark.parametrize("pr", ["2446", "2449"])
def test_the_record_lists_the_failing_checks_and_tests_of_a_real_dequeue(pr: str) -> None:
    gh = FakeGh(CASES[pr]["logs"])
    code, _ = run(env_of(pr), gh)
    [body] = gh.posted
    assert code == 0
    assert body.split("\n", 1)[0] == "Queue failure"
    assert "left the merge queue: CHECKS_FAILED" in body
    assert "At fault: this pull request" in body
    for name in EXPECTED[pr]["checks"]:
        assert re.search(
            rf"^- \[`{name}`\]\(https://github\.com/\S+/job/\d+\)$", body, re.MULTILINE
        )
    tests = re.findall(r"^- `(tests/[^`]+)`$", body, re.MULTILINE)
    assert tests == EXPECTED[pr]["tests"]


@pytest.mark.parametrize("pr", ["2446", "2449"])
def test_the_supervisor_reads_the_same_code_and_the_same_tests(pr: str) -> None:
    comment = CASES[pr]["comment"] | {"issue_url": f"https://api.github.com/repos/o/r/issues/{pr}"}
    entry = omnigent_agent.queue_comment(comment)
    assert omnigent_agent.queue_comment is QF.queue_comment
    assert omnigent_agent.failed_tests is QF.failed_tests
    entry["tests"] = [t for log in CASES[pr]["logs"].values() for t in QF.failed_tests(log)]
    entry["tests"] = list(dict.fromkeys(entry["tests"]))
    message = omnigent_agent.dequeue_message("o/r", entry, {})
    assert entry["tests"] == EXPECTED[pr]["tests"]
    assert "Failing tests: " + ", ".join(entry["tests"]) in message
    assert all(line in message for line in QF.failure_lines(entry))


def test_a_comment_reported_once_is_not_reported_again() -> None:
    gh = FakeGh(CASES["2446"]["logs"])
    run(env_of("2446"), gh)
    again = FakeGh(CASES["2446"]["logs"], existing=tuple(gh.posted))
    code, said = run(env_of("2446"), again)
    assert (code, again.posted) == (0, [])
    assert "already reported" in said


@pytest.mark.parametrize(
    "over",
    [
        {"AUTHOR": "someone"},  # a comment anyone can post on a public repo
        {"BODY": "Queued for Mergify\n\nHead: " + "a" * 40},
        {"BODY": "a plain comment"},
    ],
)
def test_a_comment_that_is_not_a_mergify_dequeue_writes_nothing(over: dict[str, str]) -> None:
    gh = FakeGh(CASES["2446"]["logs"])
    code, _ = run(env_of("2446", **over), gh)
    assert (code, gh.posted) == (0, [])


def test_a_merge_or_a_dequeue_that_is_not_a_failed_check_writes_nothing() -> None:
    body = CASES["2446"]["comment"]["body"]
    merged = body.replace('"state": "dequeued"', '"state": "merged"')
    manual = body.replace("CHECKS_FAILED", "PR_DEQUEUED")
    for text in (merged, manual):
        gh = FakeGh(CASES["2446"]["logs"])
        assert run(env_of("2446", BODY=text), gh)[0] == 0
        assert gh.posted == []


def test_an_unreadable_log_still_leaves_a_record_that_says_so() -> None:
    gh = FakeGh({})
    code, _ = run(env_of("2446"), gh)
    [body] = gh.posted
    assert code == 0
    assert "Log not read for: `qualify`" in body
    assert "none found in the failing jobs' logs" in body


def test_a_refused_post_exits_1() -> None:
    gh = FakeGh(CASES["2446"]["logs"], post_fails=True)
    assert run(env_of("2446"), gh)[0] == 1


@pytest.mark.parametrize("pr", ["2446", "2449"])
def test_the_record_names_nothing_private(pr: str) -> None:
    gh = FakeGh(CASES[pr]["logs"])
    run(env_of(pr), gh)
    [body] = gh.posted
    hosts = set(re.findall(r"https?://([^/\s)]+)", body))
    assert hosts <= {"github.com"}
    assert not re.search(r"(?i)session|/home/|/Users/|token|secret", body)


def test_a_test_name_from_a_log_cannot_close_its_code_span() -> None:
    entry = {
        "pr": 7,
        "code": "CHECKS_FAILED",
        "checks": [("check", "https://x/1", "1")],
        "tests": ["t`[x](https://e)@bot"],
    }
    body = QF.record(entry, "9")
    assert "- `t'[x](https://e)@bot`" in body
    assert body.count("`") % 2 == 0


def test_a_noisy_log_still_leaves_a_record_under_the_size_limit() -> None:
    tests = [f"tests/test_{i}.py::test_{'x' * 400}_{i}" for i in range(5000)]
    entry = {
        "pr": 7,
        "code": "CHECKS_FAILED",
        "checks": [("check", "https://x/1", "1")],
        "tests": tests,
    }
    body = QF.record(entry, "9")
    assert len(body) < 65536
    assert "- and 4950 more in the failing jobs' logs" in body
    assert QF.reported([body], "9")  # the once-per-comment marker survives the cut
