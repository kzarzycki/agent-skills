"""wait-for's PR waits and the supervisor's required_pending spend no GitHub quota on a round where nothing they read
changed: each REST read carries its last ETag, GitHub's 304 costs nothing, and the GraphQL read of `--until checks`
waits for a REST read to move (#1984). A fake GitHub answers as the real one does, through the real gh()."""

import hashlib
import itertools
import json
import subprocess
from typing import Any

import pytest
from test_omnigent_agent import omnigent_agent as oa

HEAD = "a" * 40
TREE = "c" * 40
ROUNDS = 30  # an hour of rounds at WAIT_FOR_PR_EVERY (120 s)


class GitHub:
    """REST answers by path, each with an ETag of its body; `spent` counts the calls that cost quota (a 200 or a
    GraphQL read), `free` the 304s."""

    def __init__(
        self, monkeypatch: pytest.MonkeyPatch, rest: dict[str, Any], view: dict[str, Any]
    ) -> None:
        self.rest, self.view, self.spent, self.free = rest, view, 0, 0
        monkeypatch.setattr(oa, "ETAGS", {})
        monkeypatch.setattr(oa, "COMMITS", {})
        monkeypatch.setattr(oa.subprocess, "run", self.run)

    def run(self, cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        assert cmd[:2] == ["gh", "pr"] or cmd[:2] == ["gh", "api"], cmd
        if cmd[1] == "pr":  # gh pr view: GraphQL
            self.spent += 1
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(self.view))
        if (
            "--paginate" in cmd
        ):  # a paged list (a verdict's comments and reviews): read only once the pull moved
            self.spent += 1
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout="".join(
                    json.dumps(i) + "\n" for i in self.rest[cmd[3].replace("{owner}/{repo}", "o/r")]
                ),
            )
        path = cmd[-1]
        assert "--cache" not in cmd and "-i" in cmd, cmd  # every single read is an ETag read
        body = json.dumps(self.rest[path.replace("{owner}/{repo}", "o/r")])
        tag = f'"{hashlib.sha1(body.encode()).hexdigest()}"'
        if f"If-None-Match: {tag}" in cmd:
            self.free += 1  # gh exits 1 on a 304, printing the status line with -i
            raise subprocess.CalledProcessError(
                1, cmd, output="HTTP/2.0 304 Not Modified\n\n", stderr="gh: HTTP 304"
            )
        self.spent += 1
        return subprocess.CompletedProcess(cmd, 0, stdout=f"HTTP/2.0 200 OK\nEtag: {tag}\n\n{body}")

    def round_cost(self, poll: Any) -> int:
        """The quota one more poll spends."""
        before = self.spent
        poll()
        return self.spent - before


def pull(updated: str = "t0") -> dict[str, Any]:
    return {"head": {"sha": HEAD}, "base": {"ref": "main"}, "state": "open", "updated_at": updated}


def rest_answers(**more: Any) -> dict[str, Any]:
    return {
        "repos/o/r/pulls/5": pull(),
        f"repos/o/r/git/commits/{HEAD}": {
            "tree": {"sha": TREE},
            "committer": {"date": "2026-01-01T10:00:00Z"},
        },
        f"repos/o/r/git/matching-refs/heads/loop-gate/{TREE}-": [],
        f"repos/o/r/commits/{HEAD}/statuses?per_page=100": [],
        f"repos/o/r/commits/{HEAD}/check-runs?per_page=100": {
            "check_runs": [{"name": "ci", "status": "queued"}]
        },
        f"repos/o/r/commits/{HEAD}/status": {"state": "pending"},
        "repos/o/r/issues/5/comments": [],
        "repos/o/r/pulls/5/reviews": [],
        **more,
    }


