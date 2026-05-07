// ChatGPT Deep Research report extraction for playwright-cli.
//
// Runs inside pw-driver.py's eval_json_in_root_frame wrapper, which prepends
// JS_HELPERS and evaluates this block inside the nested `root` iframe that
// hosts the completed research report. The main chatgpt.com page holds only
// the composer and sidebar — the report lives in the iframe at
// connector_openai_deep_research.web-sandbox.oaiusercontent.com -> root.
//
// Contract:
//   Returns { ok: true,  markdown: <string>, chars: <number> }
//        or { ok: false, reason: <string>  }
//
// Strategy:
//  1. Primary: `div[class*="_reportPage_"]` — the CSS-module-hashed wrapper
//     that contains h1, h2s, paragraphs, tables of the finished report.
//  2. Fallback: the deepest ancestor containing the h1 and all h2s.
//  3. Convert HTML to markdown with htmlToMd() below.

// ---- Element selection ----

let picked = { el: null, len: 0 };

// Primary: _reportPage_ wrapper (stable across ChatGPT deploys — the class
// hash changes but the `_reportPage_` prefix persists).
const reportEls = Array.from(document.querySelectorAll('div[class*="_reportPage_"]'));
if (reportEls.length) {
  let best = null;
  let bestLen = 0;
  for (const el of reportEls) {
    const len = (el.innerText || '').length;
    if (len > bestLen) { bestLen = len; best = el; }
  }
  if (best && bestLen > 500) picked = { el: best, len: bestLen };
}

// Fallback: smallest ancestor of h1 that also contains every h2.
if (!picked.el || picked.len < 500) {
  const h1 = document.querySelector('h1');
  const h2s = Array.from(document.querySelectorAll('h2'));
  if (h1 && h2s.length) {
    let candidate = h1.parentElement;
    while (candidate) {
      if (h2s.every(h => candidate.contains(h))) break;
      candidate = candidate.parentElement;
    }
    if (candidate) {
      const len = (candidate.innerText || '').length;
      if (len > 500) picked = { el: candidate, len };
    }
  }
}

if (!picked.el || picked.len < 500) {
  return { ok: false, reason: 'no_report_content' };
}

// ---- HTML -> Markdown conversion (from extract-report.js, verbatim) ----

function extractTable(table) {
  let md = '';
  const rows = table.querySelectorAll('tr');
  rows.forEach((row, i) => {
    const cells = row.querySelectorAll('td, th');
    md += '| ' + Array.from(cells).map(c => c.textContent.trim()).join(' | ') + ' |\n';
    if (i === 0) {
      md += '|' + Array.from(cells).map(() => ' --- ').join('|') + '|\n';
    }
  });
  return md;
}

function htmlToMd(el) {
  let md = '';
  for (const node of el.childNodes) {
    if (node.nodeType === 3) {
      md += node.textContent;
      continue;
    }
    if (node.nodeType !== 1) continue;
    const tag = node.tagName.toLowerCase();
    switch (tag) {
      case 'h1': md += '# ' + node.textContent.trim() + '\n\n'; break;
      case 'h2': md += '## ' + node.textContent.trim() + '\n\n'; break;
      case 'h3': md += '### ' + node.textContent.trim() + '\n\n'; break;
      case 'h4': md += '#### ' + node.textContent.trim() + '\n\n'; break;
      case 'p':  md += htmlToMd(node) + '\n\n'; break;
      case 'strong':
      case 'b':  md += '**' + htmlToMd(node) + '**'; break;
      case 'em':
      case 'i':  md += '*' + htmlToMd(node) + '*'; break;
      case 'code':
        if (node.parentElement && node.parentElement.tagName.toLowerCase() === 'pre') {
          md += node.textContent;
        } else {
          md += '`' + node.textContent + '`';
        }
        break;
      case 'pre': md += '```\n' + node.textContent + '\n```\n\n'; break;
      case 'blockquote': md += '> ' + htmlToMd(node).replace(/\n/g, '\n> ') + '\n\n'; break;
      case 'a':
        md += '[' + node.textContent + '](' + (node.href || '') + ')';
        break;
      case 'ul': md += htmlToMd(node) + '\n'; break;
      case 'ol': md += htmlToMd(node) + '\n'; break;
      case 'li': {
        const parent = node.parentElement;
        const prefix = parent && parent.tagName.toLowerCase() === 'ol'
          ? (Array.from(parent.children).indexOf(node) + 1) + '. '
          : '- ';
        md += prefix + htmlToMd(node).trim() + '\n';
        break;
      }
      case 'table': md += extractTable(node) + '\n\n'; break;
      case 'hr': md += '---\n\n'; break;
      case 'br': md += '\n'; break;
      case 'sup': md += '^' + node.textContent + '^'; break;
      case 'div':
      case 'span':
      case 'section':
      case 'article':
        md += htmlToMd(node);
        break;
      default:
        md += htmlToMd(node);
        break;
    }
  }
  return md;
}

const markdown = htmlToMd(picked.el).replace(/\n{3,}/g, '\n\n').trim();

if (markdown.length < 500) {
  return { ok: false, reason: 'markdown_too_small', len: markdown.length };
}

return { ok: true, markdown: markdown, chars: markdown.length };
