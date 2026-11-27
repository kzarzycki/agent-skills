"""omnigent_agent.py supervise: the owner's own words in a followed session mark it ``direct``; a session's message
(a relay, a tool message, the supervisor, a brief) never does; an approval prompt and a long-open card are recorded, not
posted, unless steward mode is on (#2824)."""

from pathlib import Path

import pytest
import test_omnigent_agent as base  # the faked server, the supervisor loop
from test_omnigent_agent import no_model, no_sleep  # noqa: F401  (the fixtures apply here by name)

omnigent_agent = base.omnigent_agent
typed = base.typed


def fields(registry: Path, sid: str = "a") -> list[str]:
    [line] = [x for x in registry.read_text().splitlines() if x.startswith(f"{sid}=")]
    return line.split("\t")


def test_an_owner_message_marks_the_lead_direct_and_logs_it_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    registry = base.following(tmp_path)
    og = base.Lead(base.told("brief", 600), typed("how is it going?", 1))
    base.supervised(og, registry, monkeypatch, 3, notify="cos", console=True)
    assert "direct" in fields(registry)
    og.histories["a"].append(typed("and the tests?", 2))  # a second owner message
    base.supervised(og, registry, monkeypatch, 3, notify="cos", console=True)
    assert capsys.readouterr().out.count("marked direct") == 1


@pytest.mark.parametrize(
    "text",
    [
        omnigent_agent.RELAY_FROM.format(source="sync") + "\nhello",
        omnigent_agent.RELAYED.format(who="cos") + "\nhello",
        "[Message from session abc123]\nhello",
        "Supervisor [act] b-1: 1 event\nhello",
        "[System: sub-agent b finished] hello",
        "Work on #7. Your brief:\n\nhello",
    ],
)
def test_a_session_s_message_never_marks_a_lead_direct(
    text: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = base.following(tmp_path)
    og = base.Lead(typed(text, 1))
    base.supervised(og, registry, monkeypatch, 3, notify="cos", console=True)
    assert "direct" not in fields(registry)


def test_a_message_with_a_sender_session_never_marks_a_lead_direct(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = base.following(tmp_path)
    og = base.Lead(typed("hello", 1, sender_session_id="s"))
    base.supervised(og, registry, monkeypatch, 3, notify="cos", console=True)
    assert "direct" not in fields(registry)


def test_direct_off_stays_off_until_a_newer_owner_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = base.following(tmp_path)
    og = base.Lead(typed("hello", 1))
    base.supervised(og, registry, monkeypatch, 3, notify="cos", console=True)
    assert "direct" in fields(registry)
    assert omnigent_agent.mark_direct(registry, "a", False)  # direct a --off
    base.supervised(og, registry, monkeypatch, 3, notify="cos", console=True)
    assert "direct" not in fields(registry)  # the message was seen already
    og.histories["a"].append(typed("one more thing", 2))
    base.supervised(og, registry, monkeypatch, 3, notify="cos", console=True)
    assert "direct" in fields(registry)


def test_owner_talked_does_not_count_a_tool_message_from_a_session() -> None:
    og = base.Fleet(a=[typed("[Message from session abc]\nstatus?", 1)], b=[typed("status?", 1)])
    assert not omnigent_agent.owner_talked(og, "a")
    assert omnigent_agent.owner_talked(og, "b")


STEWARD = "- **Steward mode**: **ON**, the chief of staff answers in the owner's name"


@pytest.mark.parametrize("kind", ["blocked", "card-waiting"])
def test_an_approval_or_a_waiting_card_is_recorded_unless_steward_mode_is_on(kind: str) -> None:
    def route(**event: object) -> str:
        return omnigent_agent.route({"kind": kind, **event}, lambda: pytest.fail("no model"))[1]

    assert route() == "record"
    assert route(steward=False) == "record"
    assert route(steward=True) == ("owner" if kind == "blocked" else "act")


def test_steward_mode_is_read_from_its_bullet_in_the_decisions() -> None:
    on = omnigent_agent.steward_on
    assert on(f"- Other rule\n{STEWARD}\n")
    assert not on("- **Steward mode**: **OFF**\n- **ON** is not it")
    assert not on("")
    assert not on("Steward mode ON")


def test_a_manager_the_owner_wrote_to_tells_only_its_waiters_when_its_turn_ends_done(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    leads = tmp_path / "app-leads.registry"
    leads.write_text(f"x={tmp_path / 'x.md'}\tfollow\n")
    registry = tmp_path / "registry"
    registry.write_text(
        f"a={tmp_path / 'a.md'}\tfollow\tleads={leads}\nb={tmp_path / 'b.md'}\tfollow\tafter=a\n"
    )
    og = base.Leads(
        a=[base.told("brief", 600), typed("let's talk about the plan", 1)],
        b=[base.told("brief", 600), base.ending("STILL WORKING: waiting on lead a", 5)],
        x=[base.told("brief", 600)],
    )

    def done(poll: int) -> None:
        if poll == 1:
            og.histories["a"].append(base.ending("DONE: plan agreed", 0))

    base.supervised(og, registry, monkeypatch, 3, done, notify="cos", console=True)
    assert "direct" in fields(registry)
    assert base.posted(og) == []
    assert [(s, t) for s, t in og.inbox] == [
        ("b", "Supervisor: a t-a, the lead you wait on, ended: DONE: plan agreed")
    ]
