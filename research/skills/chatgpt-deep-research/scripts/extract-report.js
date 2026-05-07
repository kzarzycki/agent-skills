// ChatGPT Deep Research report extraction — HTML → Markdown
// Runs in page context via javascript_tool(). Copies markdown to clipboard.
// Returns only a status string with char count — never the content itself.
//
// Usage: pass this entire script to javascript_tool() when "Copy contents"
// strips formatting or produces empty output.

(() => {
  // Find the last assistant message container
  const msgs = document.querySelectorAll('[data-message-author-role="assistant"]');
  if (!msgs.length) return 'ERROR: No assistant messages found';
  const lastMsg = msgs[msgs.length - 1];

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

  const markdown = htmlToMd(lastMsg);
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
