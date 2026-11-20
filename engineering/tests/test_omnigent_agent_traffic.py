"""One notice per event: the supervisor stays silent on what the lead already has, and owner questions are cards (#1529)."""

import time
from pathlib import Path

import omnigent_agent
import pytest
import test_omnigent_agent as base
from test_omnigent_agent import COS, WORKER, Lead, ending, manager, supervised, told

WAIT = "STILL WORKING: waiting on the check. Report: m.md"
CARD = {
    "elicitation_id": "question_q1",
    "params": {"message": "pick one", "ask_user_question": True},
}
PR = {omnigent_agent.PR_LABEL: "o/r#7"}


def told_m(og: base.Leads) -> list[str]:
    return [t for s, t in og.inbox if s == "m" and "a session it started" in t]


def run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    worker: dict,
    history=(),
    live=None,
    said: str = "DONE: checked. Report: w.md",
):
    """A manager idle an hour with ``WORKER`` its child, shaped by ``worker`` and ending ``said``; ``history`` joins its
    lead's, ``live`` is the session list."""
    tmp_path.mkdir(exist_ok=True)
    gone = {"status": "idle", "updated_at": time.time() - 1300, **worker}
    registry, og = manager(tmp_path, WAIT, m={"status": "idle"}, **{WORKER: gone})
    og.histories[WORKER] = [ending(said, 1300)]
    og.histories["m"].extend(history)
    og.call = lambda method, path, *a: {"data": live or []}  # type: ignore[method-assign]
    supervised(og, registry, monkeypatch, 2, notify=COS, console=True, fyi="post")
    return og


def test_an_unread_done_and_a_failure_still_reach_the_lead_once(tmp_path, monkeypatch) -> None:
    assert len(told_m(run(tmp_path / "a", monkeypatch, {}))) == 1
    (tmp_path / "b").mkdir()
    og = run(tmp_path / "b", monkeypatch, {"status": "failed"})
    assert len(told_m(og)) == 1 and "failed" in told_m(og)[0]


def test_an_archived_worker_raises_no_alert(tmp_path, monkeypatch) -> None:
    assert told_m(run(tmp_path, monkeypatch, {"archived": True})) == []


def test_a_failed_worker_whose_pr_has_a_newer_worker_raises_no_alert(tmp_path, monkeypatch) -> None:
    old = {"status": "failed", "labels": PR, "created_at": 100.0}
    newer = [{"id": "n" * 32, "labels": PR, "created_at": 200.0}]
    assert told_m(run(tmp_path, monkeypatch, old, live=newer)) == []


def test_a_failed_worker_with_no_newer_worker_still_alerts(tmp_path, monkeypatch) -> None:
    old = {"status": "failed", "labels": PR, "created_at": 100.0}
    older = [{"id": "n" * 32, "labels": PR, "created_at": 50.0}]
    assert len(told_m(run(tmp_path, monkeypatch, old, live=older))) == 1


def test_a_turn_end_the_lead_has_read_raises_no_alert(tmp_path, monkeypatch) -> None:
    seen = [{**told("[notice] DONE", 1000), "id": "n1"}]  # arrived after the end, 1300 s ago
    assert told_m(run(tmp_path, monkeypatch, {}, history=seen)) == []


def test_a_failure_the_lead_has_read_still_alerts(tmp_path, monkeypatch) -> None:
    seen = [told("[notice] failed", 1000)]
    assert len(told_m(run(tmp_path, monkeypatch, {"status": "failed"}, history=seen))) == 1


def test_a_child_turn_end_waiting_on_an_open_owner_card_is_not_forwarded(
    tmp_path, monkeypatch
) -> None:
    ask = "USER NEEDED: pick one. Report: w.md"
    assert len(told_m(run(tmp_path / "a", monkeypatch, {}, said=ask))) == 1  # no card: still news
    card = {"pending_elicitations": [CARD]}
    assert told_m(run(tmp_path / "b", monkeypatch, card, said=ask)) == []


def test_a_followed_lead_ending_on_its_open_card_is_not_forwarded_but_without_one_is(
    tmp_path, monkeypatch
) -> None:
    def turn_ends(card: bool) -> list[str]:
        og = Lead(told("brief", 60), ending("USER NEEDED: pick one", 5))
        og.snap = {"status": "idle", **({"pending_elicitations": [CARD]} if card else {})}
        offset = base.skewed(monkeypatch)
        supervised(
            og,
            base.following(tmp_path / ("c" if card else "n")),
            monkeypatch,
            3,
            lambda poll: offset.__setitem__(0, poll * 400.0),
            notify="cos",
            console=True,
        )
        return [t for t in base.posted(og) if "turn ended" in t]

    for sub in ("c", "n"):
        (tmp_path / sub).mkdir()
    assert turn_ends(True) == []
    assert len(turn_ends(False)) == 1


def test_relay_refuses_a_message_carrying_an_owner_question(
    monkeypatch, capsys: pytest.CaptureFixture[str]
) -> None:
    og = base.FakeOmnigent()
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    for text in ("USER NEEDED: which one?", "ok\nQuestion for the owner: which?"):
        assert omnigent_agent.main(["relay", "s1", text]) == 1
        err = capsys.readouterr().err
        assert "relay refused" in err and "sys_ask_user_question" in err
    assert og.posts == 0


def test_withdraw_cancels_the_open_cards_only() -> None:
    og = base.FakeOmnigent()
    og.info = lambda sid: {  # type: ignore[method-assign]
        "pending_elicitations": [
            CARD,
            {"elicitation_id": "a1", "params": {"content_preview": "ls"}},
        ]
    }
    assert omnigent_agent.withdraw(og, "s") == [
        "session s: withdrew card question_q1: question_q1: pick one"
    ]
    assert og.resolved == [("s", "question_q1", "cancel", None)]
    og.info = lambda sid: {}  # type: ignore[method-assign]
    with pytest.raises(omnigent_agent.Fail):
        omnigent_agent.withdraw(og, "s")


def test_reap_force_finishes_a_replaced_worker_while_its_pr_is_open(monkeypatch) -> None:
    og = base.FakeOmnigent()
    monkeypatch.setattr(omnigent_agent, "pr_hold", lambda repo, pr: "o/r#7 is open")
    infos = {
        "old": {"labels": PR, "created_at": 100.0, "status": "failed"},
        "new": {"labels": PR, "created_at": 200.0, "status": "running"},
    }
    og.info = lambda sid: dict(infos[sid], id=sid)  # type: ignore[method-assign]
    og.call = lambda method, path, *a: {  # type: ignore[method-assign]
        "data": [dict(v, id=k) for k, v in infos.items()]
    }
    kept, _ = omnigent_agent.reap(og, ["old"])  # no force: still held
    assert og.archived == [] and "kept (o/r#7 is open)" in kept[0]
    omnigent_agent.reap(og, ["new"], force=True)  # the newest holds the PR
    assert og.archived == []
    omnigent_agent.reap(og, ["old"], force=True)
    assert og.archived == ["old"]
