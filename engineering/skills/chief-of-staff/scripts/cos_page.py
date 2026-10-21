#!/usr/bin/env python3
"""Serve one page that shows a chief of staff's leads at a glance.

It reads what ``omnigent_agent.py supervise --console`` writes next to its registry
(``leads.registry`` → ``leads.state.json``, ``leads.events.jsonl``) and the handover board's
``## Needs the owner``, on every request, and never writes. It binds 127.0.0.1 unless ``--host``
names the machine's tailnet address (``tailscale ip -4``), which only tailnet peers reach; where
the user is the tailscale operator, ``tailscale serve --bg --https=<port> http://127.0.0.1:<port>``
adds HTTPS instead. Never a public address, never Funnel.

    cos_page.py --registry reports/leads.registry --board board.md \
        --omnigent https://<host>.<tailnet>.ts.net:6767 [--host <tailnet ip>] [--port 6768]
"""

from __future__ import annotations

import argparse
import html
import json
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

EVENTS = 30
CSS = """
:root{--bg:#fff;--fg:#1d1d1f;--mute:#6e6e73;--line:#e5e5ea;--warn:#b25000;--ok:#1a7f37}
@media (prefers-color-scheme:dark){:root{--bg:#161618;--fg:#f2f2f7;--mute:#98989f;
--line:#2c2c2e;--warn:#ff9f0a;--ok:#30d158}}
body{background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,sans-serif;margin:0;
padding:16px;max-width:1200px}
h1{font-size:20px;margin:0 0 4px}h2{font-size:15px;margin:24px 0 8px}
.mute{color:var(--mute)}.warn{color:var(--warn)}.ok{color:var(--ok)}a{color:inherit}
.wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;min-width:720px}
th,td{text-align:left;vertical-align:top;padding:6px 8px;border-bottom:1px solid var(--line)}
th{font-weight:600;color:var(--mute);white-space:nowrap}td.n{white-space:nowrap}
small{display:block;color:var(--mute)}ul{margin:0;padding-left:20px}li{margin:4px 0}
"""


def read(path: Path) -> tuple[object, str | None]:
    """The file's JSON, or None and why it could not be read: the supervisor may be mid-write."""
    try:
        return json.loads(path.read_text()), None
    except (OSError, ValueError) as e:
        return None, f"{path.name}: {e}"


def events(path: Path) -> tuple[list[dict], str | None]:
    """The last ``EVENTS`` lines that parse, newest first."""
    try:
        lines = path.read_text().splitlines()[-EVENTS:]
    except (OSError, ValueError) as e:
        return [], f"{path.name}: {e}"
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except ValueError:
            pass  # a line the supervisor is still appending
    return [x for x in out[::-1] if isinstance(x, dict)], None


