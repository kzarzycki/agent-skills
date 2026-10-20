#!/usr/bin/env python3
"""Spike: write the chief of staff's status as one JSON file both surfaces render.

Reads the Live leads table of a board (a path, or `gh:<owner>/<repo>/<path>`), asks Omnigent
for each lead's live state, and writes `status.json` (schema `cos-status/1`). Read-only on
Omnigent. In the design this is the supervisor's job on every poll; here it is one shot.

    python3 status_snapshot.py gh:kzarzycki/chief-of-staff/board.md status.json [status.html]
"""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "engineering/skills/orchestrating-agents/scripts"))
import omnigent_agent as o  # noqa: E402

ROW = re.compile(r"^\|\s*`([0-9a-f]{32})`\s*\|(.*)\|\s*$")
UI = os.environ.get("COS_UI_BASE", "")  # the web UI's session URL prefix, e.g. https://<server>/c/


def board_text(src: str) -> str:
    if not src.startswith("gh:"):
        return Path(src).read_text()
    owner, repo, path = src[3:].split("/", 2)
    out = subprocess.run(
        ["gh", "api", f"repos/{owner}/{repo}/contents/{path}", "--jq", ".content"],
        check=True, capture_output=True, text=True,
    ).stdout
    return base64.b64decode(out).decode()


def live_leads(board: str) -> list[dict]:
    section = board.split("## Live leads", 1)[1].split("\n## ", 1)[0]
    leads = []
    for line in section.splitlines():
        if m := ROW.match(line):
            cells = [c.strip() for c in m.group(2).split("|")]
            title, harness_host, waits, report = (cells + ["", "", "", ""])[:4]
            spent = re.search(r"\((\d+)\)\s*$", waits)
            leads.append({
                "id": m.group(1), "board_title": title, "harness_host": harness_host,
                "waits_on": re.sub(r"\s*\(\d+\)\s*$", "", waits),
                "revives_spent": int(spent.group(1)) if spent else None,
                "report": report.strip("`"),
            })
    return leads


def state_of(info: dict) -> str:
    if info.get("archived"):
        return "archived"
    if o.prompts_of(info):
        return "blocked"
    status = str(info.get("status"))
    if status == "failed":
        return "failed"
    return "running" if status in o.RUNNING else "idle"


def snapshot(src: str) -> dict:
    og = o.Omnigent()
    hosts = {h["host_id"]: h["name"] for h in og.call("GET", "/v1/hosts").get("hosts", [])}
    leads = []
    for lead in live_leads(board_text(src)):
        try:
            info = og.info(lead["id"])
            items = og.items(lead["id"])
        except o.Fail as e:
            leads.append({**lead, "state": "unknown", "error": str(e)})
            continue
        last = o.last_said(items)
        leads.append({
            **lead,
            "title": info.get("title") or lead["board_title"],
            "host": hosts.get(info.get("host_id"), info.get("host_id")),
            "state": state_of(info),
            "prompt": "; ".join(o.prompts_of(info)) or None,
            "ending": m.group(1) if (m := o.ENDING.search(last)) else None,
            "last_line": last.strip().splitlines()[0][:200] if last.strip() else "",
            "updated_at": info.get("updated_at"),
            "cost_usd": info.get("total_cost_usd"),
            "link": UI + lead["id"] if UI else "",
        })
    return {"schema": "cos-status/1", "written_at": int(time.time()), "source": src, "leads": leads}


def html(data: dict) -> str:
    """The same status as a page, for Omnigent's Files panel (sandboxed iframe, no network)."""
    from html import escape
    mark = {"running": "●", "idle": "○", "blocked": "!", "failed": "✗", "archived": "·"}
    rows = "".join(
        f"<tr class='{escape(lead.get('state', ''))}'><td>{mark.get(lead.get('state', ''), '?')}</td>"
        f"<td><a href='{escape(lead.get('link', ''))}' target='_blank'>{escape(lead.get('title', lead['id']))}</a>"
        f"<div class='id'>{lead['id'][:8]} · {escape(str(lead.get('host', '')))}</div></td>"
        f"<td>{escape(lead.get('waits_on', ''))}<div class='last'>{escape(lead.get('last_line', ''))}</div></td></tr>"
        for lead in data["leads"]
    )
    when = time.strftime("%H:%M:%S", time.localtime(data["written_at"]))
    return f"""<!doctype html><meta charset=utf-8><title>Leads</title>
<style>body{{font:13px system-ui;margin:12px;color:#222;background:#fff}}td{{padding:6px;vertical-align:top;border-bottom:1px solid #eee}}
.id,.last{{color:#777;font-size:12px}}.blocked td,.failed td{{background:#fff3f0}}a{{color:#0b6}}
@media (prefers-color-scheme:dark){{body{{color:#ddd;background:#1b1b1b}}td{{border-color:#333}}.blocked td,.failed td{{background:#3a2420}}}}</style>
<h3>Leads · written {when}</h3><table>{rows}</table>"""


def write_html(data: dict, out: Path) -> None:
    tmp = out.with_suffix(".tmp")
    tmp.write_text(html(data))
    tmp.replace(out)


if __name__ == "__main__":
    src, out = sys.argv[1], Path(sys.argv[2])
    data = snapshot(src)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1))
    tmp.replace(out)  # atomic, so a reader never sees half a file
    if len(sys.argv) > 3:
        write_html(data, Path(sys.argv[3]))
    print(f"{out}: {len(data['leads'])} leads")
