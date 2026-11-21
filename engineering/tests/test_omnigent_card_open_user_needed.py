"""omnigent_agent.py supervise: a lead whose turn ends USER NEEDED with its question card open is recorded, not posted;
with no card it still posts (the unasked event) (#1575)."""

from test_omnigent_agent import (
    Lead,
    ending,
    events_of,
    following,
    omnigent_agent,
    posted,
    skewed,
    supervised,
    told,
)

CARD = {
    "elicitation_id": "q1",
    "params": {
        "policy_name": "sys_ask_user_question",
        "ask_user_question": {"questions": [{"question": "Which base?"}]},
        "message": "Which base?",
    },
}


def run(tmp_path, monkeypatch, pending):
    registry = following(tmp_path)
    monkeypatch.setattr(omnigent_agent, "PROMPT_CONFIRM_SECONDS", 0.0)
    offset = skewed(monkeypatch)
    og = Lead(told("brief", 60), ending("USER NEEDED: which base?", 5))
    og.snap = {"host_id": "h", "pending_elicitations": pending}

    def later(poll):
        offset[0] = {1: 30.0, 2: 61.0}.get(poll, 400.0)

    supervised(og, registry, monkeypatch, 3, later, notify="cos", console=True)
    return [(e["kind"], e["action"]) for e in events_of(registry)], posted(og)


def test_card_open_records(tmp_path, monkeypatch):
    routed, posts = run(tmp_path, monkeypatch, [CARD])
    assert ("ended", "record") in routed
    assert not any("USER NEEDED" in p for p in posts)


def test_no_card_still_posts(tmp_path, monkeypatch):
    routed, posts = run(tmp_path, monkeypatch, [])
    assert routed and routed[0][0] == omnigent_agent.UNASKED
    assert posts
