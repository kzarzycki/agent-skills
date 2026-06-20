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


def parse_table(lines):
    """Pull the first markdown table out of a block; returns (header, rows) or None."""
    rows = [
        [c.strip() for c in ln.strip().strip("|").split("|")]
        for ln in lines
        if ln.strip().startswith("|")
    ]
    if len(rows) < 2:
        return None
    header, body = rows[0], rows[1:]
    if body and all(re.fullmatch(r":?-{2,}:?", c) for c in body[0]):
        body = body[1:]
    return (header, body) if body else None


def _sentiment(cell):
    """Tint a scorecard cell only on unambiguous leading sentiment; else neutral."""
    low = cell.strip().lower()
    if low.startswith(("yes", "strong", "good", "full ")):
        return "pos", "✓"
    if low.startswith(("at risk", "weaker", "coarse", "too coarse", "depends")) or "must audit" in low:
        return "neg", "⚠"
    if low.startswith(("identical", "same", "equivalent")):
        return "eq", "="
    return "neu", ""


def w_score_matrix(body):
    """Scorecard widget: needs as sticky rows, options as sticky columns, sentiment-
    tinted cells with full text on hover, and a clear-yes fit row. Deterministic from
    the markdown table; no invented numeric scores. Falls back (None) if no table."""
    parsed = parse_table(body)
    if not parsed:
        return None
    header, rows = parsed
    opts = header[1:]
    fit = [0] * len(opts)
    trs = []
    for r in rows:
        need, cells = r[0], r[1:]
        tds = []
        for j, c in enumerate(cells):
            cls, mark = _sentiment(c)
            if cls == "pos":
                fit[j] += 1
            tds.append(
                f'<td class="sm-{cls}" title="{html.escape(c, quote=True)}">'
                f'<span class="mk">{mark}</span><span class="txt">{inline(c)}</span></td>'
            )
        trs.append(
            f'<tr><th scope="row" title="{html.escape(need, quote=True)}">{inline(need)}</th>'
            f'{"".join(tds)}</tr>'
        )
    maxfit = max(fit) if fit else 0
    ths = "".join(f'<th scope="col">{inline(o)}</th>' for o in opts)
    foot = ""
    for j, o in enumerate(opts):
        w = int(round(100 * fit[j] / maxfit)) if maxfit else 0
        lead = ' class="lead"' if maxfit and fit[j] == maxfit else ""
        foot += f'<td{lead}><div class="fitbar"><i style="width:{w}%"></i></div><small>{fit[j]} clear-yes</small></td>'
    return (
        '<div class="smwrap"><table class="score-matrix">'
        f'<thead><tr><th scope="col">{inline(header[0])}</th>{ths}</tr></thead>'
        f'<tbody>{"".join(trs)}</tbody>'
        f'<tfoot><tr><th scope="row">fit</th>{foot}</tr></tfoot></table>'
        '<p class="smnote">Cells tinted on clear sentiment only (✓ yes · ⚠ caution · = parity); '
        'hover any cell for its full text. The fit row counts clear-yes cells as a reading aid — '
        'not a weighted score (weighted scoring needs per-need numbers the markdown does not carry).</p></div>'
    )


def w_option_cards(body):
    """Options widget: each `### Option …` H3 becomes a selectable card with its prose
    folded. Clicking a card records `chosenOption` (the override the rework loop reads).
    Intro prose and a trailing bold-led note render around the cards. Falls back if no H3s."""
    text = "\n".join(body)
    parts = re.split(r"(?m)^### +", text)
    if len(parts) < 2:
        return None
    intro = re.sub(r"(?m)^## +.*\n?", "", parts[0], count=1).strip()
    chunks = parts[1:]
    cards, trailing, selectable = [], "", False
    for idx, chunk in enumerate(chunks):
        lines = chunk.split("\n")
        title, rest = lines[0].strip(), "\n".join(lines[1:]).strip()
        if idx == len(chunks) - 1:
            sm = re.search(r"\n\n(\*\*.+)$", rest, re.S)
            if sm:
                trailing, rest = sm.group(1).strip(), rest[: sm.start()].strip()
        mo = re.match(r"Option\s+([A-Za-z0-9]+)\b", title)
        data = ""
        pick = ""
        if mo:
            selectable = True
            data = f' data-opt="{html.escape(mo.group(1), quote=True)}"'
            pick = '<span class="opt-pick">✓ your choice</span>'
        body_html = md_to_html(rest) if rest else ""
        cards.append(
            f'<div class="opt-card"{data}><div class="opt-head">'
            f'<span class="opt-title">{inline(title)}</span>{pick}</div>'
            f"<details><summary>details</summary>{body_html}</details></div>"
        )
    intro_html = f'<p class="optintro">{inline(intro)}</p>' if intro else ""
    note = (
        '<p class="smnote">Click an option to record your pick — on rework it routes to the '
        "author as an override; the artifact's recommendation stands otherwise.</p>"
        if selectable
        else ""
    )
    trail_html = md_to_html(trailing) if trailing else ""
    return f'{intro_html}<div class="optcards">{"".join(cards)}</div>{note}{trail_html}'


