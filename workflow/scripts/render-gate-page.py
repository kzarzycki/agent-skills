#!/usr/bin/env python3
"""Render a workflow gate page: artifact + verdicts + approve/rework copy-back form.

Usage:
  render-gate-page.py --artifact <md> --out <html> [--phase spec] [--verdicts '<json>']

Deterministic replacement for the LLM-rendered gate page: one self-contained
offline HTML file. The markdown converter covers the contract artifact shape
(H1/H2 headings, tables, flat lists, fenced code, bold/italic/code/links).
"""
import argparse
import html
import json
import re
import sys
from pathlib import Path


def inline(s):
    s = html.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', s)
    return s


def md_to_html(text):
    out, lines, i = [], text.splitlines(), 0
    in_code = in_ul = in_ol = False
    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            if in_code:
                out.append("</code></pre>")
            else:
                out.append("<pre><code>")
            in_code = not in_code
            i += 1
            continue
        if in_code:
            out.append(html.escape(line))
            i += 1
            continue
        for flag, tag, pat in ((in_ul, "ul", r"^[-*] +"), (in_ol, "ol", r"^\d+\. +")):
            if flag and not re.match(pat, line):
                out.append(f"</{tag}>")
                if tag == "ul":
                    in_ul = False
                else:
                    in_ol = False
        if not line.strip():
            i += 1
            continue
        m = re.match(r"^(#{1,6}) +(.*)", line)
        if m:
            n = len(m.group(1))
            out.append(f"<h{n}>{inline(m.group(2))}</h{n}>")
        elif line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            i -= 1
            body_start = 1
            if len(rows) > 1 and all(re.fullmatch(r":?-{2,}:?", c) for c in rows[1]):
                body_start = 2
            out.append("<table><thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in rows[0]) + "</tr></thead><tbody>")
            for r in rows[body_start:]:
                out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>")
            out.append("</tbody></table>")
        elif re.match(r"^[-*] +", line):
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{inline(re.sub(r'^[-*] +', '', line))}</li>")
        elif re.match(r"^\d+\. +", line):
            if not in_ol:
                out.append("<ol>")
                in_ol = True
            out.append(f"<li>{inline(re.sub(r'^\\d+\\. +', '', line))}</li>")
        elif re.fullmatch(r"-{3,}", line.strip()):
            out.append("<hr>")
        else:
            out.append(f"<p>{inline(line)}</p>")
        i += 1
    for flag, tag in ((in_ul, "ul"), (in_ol, "ol")):
        if flag:
            out.append(f"</{tag}>")
    if in_code:
        out.append("</code></pre>")
    return "\n".join(out)


CSS = """
:root{--ink:#1a1a1a;--mut:#666;--line:#e3e0da;--bg:#faf9f7;--card:#fff;--ok:#1a7f4b;--okbg:#e6f4ec;
--warn:#9a6700;--warnbg:#fff3d6;--accent:#bd5b28}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:16px/1.55 -apple-system,'Segoe UI',Roboto,sans-serif}
.wrap{max-width:860px;margin:0 auto;padding:24px 16px 64px}
header{border-bottom:2px solid var(--ink);padding-bottom:12px;margin-bottom:16px}
header h1{margin:0 0 6px;font-size:1.4rem}header p{margin:0;color:var(--mut)}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0}
.chip{padding:4px 12px;border-radius:999px;font-size:.85rem;font-weight:600}
.chip.pass{background:var(--okbg);color:var(--ok)}
.chip.other{background:var(--warnbg);color:var(--warn)}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:20px 24px;margin:16px 0}
.card h1{font-size:1.25rem;border-bottom:1px solid var(--line);padding-bottom:8px}
.card h2{font-size:1.05rem;margin-top:1.6em;color:var(--accent)}
table{border-collapse:collapse;width:100%;margin:10px 0;font-size:.92rem}
th,td{border:1px solid var(--line);padding:6px 10px;text-align:left;vertical-align:top}
th{background:var(--bg)}code{background:#f1efeb;padding:1px 5px;border-radius:4px;font-size:.88em}
pre{background:#f1efeb;padding:12px;border-radius:8px;overflow-x:auto}
.gatebox label{display:block;font-weight:600;margin:12px 0 4px}
textarea{width:100%;min-height:90px;border:1px solid var(--line);border-radius:8px;padding:10px;font:inherit}
.btn{border:0;border-radius:8px;padding:10px 18px;font:600 1rem inherit;cursor:pointer;margin:8px 8px 0 0}
.btn.ok{background:var(--ok);color:#fff}.btn.rw{background:var(--accent);color:#fff}
#token{display:none;margin-top:12px}#token pre{white-space:pre-wrap;word-break:break-all}
.note{color:var(--mut);font-size:.88rem}
@media(max-width:420px){.card{padding:14px}}
"""

JS = """
function emit(decision){
  var fb=document.getElementById('fb').value.trim();
  var payload={gate:GATE,decision:decision};
  if(fb)payload.feedback=fb;
  var tok='ANSWERS<<< '+JSON.stringify(payload)+' >>>ANSWERS';
  var box=document.getElementById('token');box.style.display='block';
  document.getElementById('tokval').textContent=tok;
  if(navigator.clipboard)navigator.clipboard.writeText(tok).catch(function(){});
}
"""


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--artifact", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--phase", default="spec")
    p.add_argument("--verdicts", default="{}", help='JSON: {"intent":{"verdict":"pass","findings":[]}}')
    a = p.parse_args()

    md = Path(a.artifact).read_text(encoding="utf-8")
    verdicts = json.loads(a.verdicts)
    chips = []
    findings = []
    for name, v in verdicts.items():
        verdict = v.get("verdict", "?") if isinstance(v, dict) else str(v)
        cls = "pass" if verdict == "pass" else "other"
        chips.append(f'<span class="chip {cls}">{html.escape(name)}: {html.escape(verdict)}</span>')
        for f in (v.get("findings", []) if isinstance(v, dict) else []):
            findings.append(f"<li><strong>{html.escape(name)}</strong>: {inline(f)}</li>")
    findings_html = f"<div class='card'><h2>Findings</h2><ul>{''.join(findings)}</ul></div>" if findings else ""

    title = f"{a.phase.replace('_', ' ').title()} gate — {Path(a.artifact).name}"
    page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>{CSS}</style></head><body><div class="wrap">
<header><h1>{html.escape(title)}</h1>
<p>Review the artifact below, then approve or request rework. Your answer copies as a token to paste back into chat.</p>
<div class="chips">{''.join(chips)}</div></header>
{findings_html}
<div class="card">{md_to_html(md)}</div>
<div class="card gatebox"><h2>Your decision</h2>
<label for="fb">Feedback / rework instructions (optional for approve, required for rework)</label>
<textarea id="fb" placeholder="What should change?"></textarea>
<button class="btn ok" onclick="emit('approve')">Approve</button>
<button class="btn rw" onclick="emit('rework')">Request rework</button>
<div id="token"><p class="note">Copied to clipboard — paste into the chat:</p><pre id="tokval"></pre></div>
</div>
<p class="note">Markdown artifact is the source of truth: {html.escape(a.artifact)}</p>
</div><script>var GATE={json.dumps(a.phase)};{JS}</script></body></html>"""

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    print(out)


if __name__ == "__main__":
    sys.exit(main())
