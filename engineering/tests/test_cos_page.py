from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[1] / "skills" / "chief-of-staff" / "scripts" / "cos_page.py"
)
spec = importlib.util.spec_from_file_location("cos_page", SCRIPT)
cos_page = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cos_page)

SID = "99a79f4d70454a6193439337cf828b49"
URL = "https://host.ts.net:6767"


def test_page_shows_leads_owner_events_and_recent_events(tmp_path: Path) -> None:
    registry = tmp_path / "leads.registry"
    lead = {
        "title": "Console <epic>",
        "host": "h",
        "state": "idle",
        "wait": "until 2026-10-21T23:17Z",
    }
    lead.update(last_line="report written", progress_at=1000, label={"line": "turn ended"})
    state = {"written_at": 1990, "leads": {SID: lead}, "rate": {"next_post_at": 0}}
    state["attention"] = [
        {
            "id": "x",
            "session": SID,
            "route": "owner",
            "line": "needs a decision",
            "why": "fork",
            "at": 1900,
        },
        {"id": "y", "session": SID, "route": "act", "line": "stall", "why": "nudge", "at": 1950},
    ]
    (tmp_path / "leads.state.json").write_text(json.dumps(state))
    old = {
        "at": 100,
        "session": SID,
        "kind": "deadline",
        "settled": "rule",
        "action": "nudge",
        "why": "old one",
    }
    new = {
        "at": 200,
        "session": SID,
        "kind": "ended",
        "settled": "rule",
        "action": "record",
        "why": "new one",
    }
    (tmp_path / "leads.events.jsonl").write_text(f"{json.dumps(old)}\n{json.dumps(new)}\n{{half")
    board = tmp_path / "board.md"
    board.write_text(
        "## Needs the owner\n- Sign in to X.\n  - nested note\n\n## Owner asks\n- not this\n"
    )

    page = cos_page.render(registry, board, URL + "/", now=2000)

    assert f'href="{URL}/c/{SID}"' in page  # full id, no double slash
    assert "Console &lt;epic&gt;" in page and "<epic>" not in page
    assert "until 2026-10-21T23:17Z" in page and "report written" in page and "16m" in page
    now = page.split("Needs you now")[1].split("By project")[0]
    assert "supervisor: fork" in now and "nudge" not in now  # routed owner, not act
    assert "Sign in to X." in now and "not this" not in page and "nested note" not in page
    assert page.index("new one") < page.index("old one")
    assert "rule → record" in page


def test_page_renders_without_the_supervisor_files(tmp_path: Path) -> None:
    page = cos_page.render(tmp_path / "leads.registry", tmp_path / "board.md", URL, now=0)
    assert "leads.state.json" in page and "No sessions read yet." in page
    assert "first poll has not finished" in page
    assert "No events yet." in page


def test_page_renders_odd_and_half_written_files(tmp_path: Path) -> None:
    good = {"title": "Good lead", "progress_at": "unknown", "state": 3}
    state = {"leads": {SID: good, "b" * 32: None}, "attention": [None, "x"], "rate": []}
    (tmp_path / "leads.state.json").write_text(json.dumps(state))
    (tmp_path / "leads.events.jsonl").write_text('null\n["x"]\n{"session": 5, "kind": "ended"}\n')
    (tmp_path / "board.md").write_bytes(b"## Needs the owner\n- caf\xe2\x80")
    page = cos_page.render(tmp_path / "leads.registry", tmp_path / "board.md", URL, now=0)
    assert "Good lead" in page and "ended" in page and "board.md: " in page
    page = cos_page.render(tmp_path / "leads.registry", tmp_path, URL, now=0)  # board is a dir
    assert "Good lead" in page
    (tmp_path / "leads.state.json").write_text('{"leads": ["x"], "attention": {}}')
    assert "No sessions read yet." in cos_page.render(tmp_path / "leads.registry", None, URL)


A, B, C, D, E, F, G, H = (c * 32 for c in "abcdef01")


class FakeOmnigent:
    """The calls ``collect`` makes, over fixed sessions; counts history reads."""

    def __init__(self) -> None:
        self.reads = 0
        self.top = [
            {"id": A, "title": "Blocked", "status": "idle", "pending_elicitations_count": 1},
            {"id": B, "title": "Asks", "status": "idle", "project_id": "p1", "host_id": "h1"},
            {"id": C, "title": "Done", "status": "idle", "project_id": "p1"},
            {"id": D, "title": "Busy", "status": "running", "labels": {"status.line": "running"}},
            {"id": E, "title": "Quiet", "status": "idle", "updated_at": 5},
            {"id": F, "title": "Parent", "status": "idle", "project_id": "p2"},
            {"id": H, "title": "Reported", "status": "idle"},
        ]
        self.said = {
            B: "Built it.\nUSER NEEDED: pick a **name**",
            C: "DONE: merged",
            E: "Here is the summary.",
            F: "STILL WORKING on the verifier",
            H: "tmp/loop/report.md",
        }

    def hosts(self) -> dict:
        return {"h1": "kris"}

    def call(self, method: str, path: str) -> dict:
        if path == "/v1/projects":
            return {"data": [{"id": "p1", "name": "Voice note"}, {"id": "p2", "name": "Omnigent"}]}
        if "sub_agent" in path:
            return {"data": [{"id": G, "title": "worker", "pending_elicitations_count": 1}]}
        return {"data": self.top}

    def info(self, sid: str) -> dict:
        if sid == G:
            ask = {"params": {"message": "Which branch?", "ask_user_question": True}}
            return {"root_conversation_id": F, "pending_elicitations": [ask]}
        return {"pending_elicitations": [{"params": {"content_preview": "Bash(rm x)"}}]}

    def read_file(self, sid: str, path: str) -> str:
        assert (sid, path) == (H, "tmp/loop/report.md")
        return "PARKED: no host capacity\nmore"

    def items(self, sid: str) -> list[dict]:
        self.reads += 1
        msg = {"type": "message", "role": "assistant", "content": [{"text": self.said[sid]}]}
        return [{**msg, "id": f"item-{sid[0]}"}]


