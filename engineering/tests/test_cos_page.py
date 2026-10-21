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
        "## Needs the owner\n- Sign in to X.\n  - detail\n\n## Owner asks\n- not this\n"
    )

    page = cos_page.render(registry, board, URL + "/", now=2000)

    assert f'href="{URL}/c/{SID}"' in page  # full id, no double slash
    assert "Console &lt;epic&gt;" in page and "<epic>" not in page
    assert "until 2026-10-21T23:17Z" in page and "report written" in page and "16m" in page
    owner = page.split("Waiting on the owner")[1].split("<h2>")[0]
    assert "fork" in owner and "nudge" not in owner
    assert "1 event(s) queued for the CoS" in page
    assert "Sign in to X." in page and "not this" not in page and "detail" not in page
    assert page.index("new one") < page.index("old one")
    assert "rule → record" in page


def test_page_renders_without_the_supervisor_files(tmp_path: Path) -> None:
    page = cos_page.render(tmp_path / "leads.registry", tmp_path / "board.md", URL, now=0)
    assert "leads.state.json" in page and "No leads in the state file." in page
    assert "No events yet." in page


def test_page_renders_odd_and_half_written_files(tmp_path: Path) -> None:
    good = {"title": "Good lead", "progress_at": "unknown", "state": 3}
    state = {"leads": {SID: good, "b" * 32: None}, "attention": [None, "x"], "rate": []}
    (tmp_path / "leads.state.json").write_text(json.dumps(state))
    (tmp_path / "leads.events.jsonl").write_text('null\n["x"]\n{"session": 5, "kind": "ended"}\n')
    (tmp_path / "board.md").write_bytes(b"## Needs the owner\n- caf\xe2\x80")
    page = cos_page.render(tmp_path / "leads.registry", tmp_path / "board.md", URL, now=0)
    assert "Good lead" in page and "ended" in page
    page = cos_page.render(tmp_path / "leads.registry", tmp_path, URL, now=0)  # board is a dir
    assert "Good lead" in page
    (tmp_path / "leads.state.json").write_text('{"leads": ["x"], "attention": {}}')
    assert "No leads in the state file." in cos_page.render(tmp_path / "leads.registry", None, URL)
