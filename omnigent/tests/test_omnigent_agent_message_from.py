"""Messages the script sends open with the ``[Message from …]`` line the web chat draws as a message row (#3001)."""

from pathlib import Path

import pytest
import test_omnigent_agent as base

omnigent_agent = base.omnigent_agent
Omnigent = omnigent_agent.Omnigent
SID = "s1"


class Wire(Omnigent):
    """The real ``Omnigent`` over an in-memory server: a posted message lands as a user item at once."""

    def __init__(self) -> None:  # no config, no network
        self.base, self.host_id, self._token, self.loops = "https://og.test", "h", "", {}
        self.items_: list[dict] = []
        self.posted: list[str] = []

    def call(self, method, path, body=None, **kw):
        if method == "POST" and path.endswith("/events"):
            text = body["data"]["content"][0]["text"]
            self.posted.append(text)
            self.items_.append(
                {
                    "id": f"i{len(self.items_)}",
                    "type": "message",
                    "role": "user",
                    "created_at": 1.0,
                    "content": [{"type": "input_text", "text": text}],
                }
            )
            return {}
        if path.split("?")[0].endswith("/items"):
            return {"data": list(reversed(self.items_))}
        return {"id": SID, "status": "idle", "runner_online": True, "pending_inputs": []}


@pytest.fixture
def wire(monkeypatch: pytest.MonkeyPatch) -> Wire:
    monkeypatch.setattr(omnigent_agent, "own_id", lambda: "m1")
    monkeypatch.setattr(omnigent_agent.time, "sleep", lambda s: None)
    return Wire()


def first(text: str) -> str:
    return text.split("\n", 1)[0]


def test_a_relay_opens_with_the_message_from_line(wire: Wire) -> None:
    omnigent_agent.relay(wire, SID, "please look at the PR", 1.0)
    assert first(wire.posted[0]) == "[Message from session m1]"
    assert "please look at the PR" in wire.posted[0]


def test_a_supervisor_nudge_opens_with_the_message_from_line(wire: Wire) -> None:
    omnigent_agent.send_to_confirm(wire, SID, omnigent_agent.NO_REPORT + " Post it now.")
    assert first(wire.posted[0]) == "[Message from session m1]"
    assert omnigent_agent.NO_REPORT in wire.posted[0]


def test_a_revive_line_opens_with_the_message_from_line(wire: Wire) -> None:
    wire.send(SID, omnigent_agent.revive_line(Path("/r.md"), []))
    assert first(wire.posted[0]) == "[Message from session m1]"
    assert omnigent_agent.REVIVED in wire.posted[0]


def test_a_brief_opens_with_the_message_from_line(wire: Wire) -> None:
    outcome, _ = omnigent_agent.send(wire, SID, "Work on #1. Your brief: do it", None, 1.0)
    assert outcome == "delivered"
    assert first(wire.posted[0]) == "[Message from session m1]"


def test_with_no_sender_session_the_label_is_supervisor(
    wire: Wire, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(omnigent_agent, "own_id", lambda: "")
    wire.send(SID, "hello")
    assert wire.posted == ["[Message from Supervisor]\nhello"]


def test_prefixed_text_is_not_prefixed_again(wire: Wire) -> None:
    wire.send(SID, "hello")
    wire.send(SID, wire.posted[0])  # a relay of an already-sent message
    wire.send(SID, "[Message from session abc]\nhi")
    assert wire.posted == [
        "[Message from session m1]\nhello",
        "[Message from session m1]\nhello",
        "[Message from session abc]\nhi",
    ]


def test_send_to_confirm_still_confirms_a_delivered_prefixed_message(wire: Wire) -> None:
    outcome, posted = omnigent_agent.send(wire, SID, "ping", None, 1.0)
    assert (outcome, posted) == ("delivered", True)
    assert wire.posted == ["[Message from session m1]\nping"]
    # the same words again are the copy already there, found through the prefix
    assert omnigent_agent.send(wire, SID, "ping", None, 1.0) == ("already", False)
    assert len(wire.posted) == 1
    pending = {"pending_inputs": [{"content": [{"type": "input_text", "text": wire.posted[0]}]}]}
    assert omnigent_agent.queued(pending, "ping")


def test_the_supervisor_treats_its_own_prefixed_lines_as_its_own() -> None:
    wrapped = omnigent_agent.prefixed("Supervisor: nudge", "m1")
    assert omnigent_agent.agent_posted(wrapped)
    assert omnigent_agent.agent_posted("[Message from Supervisor]\nWork on #1. Your brief: x")
    assert omnigent_agent.agent_posted("[Message from build bot]\nanything")
    assert not omnigent_agent.agent_posted("Work on #35 next")
    assert omnigent_agent.unwrapped(wrapped).startswith(omnigent_agent.OWN_LINES)
    revive = omnigent_agent.prefixed(omnigent_agent.REVIVED, "m1")
    item = {"type": "message", "role": "user", "content": [{"text": revive}]}
    assert not omnigent_agent.instruction(item, "resume")


def wire_item(text: str) -> dict:
    return {
        "type": "message",
        "role": "user",
        "created_at": 5.0,
        "content": [{"type": "input_text", "text": text}],
    }


def test_a_managers_park_relay_is_still_a_park_after_the_prefix(wire: Wire) -> None:
    wire.send(SID, "[relayed by manager]\nPark: paused")
    assert wire.posted[0].startswith("[Message from session m1]\n[relayed by manager]")
    assert omnigent_agent.told_park(wire_item(wire.posted[0]))
    assert not omnigent_agent.told_park(wire_item("[Message from session m1]\nsay Park: now"))


def test_restart_recovery_finds_a_sent_supervisor_batch_in_history_and_pending(wire: Wire) -> None:
    wire.send(SID, "Supervisor [act] b-123: 1 event")
    found = lambda i: omnigent_agent.names_batch(i, "b-123")
    assert omnigent_agent.in_history(wire, SID, found, 0.0)  # in the message history
    held = wire_item(wire.posted[0])
    wire.items_.clear()
    assert not omnigent_agent.in_history(wire, SID, found, 0.0)
    wire.info = lambda sid: {"pending_inputs": [held]}  # type: ignore[method-assign]
    assert omnigent_agent.in_history(wire, SID, found, 0.0)  # taken, still pending
