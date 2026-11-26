"""The supervisor sets an issue's `Session` field from the `Session:` line of its claim record (#2677).

The seam: ``gh`` faked to serve issue 5's REST read, and gatekeeper's ``issue_field`` and ``set_issue_field`` faked as a
module that records its writes, so the round runs as it would on a host where GraphQL works."""

import json
import os
from types import SimpleNamespace

import pytest
from test_omnigent_agent import omnigent_agent

LINK = "https://example.test/c/lead-1"
OTHER = "https://example.test/c/lead-0"


def claim(issue: int, link: str = LINK, body: str = "") -> dict:
    record = f"Assigned: @ann\n\n<details><summary>Details</summary>\n\nBy: loop\nPR: #7\nSession: {link}\n\n</details>"
    return {
        "body": body or record,
        "issue_url": f"https://api.github.com/repos/o/r/issues/{issue}",
    }


class Host:
    """``gh`` and gatekeeper's two field calls for repo o/r: ``values`` is each issue's current `Session` value."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, field: str | None = "FIELD") -> None:
        self.values: dict[int, str | None] = {5: None}
        self.pulls: set[int] = set()
        self.reads: list[int] = []
        self.looked: list[int] = []
        self.writes: list[tuple[str, str, str]] = []
        self.field = field
        self.refuse = 0  # the next writes that fail
        gatekeeper = SimpleNamespace(issue_field=self.issue_field, set_issue_field=self.set)
        monkeypatch.setattr(omnigent_agent, "gh", self.gh)
        monkeypatch.setattr(omnigent_agent, "_load_gatekeeper", lambda: gatekeeper)

    def gh(self, *args: str, timeout: float = 0) -> str:
        number = int(args[-1].rsplit("/", 1)[1])
        self.reads.append(number)
        have = self.values.get(number)
        body: dict = {"number": number}
        if have is not None:
            body["issue_field_values"] = [{"issue_field_name": "Session", "value": have}]
        if number in self.pulls:
            body["pull_request"] = {}
        return json.dumps(body)

    def issue_field(self, number: int, name: str) -> tuple[str | None, str]:
        self.looked.append(number)
        return self.field, f"ISSUE_{number}"

    def set(self, issue: str, field: str, text: str) -> None:
        if self.refuse:
            self.refuse -= 1
            raise RuntimeError("HTTP 502")
        self.writes.append((issue, field, text))


def noted(*comments: dict) -> dict:
    memo: dict = {}
    for c in comments:
        omnigent_agent.session_note(memo, c)
    return memo


def test_a_claim_record_naming_a_session_and_an_empty_field_is_written(monkeypatch) -> None:
    host = Host(monkeypatch)
    memo = noted(claim(5))
    assert omnigent_agent.session_field_round("o/r", memo) is None
    assert host.writes == [("ISSUE_5", "FIELD", LINK)]
    assert memo["session_fields"] == {}  # done: not read again


def test_a_field_that_differs_is_replaced_and_the_newest_record_wins(monkeypatch) -> None:
    host = Host(monkeypatch)
    host.values[5] = "https://example.test/c/old"
    omnigent_agent.session_field_round("o/r", noted(claim(5, OTHER), claim(5, LINK)))
    assert host.writes == [("ISSUE_5", "FIELD", LINK)]


def test_a_field_already_equal_is_not_written(monkeypatch) -> None:
    host = Host(monkeypatch)
    host.values[5] = LINK
    memo = noted(claim(5))
    omnigent_agent.session_field_round("o/r", memo)
    assert host.writes == [] and host.looked == [] and memo["session_fields"] == {}


def test_an_account_without_the_field_gets_no_write_one_note_and_no_repeat_lookup(
    monkeypatch,
) -> None:
    host = Host(monkeypatch, field=None)
    host.values[6] = None
    memo = noted(claim(5), claim(6))
    note = omnigent_agent.session_field_round("o/r", memo)
    assert note and "no `Session` issue field" in note and host.writes == []
    assert omnigent_agent.session_field_round("o/r", memo) is None
    assert host.looked == [5] and host.reads == [
        5
    ]  # nothing asked again for the second issue or poll


def test_a_pull_request_and_a_record_naming_no_session_are_left_alone(monkeypatch) -> None:
    host = Host(monkeypatch)
    host.pulls.add(7)
    memo = noted(
        claim(7), claim(5, body="Assigned: @ann\n\n<details>\n\nBy: loop\nPR: #7\n\n</details>")
    )
    omnigent_agent.session_field_round("o/r", memo)
    assert host.writes == [] and host.looked == [] and list(memo["session_fields"]) == []


def test_a_failed_write_is_tried_at_the_next_polls_then_left(monkeypatch) -> None:
    host = Host(monkeypatch)
    host.refuse = 3
    memo = noted(claim(5))
    for _ in range(2):
        assert "not set" in (omnigent_agent.session_field_round("o/r", memo) or "")
        assert "5" in memo["session_fields"]
    omnigent_agent.session_field_round("o/r", memo)
    assert host.writes == [] and memo["session_fields"] == {}


def test_a_rate_limit_keeps_the_record_for_the_next_poll(monkeypatch) -> None:
    Host(monkeypatch)

    def limited(*args: str, timeout: float = 0) -> str:
        raise omnigent_agent.RateLimited("gh api: API rate limit exceeded", 0.0)

    memo = noted(claim(5))
    monkeypatch.setattr(omnigent_agent, "gh", limited)
    with pytest.raises(omnigent_agent.RateLimited):
        omnigent_agent.session_field_round("o/r", memo)
    assert memo["session_fields"]["5"]["tries"] == 0


def test_the_round_names_the_repo_to_gatekeeper_and_restores_the_environment(
    monkeypatch,
) -> None:
    host = Host(monkeypatch)
    monkeypatch.delenv("GH_REPO", raising=False)
    seen: list[str | None] = []
    monkeypatch.setattr(
        host,
        "issue_field",
        lambda n, name: (seen.append(os.environ.get("GH_REPO")), ("FIELD", "I"))[1],
    )
    gk = SimpleNamespace(issue_field=host.issue_field, set_issue_field=host.set)
    monkeypatch.setattr(omnigent_agent, "_load_gatekeeper", lambda: gk)
    omnigent_agent.session_field_round("o/r", noted(claim(5)))
    assert seen == ["o/r"] and "GH_REPO" not in os.environ


def test_the_queue_read_keeps_the_claim_records_it_lists(monkeypatch) -> None:
    """No call of its own: the comments the supervisor already reads carry the record."""
    monkeypatch.setattr(omnigent_agent, "rest_pages", lambda path, *a, **k: [claim(5)])
    memo: dict = {}
    omnigent_agent.queue_read("o/r", memo)
    assert memo["session_fields"] == {"5": {"link": LINK, "tries": 0}}
