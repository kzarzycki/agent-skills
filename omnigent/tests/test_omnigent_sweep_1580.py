"""omnigent_agent.py sweep: sessions idle over a day are archived through finish_delivered (#1580)."""

import json
import time
from pathlib import Path

import pytest
import test_omnigent_agent as base

omnigent_agent = base.omnigent_agent
DAY = 24 * 3600
CARD = {"elicitation_id": "question_1", "params": {"message": "Land it?"}}
OWNER = {
    "type": "message",
    "role": "user",
    "created_by": "owner@example.com",
    "content": [{"type": "input_text", "text": "how is it going?"}],
}


class Fake:
    """Sessions as the list and info show them; archive records, and the history is per session."""

    base = "http://omnigent.test"

    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}
        self.infos: dict[str, dict] = {}
        self.histories: dict[str, list[dict]] = {}
        self.archived: list[str] = []

    def add(
        self, sid: str, idle: float = 2 * DAY, labels: dict | None = None, **info: object
    ) -> str:
        self.rows[sid] = {
            "id": sid,
            "title": f"t-{sid}",
            "updated_at": time.time() - idle,
            "labels": labels or {},
        }
        self.infos[sid] = {"status": "idle", "labels": labels or {}, **info}
        self.histories.setdefault(sid, [])
        return sid

    def call(self, method: str, path: str, body: object = None) -> dict:
        assert (method, path) == ("GET", "/v1/sessions?kind=any&limit=1000"), path
        return {"data": [{**r, "archived": r["id"] in self.archived} for r in self.rows.values()]}

    def info(self, sid: str) -> dict:
        return {
            **self.infos[sid],
            "title": self.rows[sid]["title"],
            "archived": sid in self.archived,
        }

    def older(self, sid: str, after: str = "") -> dict:
        return {"data": list(reversed(self.histories[sid])), "has_more": False}

    def archive(self, sid: str) -> None:
        self.archived.append(sid)

    def children(self, sid: str) -> list[str]:
        return []

    def harness(self, agent: str) -> str:
        return ""


@pytest.fixture
def og(monkeypatch: pytest.MonkeyPatch) -> Fake:
    monkeypatch.setenv("OMNIGENT_SESSION_ID", "me")
    return Fake()


def swept(
    og: Fake, kept: dict[str, str] | None = None, **kw: object
) -> tuple[list[str], list[dict], bool]:
    return omnigent_agent.sweep(og, kept or {}, **kw)


def test_an_idle_session_is_archived_and_a_recent_one_and_the_sweeper_are_not(og: Fake) -> None:
    og.add("old")
    og.add("new", idle=3600)
    og.add("me")
    lines, owner, failed = swept(og)
    assert og.archived == ["old"] and owner == [] and not failed
    assert lines == ["old t-old: archived (idle)"]


@pytest.mark.parametrize("status", ["failed", "cancelled", "errored"])
def test_a_failed_session_counts_as_finished(og: Fake, status: str) -> None:
    og.add("a", status=status)
    swept(og)
    assert og.archived == ["a"]


@pytest.mark.parametrize(
    ("hold", "why"),
    [
        ({"status": "running"}, "kept (running)"),
        ({"pending_elicitations": [CARD]}, "kept (card open: question_1: Land it?)"),
        ({"background_tasks": [{"type": "shell", "status": "running"}]}, "kept (background work)"),
        (
            {
                "pending_elicitations": [
                    {"elicitation_id": "elicit_approval_1", "params": {"message": "Bash?"}}
                ]
            },
            "kept (blocked on a prompt)",
        ),
    ],
)
def test_a_session_with_a_standing_hold_is_kept(og: Fake, hold: dict, why: str) -> None:
    og.add("a", **hold)
    lines, _, _ = swept(og)
    assert og.archived == [] and why in lines[0]