def _fold_table(body, summary_from_header):
    """Shared shape for label→detail tables: headline row, remaining cells folded."""
    parsed = parse_table(body)
    if not parsed:
        return None
    header, rows = parsed
    return header, rows


def w_decision_table(body):
    """Key-decisions widget: each row becomes `Decision → Choice` with the rationale folded."""
    parsed = _fold_table(body, 2)
    if not parsed:
        return None
    header, rows = parsed
    fold_label = inline(header[2]) if len(header) > 2 else "why"
    items = []
    for r in rows:
        label = f"<b>{inline(r[0])}</b>"
        if len(r) > 1 and r[1]:
            label += f' <span class="darrow">→</span> {inline(r[1])}'
        det = (
            f"<details><summary>{fold_label}</summary><div>{inline(r[2])}</div></details>"
            if len(r) > 2 and r[2]
            else ""
        )
        items.append(f'<div class="dcard"><div class="dhead">{label}</div>{det}</div>')
    return f'<div class="dlist">{"".join(items)}</div>'


def w_risk_list(body):
    """Risks widget: each row becomes a risk headline with its mitigation folded."""
    parsed = _fold_table(body, 1)
    if not parsed:
        return None
    header, rows = parsed
    fold_label = inline(header[1]) if len(header) > 1 else "mitigation"
    items = []
    for r in rows:
        det = (
            f"<details><summary>{fold_label}</summary><div>{inline(r[1])}</div></details>"
            if len(r) > 1 and r[1]
            else ""
        )
        items.append(f'<div class="rcard"><div class="rrisk">⚠ {inline(r[0])}</div>{det}</div>')
    return f'<div class="rlist">{"".join(items)}</div>'


WIDGETS = {
    "score-matrix": w_score_matrix,
    "option-cards": w_option_cards,
    "decision-table": w_decision_table,
    "risk-list": w_risk_list,
}


