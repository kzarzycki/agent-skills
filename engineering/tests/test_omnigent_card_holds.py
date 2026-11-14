"""omnigent_agent.py: an open question card holds no input; a parked question or approval does (#977)."""

import pytest
import test_omnigent_agent as base
from test_omnigent_agent import no_model, no_sleep  # noqa: F401  (the fixtures apply here by name)

omnigent_agent = base.omnigent_agent

CARD = {"elicitation_id": "question_476b", "params": {"message": "Land it?"}}
PARKED = {
    "elicitation_id": "elicit_question_1",
    "params": {
        "message": "Which one?",
        "ask_user_question": {"questions": [{"question": "Which?"}]},
    },
}
APPROVAL = {
    "elicitation_id": "elicit_approval_1",
    "params": {"message": "Claude wants to call Bash"},
}
CARD_ANSWERABLE = {
    "elicitation_id": "question_9",
    "params": {"message": "Pick", "ask_user_question": {"questions": [{"question": "Pick?"}]}},
}


def fake(*prompts: dict, hold: int = 0) -> base.FakeOmnigent:
    og = base.FakeOmnigent(hold=hold)
    og.sessions["s1"] = []
    og.prompts = list(prompts)
    return og


def test_holds_input_by_kind() -> None:
    assert not omnigent_agent.holds_input(CARD)
    assert not omnigent_agent.holds_input(
        {"elicitation_id": "x", "params": {"policy_name": "sys_ask_user_question"}}
    )
    assert omnigent_agent.holds_input(PARKED)
    assert omnigent_agent.holds_input(APPROVAL)


def test_prompts_and_questions_ignore_a_card() -> None:
    info = {"pending_elicitations": [CARD, PARKED, APPROVAL]}
    assert omnigent_agent.prompts_of(info) == ["Which one?", "Claude wants to call Bash"]
    assert omnigent_agent.questions_of(info) == ["Which one?"]
    assert omnigent_agent.cards_of(info) == ["Land it?"]


def test_relay_delivers_past_a_card_but_queues_behind_a_parked_question() -> None:
    og = fake(CARD)
    assert omnigent_agent.relay(og, "s1", "hi", 0).endswith("delivered")
    with pytest.raises(omnigent_agent.Queued, match="behind a question"):
        omnigent_agent.relay(fake(PARKED, hold=10**6), "s1", "hi", 0)
    with pytest.raises(omnigent_agent.Queued, match="behind an approval prompt"):
        omnigent_agent.relay(fake(APPROVAL, hold=10**6), "s1", "hi", 0)
    with pytest.raises(omnigent_agent.Queued, match="until the session's current step ends"):
        omnigent_agent.relay(fake(CARD, hold=10**6), "s1", "hi", 0)


@pytest.mark.parametrize("held", [PARKED, APPROVAL])
def test_relay_skip_skips_a_held_prompt_not_a_card(held: dict) -> None:
    assert "skipped" in omnigent_agent.relay(fake(held), "s1", "x", 0, skip=True)
    assert "skipped" not in omnigent_agent.relay(fake(CARD), "s1", "x", 0, skip=True)


def test_relay_answer_still_answers_a_card() -> None:
    og = fake(CARD_ANSWERABLE)
    line = omnigent_agent.relay(og, "s1", "yes", 0, answer=True)
    assert "answered its open question" in line
    assert og.resolved == [("s1", "question_9", "accept", {"Pick?": "yes"})]


def test_approve_still_resolves_approvals_only() -> None:
    og = fake(CARD, APPROVAL)
    lines, _ = omnigent_agent.approve(og, "s1")
    assert [r[1] for r in og.resolved] == ["elicit_approval_1"] and len(lines) == 1


def test_reap_archives_a_session_with_only_a_card_and_keeps_one_with_a_parked_question() -> None:
    states = {"card": [CARD], "parked": [PARKED]}
    og = base.FakeOmnigent()
    og.info = lambda s: {"status": "idle", "title": s, "pending_elicitations": states[s]}  # type: ignore[method-assign]
    og.children = lambda p: list(states)  # type: ignore[attr-defined]
    lines, _ = omnigent_agent.reap(og, [], parent="p")
    assert og.archived == ["card"]
    assert lines[1] == "parked parked: kept (blocked on a prompt)"


def test_watch_status_shows_a_card_open_not_blocked() -> None:
    og = fake(CARD)
    info = {"status": "idle", "pending_elicitations": [CARD]}
    assert omnigent_agent.lead_status(info, [])["state"] != "blocked"
    assert (
        omnigent_agent.lead_status({**info, "pending_elicitations": [PARKED]}, [])["state"]
        == "blocked"
    )
    assert og.info("s1")["pending_elicitations"] == [CARD]
