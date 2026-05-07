// Gemini Deep Research report extraction for playwright-cli.
//
// Runs inside pw-driver.py's eval_json wrapper, which prepends JS_HELPERS and
// wraps the body in `JSON.stringify((() => { <body> })())`. So this file is a
// plain block of statements ending in a `return` that yields the result
// object. Do NOT wrap this file in its own IIFE.
//
// Contract:
//   Returns { ok: true,  markdown: <string>, chars: <number> }
//        or { ok: false, reason: <string>  }
//
// Strategy:
//  1. Find the report container via `.markdown.markdown-main-panel` (pick
//     largest by innerText length — Gemini may render multiple).
//  2. Fallback: largest div >500 chars that doesn't start with navigation text.
//  3. Convert HTML to markdown using the Gemini-specific `cn()` converter
//     (handles CODE-BLOCK, MAT-ICON, and other Gemini-specific tags).
//  4. Return the markdown string directly. We do NOT touch navigator.clipboard
//     — headless Chromium doesn't grant clipboard permission reliably.

// Priority 1: Gemini report panel `.markdown.markdown-main-panel`
const panels = document.querySelectorAll('.markdown.markdown-main-panel');
let report = null;
let maxLen = 0;
panels.forEach(function(p) {
  const len = (p.innerText || '').length;
  if (len > maxLen) { maxLen = len; report = p; }
});

// Priority 2: largest div >500 chars that doesn't start with navigation
if (!report || maxLen < 500) {
  const divs = Array.from(document.querySelectorAll('div'));
  var best = null;
  var bestLen = 0;
  for (var i = 0; i < divs.length; i++) {
    const d = divs[i];
    const t = (d.innerText || '').trim();
    // Skip navigation-like content and page wrappers
    if (/^(Home|Gemini|Menu|Sign in|Google)/i.test(t)) continue;
    if (t.length > bestLen && t.length < 200000 && d !== document.body) {
      bestLen = t.length;
      best = d;
    }
  }
  if (best && bestLen > 500) { report = best; maxLen = bestLen; }
}

if (!report || maxLen < 500) {
  return { ok: false, reason: 'no_report_content (largest=' + maxLen + ' chars)' };
}

// ---- HTML -> Markdown conversion (Gemini-specific, from extract-report.js) ----
// Handles Gemini-specific tags: CODE-BLOCK, MAT-ICON, etc.

function cn(n, lt, li) {
  if (n.nodeType === 3) return n.textContent;
  if (n.nodeType !== 1) return '';
  const t = n.tagName;
  const ch = () => {
    let r = '', i = 0;
    n.childNodes.forEach(c => {
      if (c.nodeType === 1 && c.tagName === 'LI') i++;
      r += cn(c, t === 'UL' ? 'ul' : (t === 'OL' ? 'ol' : lt), i);
    });
    return r;
  };
  if (t === 'H1') return '# ' + n.textContent.trim() + '\n\n';
  if (t === 'H2') return '## ' + n.textContent.trim() + '\n\n';
  if (t === 'H3') return '### ' + n.textContent.trim() + '\n\n';
  if (t === 'H4') return '#### ' + n.textContent.trim() + '\n\n';
  if (t === 'P') return ch().trim() + '\n\n';
  if (t === 'B' || t === 'STRONG') return '**' + ch().trim() + '**';
  if (t === 'I' || t === 'EM') return '*' + ch().trim() + '*';
  if (t === 'CODE') {
    if (!n.closest('pre') && !n.closest('code-block')) return '`' + n.textContent + '`';
    return n.textContent;
  }
  if (t === 'PRE' || t === 'CODE-BLOCK') return '\n```\n' + n.textContent.trim() + '\n```\n\n';
  if (t === 'UL' || t === 'OL') return ch() + '\n';
  if (t === 'LI') return (lt === 'ol' ? (li + '. ') : '- ') + ch().trim() + '\n';
  if (t === 'TABLE') {
    let m = '\n';
    n.querySelectorAll('tr').forEach((r, ri) => {
      const c = Array.from(r.querySelectorAll('td, th')).map(x => x.textContent.trim());
      m += '| ' + c.join(' | ') + ' |\n';
      if (ri === 0) m += '| ' + c.map(() => '---').join(' | ') + ' |\n';
    });
    return m + '\n';
  }
  if (t === 'HR') return '\n---\n\n';
  if (t === 'BR') return '\n';
  if (t === 'A') {
    const href = n.getAttribute('href');
    const text = ch().trim();
    return href ? '[' + text + '](' + href + ')' : text;
  }
  if (t === 'BUTTON' || t === 'MAT-ICON') return '';
  return ch();
}

const md = cn(report, null, 0).replace(/\n{3,}/g, '\n\n').trim();

if (md.length < 500) {
  return { ok: false, reason: 'markdown_too_small', len: md.length };
}

return { ok: true, markdown: md, chars: md.length };
