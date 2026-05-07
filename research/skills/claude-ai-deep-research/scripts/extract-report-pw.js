// Claude.ai Research report extraction for playwright-cli.
//
// Runs inside pw-driver.py's eval_json wrapper, which prepends JS_HELPERS and
// wraps the body in `JSON.stringify((() => { <body> })())`. So this file is a
// plain block of statements ending in a `return` that yields the result
// object. Do NOT wrap this file in its own IIFE.
//
// Contract:
//   Returns { ok: true,  markdown: <string> }
//        or { ok: false, reason: <string>  }
//
// Strategy:
//  1. If claude.ai created an artifact/document, open it (click "Open artifact" button).
//  2. Find the response content element via known selectors, falling back to
//     the largest div that doesn't start with sidebar navigation.
//  3. Convert its HTML to markdown and return the string directly. We do NOT
//     touch navigator.clipboard — headless Chromium doesn't grant clipboard
//     permission reliably, and we don't need it.

// Find the response content element
// (artifact/document is opened by the driver before calling this script)
// Priority 1: known claude.ai response container classes
const pickLargest = function(els) {
  var best = null;
  var bestLen = 0;
  for (var i = 0; i < els.length; i++) {
    var len = (els[i].innerText || '').length;
    if (len > bestLen) { bestLen = len; best = els[i]; }
  }
  return { el: best, len: bestLen };
};

// font-claude-response: used for artifact/document content panel
// [data-role="assistant"]: classic assistant message wrapper
// .prose / .markdown: older claude.ai response classes
const namedCandidates = [
  ...document.querySelectorAll('.font-claude-response'),
  ...document.querySelectorAll('[data-role="assistant"]'),
  ...document.querySelectorAll('[data-is-bot-message="true"]'),
  ...document.querySelectorAll('.prose'),
  ...document.querySelectorAll('.markdown'),
];

let picked = pickLargest(namedCandidates);

// Priority 2: largest div that doesn't begin with sidebar navigation
if (!picked.el || picked.len < 500) {
  const divs = Array.from(document.querySelectorAll('div'));
  var best = null;
  var bestLen = 0;
  for (var i = 0; i < divs.length; i++) {
    const d = divs[i];
    const t = (d.innerText || '').trim();
    // Skip sidebar (starts with "New chat") and very large page wrappers
    if (t.startsWith('New chat')) continue;
    if (t.length > bestLen && t.length < 200000 && d !== document.body) {
      bestLen = t.length;
      best = d;
    }
  }
  if (best && bestLen > 500) picked = { el: best, len: bestLen };
}

if (!picked.el || picked.len < 500) {
  return { ok: false, reason: 'no_report_content' };
}

// ---- HTML → Markdown conversion (preserved verbatim from extract-report.js) ----

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