def test_a_session_on_the_keep_list_is_kept_by_id_prefix_or_title(og: Fake, tmp_path: Path) -> None:
    og.add("abc123")
    og.add("def456")
    og.add("zzz")
    listed = tmp_path / "keep-sessions"
    listed.write_text("# kept by hand\nabc  # the release lead\n\nt-def456\n")
    lines, _, _ = swept(og, omnigent_agent.keep_list(listed))
    assert og.archived == ["zzz"]
    assert "abc123 t-abc123: kept (keep list: the release lead)" in lines
    assert "def456 t-def456: kept (keep list: on the keep list)" in lines
    assert omnigent_agent.keep_list(tmp_path / "missing") == {}


def test_a_manager_is_kept(og: Fake) -> None:
    og.add("cos", labels={"omni.role": "cos"})
    swept(og)
    assert og.archived == []


@pytest.mark.parametrize("label", ["omnigent.keep", "omni.keep"])
def test_a_stale_keep_label_holds_only_while_a_reason_stands(og: Fake, label: str) -> None:
    og.add("a", labels={label: "1"}, pending_elicitations=[CARD])
    assert "kept (card open" in swept(og)[0][0] and og.archived == []
    og.infos["a"][
        "pending_elicitations"
    ] = []  # the card was answered: nothing stands behind the label
    lines, _, _ = swept(og)
    assert og.archived == ["a"] and lines == [f"a t-a: archived (idle); stale {label} label"]


def test_a_session_the_owner_talked_to_goes_on_the_card_not_archived(og: Fake) -> None:
    og.add("talked")
    og.histories["talked"] = [OWNER]
    relayed = og.add("relayed")  # a message another session sent names its sender
    og.histories[relayed] = [{**OWNER, "sender_session_id": "lead"}]
    notice = og.add("notice")  # a harness notice
    og.histories[notice] = [{**OWNER, "is_meta": True}]
    briefed = og.add(
        "briefed"
    )  # an agent's brief, posted through the API with the owner's created_by
    og.histories[briefed] = [
        {**OWNER, "content": [{"type": "input_text", "text": "Work on X. Your brief:\ndo it"}]}
    ]
    lines, owner, _ = swept(og)
    assert owner == [{"id": "talked", "title": "t-talked"}]
    assert sorted(og.archived) == ["briefed", "notice", "relayed"]
    assert "talked t-talked: kept (the owner talked to it: on the owner card)" in lines


def test_a_held_session_the_owner_talked_to_is_kept_for_its_hold_not_carded(og: Fake) -> None:
    og.add("a", status="running")
    og.histories["a"] = [OWNER]
    assert swept(og)[1] == []


def test_the_owner_sessions_go_on_one_multiselect_card_with_archive_all_first(og: Fake) -> None:
    rows = [{"id": "s1", "title": "one"}, {"id": "s2", "title": ""}]
    card = omnigent_agent.sweep_card(og, rows)
    assert card is not None and len(card["questions"]) == 1
    q = card["questions"][0]
    assert q["multiSelect"] is True
    assert [o["label"] for o in q["options"]] == [
        "Archive all (Recommended)",
        "Keep one",
        "Keep s2",
    ]
    assert (
        "[one](http://omnigent.test/c/s1)" in q["question"]
        and "(http://omnigent.test/c/s2)" in q["question"]
    )
    assert q["question"].endswith(")") and "?" in q["question"]
    assert omnigent_agent.sweep_card(og, []) is None


def test_a_dry_run_archives_nothing(og: Fake) -> None:
    og.add("a", labels={"omnigent.keep": "1"})
    lines, _, _ = swept(og, dry_run=True)
    assert og.archived == [] and lines == [
        "a t-a: would archive (idle 48h; stale omnigent.keep label)"
    ]


def test_the_command_prints_lines_owner_and_card_as_json(
    og: Fake, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda *a: og)
    og.add("talked")
    og.histories["talked"] = [OWNER]
    og.add("idle")
    assert omnigent_agent.main(["sweep", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["owner"] == [{"id": "talked", "title": "t-talked"}] and og.archived == ["idle"]
    assert out["card"]["questions"][0]["options"][1]["label"] == "Keep t-talked"
