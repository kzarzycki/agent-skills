#!/usr/bin/env python3
"""Render a markdown artifact as a live decision page: approve / request rework.

Usage:
  render-decision-page.py --artifact <md> --out <html> [--gate <id>]
      [--verdicts '<json>'] [--banner '<text>']

Deterministic (zero LLM tokens), one self-contained offline HTML file. The page
is live when served by gate-server.py (POST /gate/answer, poll /gate/state,
auto-reload on version bump) and degrades to a copy-back token when opened as a
static file. Every H2 section of the artifact is annotatable (pencil button);
annotations travel with the rework decision as targeted instructions. The
decision bar is always visible -- only the notes list folds. --gate is the id
echoed in every answer payload, so the agent knows which decision this is.
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


def slug(s):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s.lower())).strip("-") or "section"


def artifact_html(md):
    """Wrap the H1 preamble and each H2 section in an annotatable block."""
    lines = md.splitlines()
    blocks, cur, head = [], [], None
    for line in lines:
        m = re.match(r"^## +(.*)", line)
        if m:
            blocks.append((head, cur))
            head, cur = m.group(1), [line]
        else:
            cur.append(line)
    blocks.append((head, cur))
    out = []
    for head, body in blocks:
        content = md_to_html("\n".join(body))
        if not content.strip():
            continue
        s = slug(head) if head else "title"
        out.append(f'<section class="sec ann" data-ann="{s}">{content}</section>')
    return "\n".join(out)


CSS = """
:root{--ink:#1a1a1a;--mut:#666;--line:#e3e0da;--bg:#faf9f7;--card:#fff;--ok:#1a7f4b;--okbg:#e6f4ec;
--warn:#9a6700;--warnbg:#fff3d6;--accent:#bd5b28;--bad:#b3261e}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:16px/1.55 -apple-system,'Segoe UI',Roboto,sans-serif}
.wrap{max-width:860px;margin:0 auto;padding:24px 16px 110px}
header{border-bottom:2px solid var(--ink);padding-bottom:12px;margin-bottom:16px}
header h1{margin:0 0 6px;font-size:1.4rem}header p{margin:0;color:var(--mut)}
.banner{background:var(--warnbg);border:1px solid #e0c684;color:var(--warn);border-radius:8px;
padding:8px 12px;margin-top:10px;font-size:.9rem}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0}
.chip{padding:4px 12px;border-radius:999px;font-size:.85rem;font-weight:600}
.chip.pass{background:var(--okbg);color:var(--ok)}
.chip.other{background:var(--warnbg);color:var(--warn)}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:20px 24px;margin:16px 0}
.card h1,.sec h1{font-size:1.25rem;border-bottom:1px solid var(--line);padding-bottom:8px;margin-top:0}
.sec h2{font-size:1.05rem;margin-top:0;color:var(--accent)}
.sec{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px 24px;margin:12px 0}
table{border-collapse:collapse;width:100%;margin:10px 0;font-size:.92rem;display:block;overflow-x:auto}
th,td{border:1px solid var(--line);padding:6px 10px;text-align:left;vertical-align:top}
th{background:var(--bg)}code{background:#f1efeb;padding:1px 5px;border-radius:4px;font-size:.88em}
pre{background:#f1efeb;padding:12px;border-radius:8px;overflow-x:auto}
.note{color:var(--mut);font-size:.88rem}
.btn{border:0;border-radius:8px;padding:7px 14px;font:600 .9rem inherit;cursor:pointer}
.btn.ok{background:var(--ok);color:#fff}.btn.rw{background:var(--accent);color:#fff}
.btn:disabled{opacity:.45;cursor:default}
/* annotations */
.ann{position:relative}
.ann .annbtn{position:absolute;top:8px;right:8px;border:1px solid var(--line);background:var(--card);
color:var(--mut);border-radius:7px;font:600 .75rem inherit;padding:2px 8px;cursor:pointer;
opacity:0;transition:opacity .15s}
.ann:hover .annbtn{opacity:1}
.ann.has .annbtn{opacity:1;background:var(--warnbg);color:var(--warn);border-color:#e0c684}
.annbox{margin-top:8px;display:none}
.annbox textarea,#fb{width:100%;min-height:60px;border:1px solid var(--line);border-radius:8px;
padding:8px;font:inherit}
.annbox .row{display:flex;gap:8px;margin-top:5px}
.mini{border:1px solid var(--line);background:var(--card);border-radius:7px;font:600 .8rem inherit;
padding:3px 10px;cursor:pointer}
/* decision bar (always visible; only the notes/feedback area folds) */
#bar{position:fixed;left:0;right:0;bottom:0;z-index:35;background:#fffdf8;
border-top:2px solid var(--accent);box-shadow:0 -6px 24px rgba(0,0,0,.12)}
#bar .head{display:flex;align-items:center;gap:10px;padding:8px 18px;flex-wrap:wrap}
#bar .cnt{background:var(--accent);color:#fff;border-radius:999px;font-size:.78rem;font-weight:700;
padding:2px 10px;cursor:pointer}
#bar .inner{display:none;max-height:46vh;overflow:auto;padding:0 18px 14px}
#bar.open .inner{display:block}
#bar .annitem{border:1px solid var(--line);border-radius:8px;padding:7px 11px;margin:6px 0;
font-size:.86rem;background:var(--card);display:flex;gap:10px;align-items:flex-start}
#bar .annitem .t{font-weight:700;color:var(--accent);flex:0 0 auto}
#bar .annitem .rm{margin-left:auto;border:0;background:none;color:var(--bad);cursor:pointer;font-weight:700}
.lstat{display:flex;align-items:center;gap:8px;font-size:.86rem;flex:1;min-width:160px;overflow:hidden}
.lstat #lstext{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.lstat .dot{width:10px;height:10px;border-radius:50%;flex:0 0 10px}
.lstat .dot.on{background:var(--ok)}.lstat .dot.off{background:#bbb}
.lstat .dot.busy{background:var(--accent);animation:pulse 1.1s infinite}
.lstat .dot.warn{background:var(--bad);animation:pulse 1.1s infinite}
@keyframes pulse{50%{opacity:.35}}
.lstat .spin{width:13px;height:13px;border:2px solid var(--line);border-top-color:var(--accent);
border-radius:50%;animation:rot .8s linear infinite;flex:0 0 13px}
@keyframes rot{to{transform:rotate(360deg)}}
#token{display:none;margin-top:10px}
#token pre{white-space:pre-wrap;word-break:break-all;background:#f0ede7;padding:10px;border-radius:8px;font-size:.8rem}
@media(max-width:420px){.sec,.card{padding:12px 14px}}
"""

JS = """
/* ---- per-section annotations ---- */
var ANN={};
document.querySelectorAll('.ann').forEach(function(el){
  var id=el.dataset.ann;
  var b=document.createElement('button');b.className='annbtn';b.textContent='\\u270e annotate';
  var box=document.createElement('div');box.className='annbox';
  var ta=document.createElement('textarea');
  ta.placeholder='Comment on \\u201c'+id+'\\u201d \\u2014 sent with your decision as a targeted instruction';
  var row=document.createElement('div');row.className='row';
  var save=document.createElement('button');save.className='mini';save.textContent='Save';
  var cancel=document.createElement('button');cancel.className='mini';cancel.textContent='Cancel';
  b.onclick=function(e){e.stopPropagation();box.style.display=box.style.display==='block'?'none':'block';ta.focus();};
  save.onclick=function(){var v=ta.value.trim();if(v)ANN[id]=v;else delete ANN[id];box.style.display='none';renderAnn();};
  cancel.onclick=function(){box.style.display='none';};
  row.appendChild(save);row.appendChild(cancel);box.appendChild(ta);box.appendChild(row);
  el.appendChild(b);el.appendChild(box);
});
function renderAnn(){
  var keys=Object.keys(ANN);
  document.getElementById('anncnt').textContent=keys.length+' \\u270e';
  document.querySelectorAll('.ann').forEach(function(el){el.classList.toggle('has',!!ANN[el.dataset.ann]);});
  document.getElementById('annlist').innerHTML=keys.length?keys.map(function(k){
    return '<div class="annitem"><span class="t">'+k+'</span><span>'+ANN[k].replace(/</g,'&lt;')+'</span>'+
      '<button class="rm" data-k="'+k+'">\\u2715</button></div>';}).join('')
    :'<p class="note">No annotations yet. Hover a section and hit \\u270e to attach a comment to it.</p>';
  document.querySelectorAll('#annlist .rm').forEach(function(b){
    b.onclick=function(){delete ANN[b.dataset.k];renderAnn();};});
}
/* ---- decision ---- */
function payload(decision){
  var p={gate:GATE,page:'gate',decision:decision};
  var fb=document.getElementById('fb').value.trim();
  if(fb)p.feedback=fb;
  var ann=Object.keys(ANN).map(function(k){return {target:k,comment:ANN[k]};});
  if(ann.length)p.annotations=ann;
  return p;
}
function emit(decision){
  var p=payload(decision);
  if(decision==='rework'&&!p.feedback&&!p.annotations){
    document.getElementById('bar').classList.add('open');
    document.getElementById('fb').focus();
    setStatus('warn',null,'rework needs instructions \\u2014 annotate a section or type feedback below');
    return;
  }
  fetch('/gate/answer',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify(p)}).then(function(r){
    if(!r.ok)throw new Error();
    setStatus('busy','spin',decision+' sent \\u2014 waiting for the agent to pick it up\\u2026');
    document.getElementById('btn-approve').disabled=true;
    document.getElementById('btn-rework').disabled=true;
  }).catch(function(){
    var tok='ANSWERS<<< '+JSON.stringify(p)+' >>>ANSWERS';
    document.getElementById('bar').classList.add('open');
    document.getElementById('token').style.display='block';
    document.getElementById('tokval').textContent=tok;
    if(navigator.clipboard)navigator.clipboard.writeText(tok).catch(function(){});
  });
}
/* ---- live agent link ---- */
var baseVersion=null;
function setStatus(dot,icon,text){
  document.getElementById('livestatus').innerHTML=
    (icon==='spin'?'<span class="spin"></span>':'<span class="dot '+dot+'"></span>')+
    '<span id="lstext">'+text+'</span>';
}
function poll(){
  fetch('/gate/state?ts='+Date.now()).then(function(r){return r.json();}).then(function(s){
    if(baseVersion===null)baseVersion=s.version||0;
    if((s.version||0)>baseVersion){
      setStatus('busy','spin','updated \\u2014 reloading the page\\u2026');
      setTimeout(function(){location.reload();},800);return;
    }
    var age=s.updated?Math.round(Date.now()/1000-s.updated):null;
    var stale=age!==null&&age>90;
    if(s.state==='needs-console'){
      setStatus('warn',null,'\\u26a0 the agent needs you in the console: '+(s.message||'a question only you can answer'));
    }else if(s.state==='working'){
      setStatus('busy','spin',(s.message||'agent is working \\u2014 hold on')+
        (stale?' (no update for a while \\u2014 it may be deep in a step)':''));
    }else if(s.state==='idle'){
      setStatus(stale?'off':'on',null,stale?
        'agent link stale \\u2014 buttons fall back to the copy-paste token if sending fails':
        'agent is listening \\u2014 Approve / Request rework act directly, no copy-paste');
    }else{
      setStatus('off',null,'agent link: unknown state');
    }
    setTimeout(poll,2500);
  }).catch(function(){
    setStatus('off',null,'no agent link (static file?) \\u2014 buttons fall back to the copy-paste token');
    setTimeout(poll,5000);
  });
}
document.getElementById('btn-approve').onclick=function(){emit('approve');};
document.getElementById('btn-rework').onclick=function(){emit('rework');};
document.getElementById('anncnt').onclick=function(){document.getElementById('bar').classList.toggle('open');};
renderAnn();poll();
"""


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--artifact", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--gate", default="review", help="decision id, echoed in the answer payload")
    p.add_argument("--verdicts", default="{}", help='JSON: {"intent":{"verdict":"pass","findings":[]}}')
    p.add_argument("--banner", default="", help="optional notice, e.g. 'Reworked from your gate answer (round 2)'")
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
    banner_html = f'<div class="banner">↻ {inline(a.banner)}</div>' if a.banner else ""

    title = f"{a.gate.replace('_', ' ').title()} gate — {Path(a.artifact).name}"
    page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>{CSS}</style></head><body><div class="wrap">
<header><h1>{html.escape(title)}</h1>
<p>Review the artifact, annotate sections with ✎, then decide in the bar below. Approve / Request
rework reach the agent directly when it is listening; otherwise they fall back to a copy-paste token.</p>
{banner_html}
<div class="chips">{''.join(chips)}</div></header>
{findings_html}
{artifact_html(md)}
<p class="note">Markdown artifact is the source of truth: {html.escape(a.artifact)}</p>
</div>
<div id="bar">
  <div class="head">
    <span id="livestatus" class="lstat"><span class="dot off"></span><span id="lstext">checking agent link…</span></span>
    <span class="cnt" id="anncnt" title="annotations — click to review">0 ✎</span>
    <button class="btn ok" id="btn-approve">Approve</button>
    <button class="btn rw" id="btn-rework">Request rework</button>
  </div>
  <div class="inner">
    <div id="annlist"></div>
    <label class="note" for="fb">General feedback (optional for approve; rework needs this or annotations)</label>
    <textarea id="fb" placeholder="What should change?"></textarea>
    <div id="token"><p class="note">Agent link unavailable — copied to clipboard, paste into the chat:</p><pre id="tokval"></pre></div>
  </div>
</div>
<script>var GATE={json.dumps(a.gate)};{JS}</script></body></html>"""

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    print(out)


if __name__ == "__main__":
    sys.exit(main())