def needs_owner(board: Path | None) -> list[str]:
    """The top-level bullets of the board's ``## Needs the owner``."""
    try:
        text = board.read_text() if board else ""
    except (OSError, ValueError):
        return []  # missing, or caught mid-write
    m = re.search(r"^## Needs the owner\n(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    return [b[2:].strip() for b in m.group(1).splitlines() if b.startswith("- ")] if m else []


def age(at: object, now: float) -> str:
    if not isinstance(at, (int, float, str)) or not str(at).replace(".", "", 1).isdigit():
        return "?"
    s = max(0, int(now - float(at)))
    return (
        f"{s}s"
        if s < 60
        else f"{s // 60}m"
        if s < 3600
        else f"{s // 3600}h"
        if s < 86400
        else f"{s // 86400}d"
    )


def num(x: object) -> float:
    try:
        return float(x)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def utc(at: object) -> str:
    try:
        return time.strftime("%m-%d %H:%MZ", time.gmtime(float(at)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "?"


def render(registry: Path, board: Path | None, omnigent: str, now: float | None = None) -> str:
    now = time.time() if now is None else now

    def e(x: object) -> str:
        return html.escape(str(x))

    state_file = registry.with_suffix(".state.json")
    state, err = read(state_file)
    state = state if isinstance(state, dict) else {}
    leads = state.get("leads")
    leads = (
        {k: v for k, v in leads.items() if isinstance(v, dict)} if isinstance(leads, dict) else {}
    )
    attention = state.get("attention")
    attention = [a for a in attention if isinstance(a, dict)] if isinstance(attention, list) else []
    recent, err2 = events(registry.with_suffix(".events.jsonl"))
    errors = [x for x in (err, err2) if x]

    def link(sid: object, text: object = None) -> str:
        sid = str(sid)
        return f'<a href="{e(omnigent.rstrip("/"))}/c/{e(sid)}">{e(text or sid[:8])}</a>'

    def title(sid: object) -> str:
        return (leads.get(sid) or {}).get("title") or str(sid)[:8]

    rows = []
    for sid, lead in sorted(leads.items(), key=lambda kv: -num(kv[1].get("progress_at"))):
        status = (lead.get("label") or {}).get("line") or ""
        st = lead.get("state") or "?"
        cls = (
            "warn"
            if lead.get("error") or st in ("failed", "blocked")
            else "ok"
            if st == "running"
            else ""
        )
        rows.append(
            f"<tr><td>{link(sid, lead.get('title') or sid[:8])}<small>{e(lead.get('host') or '')}"
            f" · {e(sid)}</small></td><td class='n {cls}'>{e(st)}"
            f"{'<small>' + e(str(lead['ending'])) + '</small>' if lead.get('ending') else ''}</td>"
            f"<td class=n>{e(lead.get('wait') or '')}</td>"
            f"<td>{e(lead.get('last_line') or '')}<small>{e(status)}</small></td>"
            f"<td class=n>{age(lead.get('progress_at'), now)}</td></tr>"
        )
    leads_html = (
        "<div class=wrap><table><tr><th>Lead</th><th>State</th><th>Wait</th><th>Last line · status</th>"
        f"<th>Progress</th></tr>{''.join(rows)}</table></div>"
        if rows
        else "<p class=mute>No leads in the state file.</p>"
    )

    owner = [a for a in attention if a.get("route") == "owner"]
    owner_html = "".join(
        f"<li>{link(a.get('session', ''), title(a.get('session', '')))} <span class=mute>{age(a.get('at'), now)} ago</span>"
        f" — {e(a.get('why') or '')}<small>{e((a.get('line') or '').splitlines()[0] if a.get('line') else '')}</small></li>"
        for a in owner
    )
    board_html = "".join(f"<li>{e(b)}</li>" for b in needs_owner(board))

    ev_rows = "".join(
        f"<tr><td class=n>{utc(ev.get('at'))}</td><td>{link(ev.get('session', ''), title(ev.get('session', '')))}</td>"
        f"<td class=n>{e(ev.get('kind') or '')}</td>"
        f"<td class=n>{e(ev.get('settled') or '')}{' → ' + e(ev['action']) if ev.get('action') else ''}</td>"
        f"<td>{e(ev.get('why') or '')}</td></tr>"
        for ev in recent
    )
    ev_html = (
        "<div class=wrap><table><tr><th>When (UTC)</th><th>Lead</th><th>Kind</th><th>Settled → route</th>"
        f"<th>Why</th></tr>{ev_rows}</table></div>"
        if ev_rows
        else "<p class=mute>No events yet.</p>"
    )
    rate = state.get("rate") if isinstance(state.get("rate"), dict) else {}
    queued = len(attention) - len(owner)
    return f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><meta http-equiv=refresh content=30>
<title>Chief of staff</title><style>{CSS}</style></head><body>
<h1>Chief of staff</h1>
<p class=mute>State written {age(state.get("written_at"), now)} ago · {queued} event(s) queued for the CoS ·
next post {utc(rate.get("next_post_at"))} · refreshes every 30s</p>
{"".join(f"<p class=warn>{e(x)}</p>" for x in errors)}
<h2>Waiting on the owner</h2>
{f"<ul>{owner_html}</ul>" if owner_html else "<p class=mute>No supervisor event waits on you.</p>"}
{f"<h2>Board: Needs the owner</h2><ul>{board_html}</ul>" if board_html else ""}
<h2>Leads</h2>{leads_html}
<h2>Recent events</h2>{ev_html}
</body></html>"""


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--registry", type=Path, required=True)
    p.add_argument("--board", type=Path)
    p.add_argument(
        "--omnigent", required=True, help="Omnigent base URL; sessions link to <url>/c/<id>"
    )
    p.add_argument("--host", default="127.0.0.1", help="127.0.0.1 or the tailnet address")
    p.add_argument("--port", type=int, default=6768)
    a = p.parse_args()

    class Page(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path.split("?")[0] != "/":
                self.send_error(404)
                return
            try:
                page = render(a.registry, a.board, a.omnigent)
            except Exception as x:  # noqa: BLE001 - a shape the supervisor never wrote: say so, keep serving
                page = f"<!doctype html><title>Chief of staff</title><p>Cannot render: {html.escape(repr(x))}"
            body = page.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_: object) -> None:
            pass

    ThreadingHTTPServer((a.host, a.port), Page).serve_forever()


if __name__ == "__main__":
    main()