def test_gate_wait_spends_nothing_while_the_pr_is_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hub = GitHub(monkeypatch, rest_answers(), {})
    end = lambda: oa.time.monotonic() + 30
    first = hub.round_cost(lambda: oa.gate_outcome(5, end()))
    assert first == 4  # the pull, its commit, the record refs, the statuses: plain reads
    assert [hub.round_cost(lambda: oa.gate_outcome(5, end())) for _ in range(ROUNDS)] == [
        0
    ] * ROUNDS
    assert (
        hub.free == 3 * ROUNDS
    )  # three ETag reads a round, each a 304 (the commit is kept for good)
    hub.rest[f"repos/o/r/commits/{HEAD}/statuses?per_page=100"] = [
        {"context": "gate", "state": "success", "created_at": "2026-01-01T11:00:00Z"}
    ]
    assert oa.gate_outcome(5, end()) == (0, f"PR #5 head {HEAD}: passed, gate status: ")
    assert hub.spent == first + 1  # the status that moved, alone


def test_verdict_wait_spends_nothing_while_the_pr_is_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hub = GitHub(monkeypatch, rest_answers(), {})
    seen: dict = {}
    poll = lambda: oa.verdict_outcome(5, oa.time.monotonic() + 30, None, seen)
    hub.round_cost(poll)
    assert [hub.round_cost(poll) for _ in range(ROUNDS)] == [0] * ROUNDS


def test_checks_wait_reads_graphql_only_once_something_moved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pending = {"state": "OPEN", "statusCheckRollup": [{"name": "ci", "status": "IN_PROGRESS"}]}
    hub = GitHub(monkeypatch, rest_answers(), pending)
    costs: list[int] = []

    def sleep(
        _: float,
    ) -> None:  # each sleep ends a round: note its cost, and turn the check green after ROUNDS
        costs.append(hub.spent)
        if len(costs) == ROUNDS:
            hub.rest[f"repos/o/r/commits/{HEAD}/check-runs?per_page=100"] = {
                "check_runs": [{"name": "ci", "status": "completed", "conclusion": "success"}]
            }
            hub.view = {
                "state": "OPEN",
                "statusCheckRollup": [
                    {"name": "ci", "status": "COMPLETED", "conclusion": "SUCCESS"}
                ],
            }

    monkeypatch.setattr(oa.time, "sleep", sleep)
    assert oa.wait_for(None, None, 5, "checks", 10_000.0) == (0, "PR #5 checks green (1)")
    per_round = [b - a for a, b in itertools.pairwise(costs)]
    assert costs[0] == 4  # the first round: three plain REST reads and one GraphQL read
    assert per_round == [0] * (ROUNDS - 1)  # quiet rounds: three 304s each, no GraphQL
    assert (
        hub.spent - costs[-1] == 2
    )  # the round after the move: the check runs that moved, one GraphQL read


def test_a_failed_read_after_an_etag_moved_is_made_again(monkeypatch: pytest.MonkeyPatch) -> None:
    """The pull's ETag moved, then the GraphQL read failed: the next round reads GraphQL again, though every REST
    read now answers 304."""
    hub = GitHub(monkeypatch, rest_answers(), {"state": "MERGED"})
    real, failed = hub.run, []

    def run(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        if cmd[1] == "pr" and not failed:
            failed.append(1)
            raise subprocess.CalledProcessError(1, cmd, stderr="connection reset")
        return real(cmd, **kw)

    monkeypatch.setattr(oa.subprocess, "run", run)
    monkeypatch.setattr(oa.time, "sleep", lambda _: None)
    assert oa.wait_for(None, None, 5, "merged", 10_000.0) == (0, "PR #5 merged")


def test_required_pending_spends_nothing_while_rules_and_runs_are_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rule = {
        "type": "required_status_checks",
        "parameters": {"required_status_checks": [{"context": "ci"}]},
    }
    hub = GitHub(monkeypatch, rest_answers(**{"repos/o/r/rules/branches/main": [rule]}), {})
    info = {"state": "open", "sha": HEAD, "base": "main"}
    hub.rest[f"repos/o/r/commits/{HEAD}/check-runs"] = {
        "check_runs": [{"name": "ci", "status": "queued"}]
    }
    assert hub.round_cost(lambda: oa.required_pending(info, "o/r")) == 2
    assert [hub.round_cost(lambda: oa.required_pending(info, "o/r")) for _ in range(ROUNDS)] == [
        0
    ] * ROUNDS
