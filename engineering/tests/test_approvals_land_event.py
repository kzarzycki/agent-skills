"""approvals.py: `land` writes the `land` event of each PR's branch (#1378): waiting, ok, failed; events.md is the contract."""

from __future__ import annotations

import io
import json
import threading
import time as real_time
from typing import Any

import pytest
from approvals_harness import (
    approvals,
    git_in,
    lands,  # noqa: F401
)

# origin's pre-receive hook as a host with push access has it: events may be rewritten, the lock only moves forward
PERMIT_EVENTS = """#!/bin/sh
zero=0000000000000000000000000000000000000000
while read old new ref; do
  case "$ref" in refs/heads/loop-landing/*) ;; *) continue ;; esac
  if [ "$new" = "$zero" ]; then echo "refused: delete of $ref" >&2; exit 1; fi
  if [ "$old" != "$zero" ] && ! git merge-base --is-ancestor "$old" "$new"; then
    echo "refused: non-fast-forward of $ref" >&2; exit 1
  fi
done
"""
LOCK = approvals.LOCK.format("main")
COMMENT_URL = "https://example.test/pull/{}#issuecomment-1"


@pytest.fixture
def events_pushed(lands: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """`lands` on an origin that accepts a rewritten `refs/loop/*`, a comment URL as GitHub returns it, and the grace
    before a merged PR's refs go set to `grace`; `event(branch)` is the event origin holds, None when it holds none."""
    hook = lands["origin"] / "hooks" / "pre-receive"
    hook.write_text(PERMIT_EVENTS)
    hook.chmod(0o755)
    posted = approvals.comment

    def comment(number: int, body: str) -> str:
        posted(number, body)
        return COMMENT_URL.format(number)

    monkeypatch.setattr(approvals, "comment", comment)
    monkeypatch.setattr(approvals, "EVENT_GRACE", 0)

    def event(branch: str) -> dict[str, Any] | None:
        ref = f"refs/loop/land/{branch}"
        if not git_in(lands["origin"], "for-each-ref", ref).strip():
            return None
        return json.loads(git_in(lands["origin"], "show", f"{ref}:event.json"))

    lands["event"] = event
    return lands


def refs_gone(lands: dict[str, Any], limit: float = 10) -> bool:
    """Whether no `refs/loop/*` is left on origin or in the clone, within `limit` seconds (the clear is its own process)."""
    end = real_time.monotonic() + limit
    while real_time.monotonic() < end:
        if (
            not git_in(lands["origin"], "for-each-ref", "refs/loop").strip()
            and not git_in(lands["work"], "for-each-ref", "refs/loop").strip()
        ):
            return True
        real_time.sleep(0.1)
    return False


class Clock:
    """A stubbed `time` for approvals: `sleep` moves `monotonic` by what it is asked, then runs `tick(now)`."""

    def __init__(self) -> None:
        self.now, self.tick, self.slept = 0.0, lambda _now: None, 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        assert self.slept < 10_000, "the wait never ends"
        self.slept += seconds
        self.now += seconds
        self.tick(self.now)

    def __getattr__(self, name: str) -> Any:
        return getattr(real_time, name)


def hold_lock(lands: dict[str, Any]) -> str:
    """Another land's HELD lock, taken now, naming no PR."""
    work = lands["work"]
    empty = git_in(work, "hash-object", "-t", "tree", "-w", "/dev/null").strip()
    commit = git_in(
        work, "commit-tree", "-m", f"{approvals.HELD} [skip ci]\n\npid 1, beats, nonce a", empty
    ).strip()
    git_in(work, "push", "-q", "origin", f"{commit}:{LOCK}")
    return commit


def free_lock(lands: dict[str, Any]) -> None:
    work, tip = lands["work"], git_in(lands["origin"], "rev-parse", LOCK).strip()
    empty = git_in(work, "hash-object", "-t", "tree", "-w", "/dev/null").strip()
    commit = git_in(
        work, "commit-tree", "-p", tip, "-m", f"{approvals.FREE} [skip ci]\n\nnonce b", empty
    ).strip()
    git_in(work, "push", "-q", "origin", f"{commit}:{LOCK}")


def test_land_wait_beats_waiting(
    events_pushed: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Blocked on a held lock, `land --wait` rewrites its `waiting` event at each poll; the lock's own tip stays
    what the holder wrote, and the PR lands once the lock is free."""
    lands = events_pushed
    clock = Clock()
    monkeypatch.setattr(approvals, "time", clock)
    monkeypatch.setattr(approvals, "QUEUE_POLL", approvals.POLL)
    lands["open"](7, {"7.txt": "7\n"})
    held = hold_lock(lands)
    seen: list[dict[str, Any]] = []

    def tick(now: float) -> None:
        event = lands["event"]("pr7")
        if event and (not seen or seen[-1]["seq"] != event["seq"]):
            seen.append(event)
        # the reference: the lock is still the holder's own tip while the land beats
        if len(seen) < 3:
            assert git_in(lands["origin"], "rev-parse", LOCK).strip() == held
        else:
            free_lock(lands)

    clock.tick = tick
    code, lines = lands["land"]("7", "--wait")
    assert code == 0, lines
    assert [e["state"] for e in seen] == ["waiting"] * len(seen) and len(seen) >= 3
    assert [e["seq"] for e in seen] == list(range(seen[0]["seq"], seen[0]["seq"] + len(seen)))
    assert lands["merged"]() == ["7"]


def test_land_evicted_event(events_pushed: dict[str, Any]) -> None:
    """A PR red alone twice ends `failed`, its `url` the comment `land` wrote with the log's last lines."""
    lands = events_pushed
    lands["open"](7, {"red.txt": "red\n"})
    code, lines = lands["land"]()
    assert code == 1, lines
    # the reference: the draft state and the comment land already writes
    assert ("pr", "ready", "--undo", "7") in lands["calls"]
    [(_, body)] = [(n, b) for n, b in lands["comments"] if n == 7]
    assert body.startswith(approvals.EVICTED)
    event = lands["event"]("pr7")
    assert event and event["state"] == "failed" and event["url"] == COMMENT_URL.format(7)
    assert (event["seq"], event["beat_s"]) == (1, 300)


def test_land_merged_event_and_cleanup(
    events_pushed: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A merged PR's event ends `ok` (written once the PR is merged), and then its refs are gone, here and on origin."""
    lands = events_pushed
    lands["open"](7, {"7.txt": "7\n"})
    ends: list[tuple[str, dict[str, Any] | None, str]] = []
    emit = approvals.loop_events.emit

    def spy(kind: str, branch: str, state: str, **kw: Any) -> str:
        ends.append((state, None, lands["pulls"][7]["state"]))
        return emit(kind, branch, state, **kw)

    monkeypatch.setattr(approvals.loop_events, "emit", spy)
    code, lines = lands["land"]("7")
    assert code == 0, lines
    # the reference: the PR as GitHub reports it, merged, onto main's squash
    assert lands["pulls"][7]["state"] == "MERGED" and lands["main"]() == lands["squashes"][7]
    assert ends == [("ok", None, "MERGED")]
    assert refs_gone(lands)


def test_native_wait_follows_land(
    events_pushed: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`wait land <branch>` started before `land` exits 0 once the PR merges: the `ok` stays readable for the grace
    before its refs go, so a poll between the two finds it."""
    lands = events_pushed
    monkeypatch.setattr(approvals, "EVENT_GRACE", 4)
    lands["open"](7, {"7.txt": "7\n"})
    result: dict[str, Any] = {}
    out = io.StringIO()

    def wait() -> None:
        result["code"] = approvals.loop_events.wait(
            "land", "pr7", timeout=30, poll=0.2, cwd=lands["work"], out=out
        )

    waiter = threading.Thread(target=wait)
    waiter.start()
    real_time.sleep(0.5)
    assert waiter.is_alive()  # nothing was written yet: it waits
    code, lines = lands["land"]("7")
    waiter.join(timeout=30)
    assert code == 0, lines
    assert result == {"code": 0}, out.getvalue()
    assert out.getvalue().startswith("land pr7: ok")
    assert refs_gone(lands)


@pytest.mark.parametrize("how", ["push refused", "emit raises"])
@pytest.mark.parametrize(("files", "code"), [({"7.txt": "7\n"}, 0), ({"red.txt": "r\n"}, 1)])
def test_land_exit_codes_without_origin_push(
    lands: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    how: str,
    files: dict[str, str],
    code: int,
) -> None:
    """An origin that refuses the event's push (as a cloud session's proxy does), or an
    emit that raises, changes none of `land`'s exit codes: a merge is 0, an eviction 1."""
    if how == "push refused":
        hook = lands["origin"] / "hooks" / "pre-receive"
        hook.write_text(
            '#!/bin/sh\nwhile read old new ref; do case "$ref" in refs/loop/*) echo refused >&2; exit 1;; esac; done\n'
        )
        hook.chmod(0o755)
    else:

        def boom(*_a: Any, **_k: Any) -> str:
            raise OSError("no git")

        monkeypatch.setattr(approvals.loop_events, "emit", boom)
    monkeypatch.setattr(approvals, "EVENT_GRACE", 0)
    lands["open"](7, files)
    got, lines = lands["land"]("7")
    assert got == code, lines
    assert not git_in(lands["origin"], "for-each-ref", "refs/loop").strip()
    assert (("pr", "ready", "--undo", "7") in lands["calls"]) == (code == 1)


def test_land_wait_ceiling_asks_the_owner(
    events_pushed: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A wait that reaches its ceiling ends `needs-owner`, the whole question in `question.md`."""
    lands = events_pushed
    monkeypatch.setattr(approvals, "time", Clock())
    monkeypatch.setattr(approvals, "QUEUE_POLL", approvals.POLL)
    lands["open"](7, {"7.txt": "7\n"})
    hold_lock(lands)
    code, lines = lands["land"]("7", "--wait")
    assert code == approvals.WAITING, lines
    event = lands["event"]("pr7")
    assert event and event["state"] == "needs-owner"
    question = git_in(lands["origin"], "show", "refs/loop/land/pr7:question.md")
    assert "stopped after 2 hours" in question


def test_land_waiting_on_the_owners_go_ends_needs_owner(
    events_pushed: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A named PR held for the owner's go ends `needs-owner`, the line `land` prints as the question."""
    lands = events_pushed
    said = "PR #7 waits for the owner's go on its head (`approve merge 7`)"
    monkeypatch.setattr(approvals, "owner_waits", lambda *_a: [said])
    lands["open"](7, {"7.txt": "7\n"})
    code, lines = lands["land"]("7")
    assert code == approvals.WAITING and said in lines, lines
    event = lands["event"]("pr7")
    assert event and event["state"] == "needs-owner"
    assert git_in(lands["origin"], "show", "refs/loop/land/pr7:question.md") == said + "\n"


def check(lands: dict[str, Any], number: int, state: str) -> None:
    """PR `number`'s required `check` is now `state` (SUCCESS, or PENDING while it runs)."""
    nodes = lands["pulls"][number]["commits"]["nodes"][0]["commit"]["statusCheckRollup"]
    nodes["contexts"]["nodes"] = [
        {"__typename": "CheckRun", "name": "check", "status": "COMPLETED", "conclusion": state}
    ]


def batch_wait(
    lands: dict[str, Any], monkeypatch: pytest.MonkeyPatch, other: str
) -> list[dict[str, Any]]:
    """`land --wait 7 8` with PR 8's CI pending for three rounds; PR 7's event as each poll sees it. PR 7 is held for
    the owner's go (`other` is "owner") or merges in the first round ("merge")."""
    clock = Clock()
    monkeypatch.setattr(approvals, "time", clock)
    monkeypatch.setattr(approvals, "QUEUE_POLL", approvals.POLL)
    monkeypatch.setattr(approvals, "required_checks", lambda _base: {"check"})
    monkeypatch.setattr(
        approvals, "EVENT_GRACE", 5
    )  # the clear is its own process: it must not race the polls
    if other == "owner":
        monkeypatch.setattr(
            approvals,
            "owner_waits",
            lambda pull, *_a: ["PR #7 waits for the owner's go"] if pull["number"] == 7 else [],
        )
    lands["open"](7, {"7.txt": "7\n"})
    lands["open"](8, {"8.txt": "8\n"})
    check(lands, 8, "PENDING")
    seen: list[dict[str, Any]] = []

    def tick(now: float) -> None:
        if event := lands["event"]("pr7"):
            seen.append(event)
        if now >= 100:
            check(lands, 8, "SUCCESS")

    clock.tick = tick
    lands["land"]("7", "8", "--wait")
    return seen


def test_land_batch_wait_keeps_the_owners_question_of_a_pr_that_ended_its_round(
    events_pushed: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A PR held for the owner's go stays `needs-owner` while a PR of its batch waits on CI: the round's beat is for
    the PRs that wait, so a `wait land` polling between two rounds reads the question."""
    seen = batch_wait(events_pushed, monkeypatch, "owner")
    assert seen and {e["state"] for e in seen} == {"needs-owner"}, seen


def test_land_batch_wait_keeps_the_end_of_a_pr_that_merged_in_its_round(
    events_pushed: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A PR merged while another of its batch waits on CI stays `ok`, never beaten back to `waiting`."""
    seen = batch_wait(events_pushed, monkeypatch, "merge")
    assert events_pushed["merged"]()[:1] == ["7"]
    assert seen and {e["state"] for e in seen} == {"ok"}, seen


def test_land_beats_waiting_while_the_round_runs_its_gate(
    events_pushed: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A round holding the lock beats `waiting` from the lock's heartbeat, so a `wait land` never reads the
    minutes of a long gate as silence."""
    lands = events_pushed
    monkeypatch.setattr(approvals, "BEAT", 0.2)
    lands["open"](7, {"7.txt": "7\n"})
    beats: list[int] = []

    def slow_gate(*_a: Any, **_k: Any) -> tuple[int, bool]:
        real_time.sleep(1.5)
        event = lands["event"]("pr7")
        beats.append(event["seq"] if event and event["state"] == "waiting" else 0)
        return 0, False

    monkeypatch.setattr(approvals, "local_queue", slow_gate)
    code, lines = lands["land"]("7", "--wait")
    assert code == 0, lines
    assert beats and beats[0] >= 3, beats


def test_land_wait_ceiling_asks_about_no_merged_pr(
    events_pushed: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The 2-hour ceiling asks the owner about the PRs still open, not one that merged during the wait."""
    lands = events_pushed
    lands["open"](7, {"7.txt": "7\n"})
    lands["pulls"][7]["state"] = "MERGED"
    approvals.land_event_of(7, "needs-owner", "question\n")
    assert lands["event"]("pr7") is None


def test_land_draft_held_for_the_owners_go_ends_needs_owner(
    events_pushed: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A draft waiting for the owner's go (held before it is readied, so CI never starts first) ends `needs-owner`."""
    lands = events_pushed
    said = "PR #7 waits for the owner's go on its head (`approve merge 7`)"
    monkeypatch.setattr(approvals, "owner_waits", lambda *_a: [said])
    lands["open"](7, {"7.txt": "7\n"})
    lands["pulls"][7]["isDraft"] = True
    code, lines = lands["land"]("7")
    assert code == approvals.WAITING and said in lines, lines
    assert lands["pulls"][7]["isDraft"]
    event = lands["event"]("pr7")
    assert event and event["state"] == "needs-owner"
    assert git_in(lands["origin"], "show", "refs/loop/land/pr7:question.md") == said + "\n"


def test_land_merged_outside_land_ends_ok(
    events_pushed: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A PR the GitHub merge queue merged (or anyone merged) ends `ok` from the first land that reads it merged."""
    lands = events_pushed
    monkeypatch.setattr(approvals, "EVENT_GRACE", 3)
    lands["open"](7, {"7.txt": "7\n"})
    lands["pulls"][7]["state"] = "MERGED"
    code, lines = lands["land"]("7")
    assert code == 0, lines
    event = lands["event"]("pr7")
    assert event and event["state"] == "ok"
    assert refs_gone(lands)


@pytest.mark.parametrize("state", ["waiting", "ok", "needs-owner"])
def test_land_events_point_to_the_pr(
    events_pushed: dict[str, Any], monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    """`waiting`, `ok` and `needs-owner` carry the PR's URL (events.md's `land` row), read from the PR."""
    lands = events_pushed
    url = "https://example.test/pull/7"
    monkeypatch.setattr(approvals, "EVENT_GRACE", 3)
    lands["open"](7, {"7.txt": "7\n"})
    lands["pulls"][7]["url"] = url
    if state == "waiting":
        clock = Clock()
        monkeypatch.setattr(approvals, "time", clock)
        monkeypatch.setattr(approvals, "QUEUE_POLL", approvals.POLL)
        hold_lock(lands)
        beat: list[dict[str, Any]] = []
        clock.tick = lambda _now: beat.append(lands["event"]("pr7")) if not beat else None
        lands["land"]("7", "--wait")
        assert beat[0] and beat[0]["state"] == state and beat[0]["url"] == url
        return
    elif state == "ok":
        lands["land"]("7")
    else:
        monkeypatch.setattr(
            approvals, "owner_waits", lambda *_a: ["PR #7 waits for the owner's go"]
        )
        lands["land"]("7")
    event = lands["event"]("pr7")
    assert event and event["state"] == state and event["url"] == url


def test_the_pr_a_land_reads_carries_its_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """The `url` of a PR is read from GraphQL's PULL query and from REST's pull, whichever the session can reach."""
    assert " number url title " in approvals.github.PULL
    github = approvals.github
    found = {
        "node_id": "n",
        "number": 7,
        "html_url": "https://example.test/pull/7",
        "title": "t",
        "state": "open",
        "base": {"ref": "main", "repo": {"full_name": "o/r", "default_branch": "main"}},
        "head": {"ref": "pr7", "sha": "abc", "repo": {"full_name": "o/r"}},
    }
    monkeypatch.setattr(github, "rest", lambda _path: {"commit": {"sha": "b"}} | found)
    for name in ("rest_pages", "pr_changes"):
        monkeypatch.setattr(github, name, lambda *_a, **_k: [])
    for name in ("rest_notes", "rest_threads", "rest_authored", "rest_timeline", "rest_checks"):
        monkeypatch.setattr(github, name, lambda *_a, **_k: {})
    monkeypatch.setattr(github, "rest_latest", lambda *_a: [])
    monkeypatch.setattr(github, "rest_queue", lambda *_a: {})
    assert github.rest_pull(7)["url"] == "https://example.test/pull/7"


def test_comment_returns_the_url_github_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    """`comment` asks `gh api` for the new comment's `html_url` and returns it, newline trimmed."""
    calls: list[tuple[Any, ...]] = []

    def gh(*args: str, data: str | None = None) -> str:
        calls.append((args, data))
        return "https://example.test/pull/7#issuecomment-9\n"

    monkeypatch.setattr(approvals.github, "gh", gh)
    assert approvals.github.comment(7, "body") == "https://example.test/pull/7#issuecomment-9"
    [(args, data)] = calls
    assert args[-2:] == ("--jq", ".html_url") and data == "body"


def test_land_clears_a_merged_prs_refs_after_its_worktree_is_gone(
    events_pushed: dict[str, Any], monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """A land that `caught_up` moved to a fresh worktree ends and has it removed within the grace: the delayed clear
    still removes the refs, since it runs on the repository's git dir, not on the worktree."""
    lands = events_pushed
    monkeypatch.setattr(approvals, "EVENT_GRACE", 2)
    lands["open"](7, {"7.txt": "7\n"})
    fresh = tmp_path / "fresh"
    git_in(lands["work"], "worktree", "add", "-q", "--detach", str(fresh), "origin/main")
    monkeypatch.chdir(fresh)
    approvals.land_ended(lands["pulls"][7])
    assert lands["event"]("pr7")["state"] == "ok"
    monkeypatch.chdir(lands["work"])
    git_in(lands["work"], "worktree", "remove", "--force", str(fresh))
    assert refs_gone(lands)