def artifact_html(md, display=None):
    """Wrap the H1 preamble and each H2 section in an annotatable block. Sections named
    in the contract's `display` map render through a widget instead of prose."""
    display = display or {}
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
        widget = WIDGETS.get(display.get(head)) if head else None
        content = widget(body) if widget else None
        if content is not None:
            content = f"<h2>{inline(head)}</h2>{content}"
        else:
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
/* score-matrix widget */
.smwrap{overflow-x:auto;border:1px solid var(--line);border-radius:10px}
.score-matrix{display:table;border-collapse:separate;border-spacing:0;width:100%;margin:0;font-size:.86rem}
.score-matrix th,.score-matrix td{border-bottom:1px solid var(--line);border-right:1px solid var(--line);
padding:7px 9px;text-align:left;vertical-align:top}
.score-matrix thead th{position:sticky;top:0;z-index:2;background:var(--bg);font-size:.84rem}
.score-matrix tbody th[scope=row],.score-matrix tfoot th{position:sticky;left:0;z-index:1;background:var(--card);
font-weight:600;min-width:120px;max-width:160px}
.score-matrix thead th:first-child{position:sticky;left:0;z-index:3}
.score-matrix td{min-width:150px}
.score-matrix td .mk{font-weight:700;margin-right:5px}
.score-matrix td .txt{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.score-matrix td.sm-pos{background:#f0f8f2}.score-matrix td.sm-pos .mk{color:var(--ok)}
.score-matrix td.sm-neg{background:#fff6ec}.score-matrix td.sm-neg .mk{color:var(--accent)}
.score-matrix td.sm-eq{background:#f7f7f5}.score-matrix td.sm-eq .mk{color:var(--mut)}
.score-matrix tfoot td{background:var(--bg);font-size:.8rem}
.score-matrix tfoot td.lead{box-shadow:inset 0 2px 0 var(--ok)}
.fitbar{height:6px;background:#e7e4de;border-radius:3px;overflow:hidden;margin-bottom:3px}
.fitbar i{display:block;height:100%;background:var(--ok)}
.smnote{color:var(--mut);font-size:.8rem;margin:8px 2px 0}
/* shared fold styling */
.sec details{margin-top:4px}
.sec summary{cursor:pointer;font-size:.84rem;color:var(--accent);font-weight:600;list-style:none}
.sec summary::-webkit-details-marker{display:none}
.sec summary::before{content:"▸ ";color:var(--mut)}
.sec details[open] summary::before{content:"▾ "}
.sec details>div,.opt-card details .full{margin-top:6px;font-size:.92rem}
/* option cards */
.optintro{margin:0 0 12px}
.optcards{display:flex;flex-direction:column;gap:10px}
.opt-card{border:1px solid var(--line);border-radius:9px;padding:12px 14px;transition:border-color .15s,background .15s}
.opt-card[data-opt]{cursor:pointer}
.opt-card[data-opt]:hover{border-color:var(--accent)}
.opt-card.sel{border-color:var(--ok);background:var(--okbg)}
.opt-head{display:flex;align-items:center;gap:10px}
.opt-title{font-weight:700;font-size:1rem}
.opt-pick{display:none;margin-left:auto;background:var(--ok);color:#fff;border-radius:999px;
font-size:.74rem;font-weight:700;padding:2px 9px}
.opt-card.sel .opt-pick{display:inline-block}
/* decision list */
.dlist,.rlist{display:flex;flex-direction:column;gap:8px}
.dcard,.rcard{border:1px solid var(--line);border-radius:8px;padding:9px 12px}
.dhead{font-size:.95rem}.darrow{color:var(--mut)}
.rrisk{font-weight:600;font-size:.93rem}.rcard{background:#fffaf4}
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
/* ---- option choice (option-cards widget) ---- */
var CHOICE=null;
document.querySelectorAll('.opt-card[data-opt]').forEach(function(c){
  c.addEventListener('click',function(e){
    if(e.target.tagName==='SUMMARY'||e.target.closest('details'))return;
    CHOICE=c.dataset.opt;
    document.querySelectorAll('.opt-card[data-opt]').forEach(function(o){
      o.classList.toggle('sel',o===c);});
    setStatus('on',null,'option '+CHOICE+' picked \\u2014 Request rework to send it as an override, or Approve to keep the recommendation');
  });
});
/* ---- decision ---- */
function payload(decision){
  var p={gate:GATE,page:'gate',decision:decision};
  var fb=document.getElementById('fb').value.trim();
  if(fb)p.feedback=fb;
  if(CHOICE)p.chosenOption=CHOICE;
  var ann=Object.keys(ANN).map(function(k){return {target:k,comment:ANN[k]};});
  if(ann.length)p.annotations=ann;
  return p;
}
function emit(decision){
  var p=payload(decision);
  if(decision==='rework'&&!p.feedback&&!p.annotations&&!p.chosenOption){
    document.getElementById('bar').classList.add('open');
    document.getElementById('fb').focus();
    setStatus('warn',null,'rework needs instructions \\u2014 pick an option, annotate a section, or type feedback');
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
    p.add_argument("--contract", default=None,
                   help="contract JSON; its `display` map upgrades named sections to widgets")
    a = p.parse_args()

    md = Path(a.artifact).read_text(encoding="utf-8")
    display = {}
    if a.contract:
        try:
            display = json.loads(Path(a.contract).read_text(encoding="utf-8")).get("display", {})
        except Exception:
            display = {}
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
{artifact_html(md, display)}
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
