from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

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
        self.at: dict[str, float] = {}  # when each session's last message was written
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
        return [{**msg, "id": f"item-{sid[0]}", "created_at": self.at.get(sid)}]


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
    assert "Board: when convenient" not in page
    other = groups.split("<summary>Other")[1].split("</details>")[0]
    assert "rotate a token" in other and "Sign in to Y." in other  # no area, no session
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


def test_a_wait_is_judged_from_when_its_message_was_written() -> None:
    og = FakeOmnigent()
    og.said[E] = (
        "STILL WORKING: a timer wakes me at 2026-10-27 06:32 UTC. The last run ended 2026-10-21 10:00 UTC."
    )
    og.at[E] = 1792584000.0  # 2026-10-21 12:00Z: the second time had passed when it was written
    rows = {r["id"]: r for r in cos_page.collect(og, {}, {}, lambda *a: ("none", ""), now=0)}
    assert rows[E]["level"] == "green" and rows[E]["what"] == "waits until 2026-10-27T06:32Z"


def test_an_ask_after_a_done_line_is_red_and_an_unsure_answer_waits_before_a_retry() -> None:
    og, asked = FakeOmnigent(), []
    og.said[C] = "DONE: #271 merged.\nUSER NEEDED: pick option A or B"

    def triage(text: str, decisions: str, prompt: str) -> tuple[str, str]:
        asked.append(decisions)
        return "unsure", "small model: TimeoutExpired"

    memo: dict = {}
    leads = {C: {"ending": "DONE", "last_line": "DONE: #271 merged."}}  # a followed lead
    rows = {r["id"]: r for r in cos_page.collect(og, leads, memo, triage, now=0, decisions="- go")}
    assert rows[C]["level"] == "red" and rows[C]["what"] == "Reply: USER NEEDED: pick option A or B"
    assert rows[E]["level"] == "amber" and asked == ["- go"]  # the standing decisions reach it
    og.top[4]["updated_at"] = 6  # read again, same last item: the failed call is not retried yet
    cos_page.collect(og, {}, memo, triage, now=60)
    assert len(asked) == 1
    cos_page.collect(og, {}, memo, triage, now=60 + cos_page.UNSURE_SECONDS)
    assert len(asked) == 2


def test_the_board_and_supervisor_never_lower_a_prompt_and_only_opening_words_defer() -> None:
    import tempfile

    rows = cos_page.collect(FakeOmnigent(), {}, {}, lambda *a: ("none", "fyi"), now=100)
    with tempfile.TemporaryDirectory() as d:
        board = Path(d) / "board.md"
        board.write_text(
            f"## Needs the owner\n- Review later: `{A[:8]}` approvals.\n"
            "- Approve the prod deploy, parked until you say go.\n"
            "- XMac display, parked by owner: run the reset.\n"
        )
        page = cos_page.render(Path(d) / "leads.registry", board, URL, {"rows": rows, "at": 100})
    now = page.split("Needs you now")[1].split("By project")[0]
    assert f"/c/{A}" in now and "Approve or deny: Bash(rm x)" in now  # still red, still its prompt
    assert "parked until you say go" in now and "XMac display" not in now


def test_the_page_warns_past_one_page_of_sessions_and_hides_a_post_time_already_past(
    tmp_path: Path,
) -> None:
    og = FakeOmnigent()
    call = og.call
    og.call = lambda m, p: {**call(m, p), "has_more": "sub_agent" in p}
    memo: dict = {}
    cos_page.collect(og, {}, memo, lambda *a: ("none", "x"), now=0)
    assert memo["warnings"] == ["More than 1000 sub_agent sessions: the older ones are not read"]
    assert memo["projects"] == ["Voice note", "Omnigent"]  # the poll hands them to render
    state = {"rate": {"next_post_at": 1000}}
    (tmp_path / "leads.state.json").write_text(json.dumps(state))
    snap = {"rows": [], "at": 0, "warnings": memo["warnings"]}
    page = cos_page.render(tmp_path / "leads.registry", None, URL, snap, now=999)
    assert "next post" in page and "older ones are not read" in page
    assert "next post" not in cos_page.render(
        tmp_path / "leads.registry", None, URL, snap, now=1001
    )


