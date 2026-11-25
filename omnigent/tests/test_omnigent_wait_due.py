"""A PR waiting on another agent tree's go carries a ``Waiting on:`` record with a deadline; past it, the supervisor of the
agent tree that owns the PR raises one event to its owner (#2501).

The seam is the one of the queue tests: ``gh`` faked to serve repo o/r's issue comments and a PR's own comments, the
Omnigent server faked as a fleet of sessions."""

import re

from test_omnigent_agent import events_of
from test_omnigent_queue_rejects import GitHub, acts, fleet, iso, owner_comment, run

HOUR = 3600.0


def waiting_comment(
    cid: int, pr: int, due_in: float, what: str = "the other agent tree's go"
) -> dict:
    """The record gatekeeper's ``record waiting`` writes: ``Waiting on: <what>``, its deadline folded under it."""
    deadline = iso(-due_in).replace("+00:00", "Z")[:19] + "Z"
    body = f"Waiting on: {what}\n\n<details><summary>Details</summary>\n\nDeadline: {deadline}\n\n</details>\n"
    return {
        "id": cid,
        "issue_url": f"https://api.github.com/repos/o/r/issues/{pr}",
        "user": {"login": "ci-account"},
        "updated_at": iso(30.0),
        "body": body,
    }


def clearing_comment(cid: int, pr: int, due_in: float) -> dict:
    cleared = waiting_comment(cid, pr, due_in)
    # as `--clear` writes it: a `Cleared:` line and no deadline
    cleared["body"] = re.sub(r"Deadline: \S+", "Cleared: 2026-11-25T10:00:00Z", cleared["body"])
    cleared["updated_at"] = iso(10.0)
    return cleared


def raised(og) -> list[str]:
    return [t for s, t in og.inbox if "waited on" in t]


def test_a_record_past_its_deadline_raises_one_event_to_its_owner(tmp_path, monkeypatch) -> None:
    registry, og = fleet(tmp_path)
    gh = GitHub(monkeypatch)
    record = waiting_comment(5, 12, due_in=-2 * HOUR)
    gh.comments.append(record)
    gh.pr_comments[12] = [owner_comment("a"), record]
    run(og, registry, monkeypatch, 5)
    [text] = raised(og)
    assert "o/r#12 has waited on the other agent tree's go past its deadline" in text
    assert [e["session"] for e in events_of(registry) if e["kind"] == "wait-due"] == ["a"]


def test_a_cleared_record_raises_nothing(tmp_path, monkeypatch) -> None:
    """Cleared before the poll that finds it due (it is read in the listing), and cleared after the listing took it
    (the PR's own comments are read before the event is raised)."""
    registry, og = fleet(tmp_path)
    gh = GitHub(monkeypatch)
    gh.comments += [
        waiting_comment(5, 12, due_in=-2 * HOUR),
        clearing_comment(6, 12, due_in=-2 * HOUR),
    ]
    gh.pr_comments[12] = [owner_comment("a"), *gh.comments]
    gh.comments.append(waiting_comment(7, 13, due_in=-2 * HOUR))
    gh.pr_comments[13] = [
        owner_comment("a"),
        waiting_comment(7, 13, due_in=-2 * HOUR),
        clearing_comment(8, 13, due_in=-2 * HOUR),
    ]
    # a control that is still waiting, so the test fails where nothing is ever raised
    gh.comments.append(waiting_comment(9, 14, due_in=-2 * HOUR))
    gh.pr_comments[14] = [owner_comment("a"), gh.comments[-1]]
    run(og, registry, monkeypatch, 4)
    [text] = raised(og)
    assert "o/r#14 has waited" in text
    assert len([e for e in events_of(registry) if e["kind"] == "wait-due"]) == 1


def test_a_record_not_yet_due_raises_nothing(tmp_path, monkeypatch) -> None:
    registry, og = fleet(tmp_path)
    gh = GitHub(monkeypatch)
    gh.comments.append(waiting_comment(5, 12, due_in=HOUR))
    gh.pr_comments[12] = [owner_comment("a"), gh.comments[0]]
    run(og, registry, monkeypatch, 3)
    assert not raised(og) and not [c for c in gh.calls if "issues/12/comments" in " ".join(c)]


def test_the_other_agent_trees_pr_raises_no_event_here(tmp_path, monkeypatch, capsys) -> None:
    """Its Owner record names a session this server does not list: its own supervisor raises it, this one says so once."""
    registry, og = fleet(tmp_path)
    gh = GitHub(monkeypatch)
    gh.comments.append(waiting_comment(5, 12, due_in=-2 * HOUR))
    gh.pr_comments[12] = [owner_comment("gone-session"), gh.comments[0]]
    run(og, registry, monkeypatch, 4)
    assert not raised(og) and not acts(og, "o/r#12")
    assert capsys.readouterr().out.count("o/r#12 waits past its deadline: owned elsewhere") == 1


def test_a_project_with_no_waiting_record_reads_and_raises_nothing_more(
    tmp_path, monkeypatch
) -> None:
    """One agent tree, no records: the supervisor makes no call about PR comments and raises no event."""
    registry, og = fleet(tmp_path)
    gh = GitHub(monkeypatch)
    run(og, registry, monkeypatch, 3)
    assert not [
        c
        for c in gh.calls
        if any("/issues/" in a and "/comments" in a and "issues/comments" not in a for a in c)
    ]
    assert not [e for e in events_of(registry) if e["kind"] == "wait-due"]


def test_the_event_names_no_session_host_or_link(tmp_path, monkeypatch) -> None:
    registry, og = fleet(tmp_path)
    gh = GitHub(monkeypatch)
    gh.comments.append(waiting_comment(5, 12, due_in=-2 * HOUR))
    gh.pr_comments[12] = [owner_comment("a"), gh.comments[0]]
    run(og, registry, monkeypatch, 2)
    [text] = raised(og)
    assert "/c/" not in text and "http" not in text
