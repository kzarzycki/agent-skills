// Claude.ai Research report extraction — HTML → Markdown
// Runs in page context via javascript_tool(). Copies markdown to clipboard.
// Returns only a status string with char count — never the content itself.
//
// Usage: pass this entire script to javascript_tool() when the Copy button
// produces empty or unformatted output.

(() => {
  // Find assistant message containers — Claude.ai uses various container patterns.
  // Strategy: find the largest text block that looks like a research response.

  // Try known patterns first
  const candidates = [
    // Claude.ai assistant messages — try data attributes
    ...document.querySelectorAll('[data-role="assistant"]'),
    ...document.querySelectorAll('[data-is-bot-message="true"]'),
    // Markdown-rendered content blocks
    ...document.querySelectorAll('.prose'),
    ...document.querySelectorAll('.markdown'),
  ];

  let target = null;
  let maxLen = 0;

  // Find the largest content block among candidates
  for (const el of candidates) {
    const len = el.innerText.length;
    if (len > maxLen) {
      maxLen = len;
      target = el;
    }
  }

  // Fallback: find the largest div with substantial text
  if (!target || maxLen < 500) {
    const divs = document.querySelectorAll('div');
    for (const d of divs) {
      const len = d.innerText.length;
      // Skip the entire page body, look for content containers
      if (len > maxLen && len < 200000 && d !== document.body && d.children.length > 3) {
        maxLen = len;
        target = d;
      }
    }
  }

  if (!target || target.innerText.length < 500) {
    return 'ERROR: No research report content found on page';
  }

  function htmlToMd(el) {
    let md = '';
    for (const node of el.childNodes) {
      if (node.nodeType === 3) {
        // Text node
        md += node.textContent;
      } else if (node.nodeType === 1) {
        const tag = node.tagName.toLowerCase();
        switch (tag) {
          case 'h1': md += '# ' + node.textContent.trim() + '\n\n'; break;
          case 'h2': md += '## ' + node.textContent.trim() + '\n\n'; break;
          case 'h3': md += '### ' + node.textContent.trim() + '\n\n'; break;
          case 'h4': md += '#### ' + node.textContent.trim() + '\n\n'; break;
          case 'p': md += htmlToMd(node) + '\n\n'; break;
          case 'strong': case 'b': md += '**' + htmlToMd(node) + '**'; break;
          case 'em': case 'i': md += '*' + htmlToMd(node) + '*'; break;
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
          case 'div': case 'span': case 'section': case 'article':
            md += htmlToMd(node);
            break;
          default: md += htmlToMd(node); break;
        }
      }
    }
    return md;
  }

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

  const markdown = htmlToMd(target).replace(/\n{3,}/g, '\n\n').trim();
  const charCount = markdown.length;
  const lineCount = markdown.split('\n').length;

  // Copy to clipboard
  navigator.clipboard.writeText(markdown).then(() => {
    // Success — handled by return below
  }).catch(err => {
    // Fallback: create a textarea and copy
    const ta = document.createElement('textarea');
    ta.value = markdown;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
  });

  return `Report copied: ${charCount} chars, ${lineCount} lines`;
})()