def test_the_real_triage_takes_the_page_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    seen = []

    def run(cmd: list[str], **kw: object) -> subprocess.CompletedProcess:
        seen.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, '{"route": "owner", "why": "Pick a name"}', "")

    monkeypatch.setattr(cos_page.OA.subprocess, "run", run)
    rows = {r["id"]: r for r in cos_page.collect(FakeOmnigent(), {}, {}, now=0, decisions="- d")}
    assert rows[E]["level"] == "red" and rows[E]["what"] == "Pick a name"
    prompt = seen[0][seen[0].index("--system-prompt") + 1]
    assert prompt.startswith("You sort one session") and prompt.endswith("decisions: - d")


def test_the_poll_hands_the_boards_standing_decisions_to_the_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    board = tmp_path / "board.md"
    board.write_text("## Standing decisions\n- merge on green\n\n## Needs the owner\n- x\n")
    seen = []

    def collect(og: object, leads: dict, memo: dict, **kw: object) -> list:
        seen.append(kw.get("decisions"))
        memo.update(warnings=[], projects=["trinity"])
        return []

    def stop(_: float) -> None:
        raise SystemExit

    monkeypatch.setattr(cos_page, "collect", collect)
    servers: list[str] = []
    monkeypatch.setattr(
        cos_page.OA, "Omnigent", lambda server="": servers.append(server) or object()
    )
    monkeypatch.setattr(cos_page.time, "sleep", stop)
    snap: dict = {}
    with pytest.raises(SystemExit):
        cos_page.poll(snap, tmp_path / "leads.registry", board, "https://work.example")
    assert seen == ["- merge on green"] and snap["error"] is None
    assert snap["projects"] == ["trinity"]
    assert servers == ["https://work.example"]  # the page reads the server its links point to


def test_a_board_bullet_opening_with_a_level_marker_takes_that_level(tmp_path: Path) -> None:
    board = tmp_path / "board.md"
    board.write_text(
        "## Needs the owner\n- 🟡 pack PR: add approved:merge when green.\n"
        "- ⚪\ufe0f FYI: the release went out.\n- 🔴 Review later wording, but marked red.\n"
    )
    page = cos_page.render(tmp_path / "leads.registry", board, URL, {"rows": [], "at": 0})
    now = page.split("Needs you now")[1].split("By project")[0]
    assert "Review later wording" in now and "pack PR" not in now and "🔴 🔴" not in now
    groups = page.split("By project")[1]
    assert "pack PR: add approved:merge" in groups and "🟡 🟡" not in groups
    assert "release went out" not in page  # neither red nor amber: no list shows it
    assert "⚪ 0 done" in page  # nor does a chip count it


def test_a_board_bullet_joins_its_sessions_project_else_the_area_it_names(tmp_path: Path) -> None:
    rows = cos_page.collect(FakeOmnigent(), {}, {}, lambda *a: ("none", "fyi"), now=100)
    board = tmp_path / "board.md"
    board.write_text(
        "## Needs the owner\n- 🔴 **voice_note:** fix the transcript.\n"
        "- 🟡 **Disk space:** clean the Mac.\n- 🟡 **disk:** and the caches.\n"
        "- 🟡 **trinity:** review the rules.\n- 🔴 **Ops:** sign in.\n"
        f"- 🟡 **trinity:** `{C[:8]}` follow-ups.\n- 🔴 Pick a name.\n"
    )
    snap = {"rows": rows, "at": 100, "projects": ["Voice note", "Omnigent", "trinity"]}
    page = cos_page.render(tmp_path / "leads.registry", board, URL, snap, now=160)
    now = page.split("Needs you now")[1].split("By project")[0]
    heads = re.findall(r"<h3>([^<]*)</h3>", now)
    assert heads == ["No project", "Omnigent", "Ops", "Other", "Voice note"]  # by-project order
    assert "<ul class=now><h3>" not in page  # headings sit beside the lists, not inside one
    voice = now.split("<h3>Voice note</h3>")[1].split("<h3>")[0]
    assert f"/c/{B}" in voice and voice.index(f"/c/{B}") < voice.index("fix the transcript.")
    assert "**" not in page and "voice_note" not in page  # the area leaves the text
    assert "clean the Mac" not in now and "🟡" not in now  # red items only

    def group(name: str) -> str:
        return page.split(f"<summary>{name} ")[1].split("</details>")[0]

    assert "clean the Mac" in group("Disk space") and "and the caches" in group("Disk space")
    assert "review the rules" in group("trinity")  # a project with no session
    assert f"/c/{C}" in group("Voice note") and "follow-ups" in group("Voice note")  # its session's
    assert "fix the transcript" in group("Voice note") and "Pick a name" in group("Other")
    assert "🟡 2 later" in group("Disk space")
