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
    emit = approvals.loop_events().emit

    def spy(kind: str, branch: str, state: str, **kw: Any) -> str:
        ends.append((state, None, lands["pulls"][7]["state"]))
        return emit(kind, branch, state, **kw)

    monkeypatch.setattr(approvals.loop_events(), "emit", spy)
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
        result["code"] = approvals.loop_events().wait(
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

        monkeypatch.setattr(approvals.loop_events(), "emit", boom)
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