def test_collect_classifies_every_session_and_asks_the_model_once_per_last_item() -> None:
    og, memo, asked = FakeOmnigent(), {}, []

    def triage(text: str, decisions: str, prompt: str) -> tuple[str, str]:
        asked.append(text)
        return "none", "a summary"

    rows = {r["id"]: r for r in cos_page.collect(og, {}, memo, triage, now=100)}
    level = {sid: r["level"] for sid, r in rows.items()}
    assert level == {A: "red", B: "red", C: "grey", D: "green", E: "grey", F: "red", H: "amber"}
    assert rows[H]["what"] == "Parked: PARKED: no host capacity"  # read from its report
    assert rows[A]["what"] == "Approve or deny: Bash(rm x)"
    assert rows[B]["what"] == "Reply: USER NEEDED: pick a name" and rows[B]["host"] == "kris"
    assert rows[B]["project"] == "Voice note" and rows[A]["project"] == "No project"
    assert rows[F]["what"] == "Answer in sub-agent “worker”: Which branch?"  # a child's prompt
    assert len(asked) == 1 and "Here is the summary." in asked[0]  # rules settle the rest
    reads = og.reads
    cos_page.collect(og, {}, memo, triage, now=110)
    assert og.reads == reads - 0 and len(asked) == 1  # unchanged sessions: no read, no model call
    og.top[4]["updated_at"] = 6  # a new message with the same last item: read, not asked again
    cos_page.collect(og, {}, memo, triage, now=120)
    assert og.reads == reads + 1 and len(asked) == 1


def test_collect_stops_asking_past_the_hourly_allowance() -> None:
    og = FakeOmnigent()
    memo = {"calls": [100.0] * cos_page.MODEL_HOURLY}
    rows = {r["id"]: r for r in cos_page.collect(og, {}, memo, lambda *a: ("owner", "x"), now=200)}
    assert rows[E]["level"] == "amber" and "unclassified" in rows[E]["why"]


def test_page_groups_by_project_red_first_with_the_board_and_supervisor(tmp_path: Path) -> None:
    rows = cos_page.collect(FakeOmnigent(), {}, {}, lambda *a: ("owner", "asks"), now=100)
    state = {
        "attention": [{"session": D, "route": "owner", "line": "approve deploy", "why": "prompt"}]
    }
    (tmp_path / "leads.state.json").write_text(json.dumps(state))
    board = tmp_path / "board.md"
    board.write_text(
        f"## Needs the owner\n- Review later: `{C[:8]}` decisions.\n- Sign in to Y.\n"
        f"- Low priority: rotate a token.\n- Parked by owner: `{E[:8]}` display.\n"
    )
    snap = {"rows": rows, "at": 100}
    page = cos_page.render(tmp_path / "leads.registry", board, URL, snap, now=160)
    now = page.split("Needs you now")[1].split("By project")[0]
    for sid in (A, B, D, F):
        assert f'href="{URL}/c/{sid}"' in now
    assert "approve deploy" in now and "supervisor: prompt" in now  # raised from green
    assert "Sign in to Y." in now and "rotate a token" not in now
    groups = page.split("By project")[1]
    assert groups.index("No project") < groups.index("Voice note")  # both red; by name
    assert "🟡 When convenient" in groups and "Review later" in groups  # C raised from grey
    assert "Board: when convenient" in groups and "rotate a token" in groups
    assert "Parked by owner" not in now and "Parked by owner" in groups  # the model's red yields
    assert "🔴 5 needs you" in page  # four sessions + one board ask


def test_page_falls_back_to_the_supervisor_when_omnigent_is_unread(tmp_path: Path) -> None:
    lead = {"title": "Android", "host": "kris", "state": "blocked", "last_line": "pair adb"}
    state = {
        "leads": {SID: lead},
        "attention": [{"session": SID, "route": "owner", "line": "pair"}],
    }
    (tmp_path / "leads.state.json").write_text(json.dumps(state))
    snap = {"error": "Omnigent sessions not read: HTTP 502", "at": None}
    page = cos_page.render(tmp_path / "leads.registry", None, URL, snap, now=0)
    assert "HTTP 502" in page and f'href="{URL}/c/{SID}"' in page and "Followed leads" in page
