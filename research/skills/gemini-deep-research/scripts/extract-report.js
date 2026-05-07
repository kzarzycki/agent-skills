// extract-report.js — Gemini Deep Research report extractor
// Runs in page context via javascript_tool(). Converts HTML report to markdown,
// copies to clipboard. Returns only a status string (not the content itself).
//
// Usage: Read this file, pass its content to javascript_tool({ action: 'javascript_exec', text: <content>, tabId: <id> })
// Then run: pbpaste > <output_path>
//
// IMPORTANT: Do NOT wrap in async/await — the Chrome extension disconnects on async IIFEs.
// navigator.clipboard.writeText() is called fire-and-forget (without await).
// First run on a Gemini page may prompt the user to "Allow" clipboard access.

const panels = document.querySelectorAll('.markdown.markdown-main-panel');
let report = null; let maxLen = 0;
panels.forEach(p => { const len = p.innerText?.length || 0; if (len > maxLen) { maxLen = len; report = p; } });
if (!report || maxLen < 500) {
  'ERROR: No report panel found (or content too short: ' + maxLen + ' chars)';
} else {
  // Walk DOM and convert to markdown
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

  // Fire-and-forget clipboard write (no await — async disconnects the extension)
  navigator.clipboard.writeText(md);

  'Report copied: ' + md.length + ' chars, ' + md.split('\n').length + ' lines';
}
