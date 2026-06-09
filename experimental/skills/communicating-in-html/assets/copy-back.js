/* copy-back.js — the bridge that turns a static HTML page into a two-way channel.
 *
 * A standalone .html file can't POST answers to the agent. Instead the page
 * gathers the user's input, serializes it to a compact token, and the user
 * pastes that token back into the chat. Inline this whole file into generated
 * interview/option pages (inside a <script> tag), then call:
 *
 *   CopyBack.init({ collect: () => ({ ... }), required: ['name'] });
 *
 * `collect` returns a plain object of answers. CopyBack renders a slim sticky
 * stripe (the token stays collapsed behind a toggle so it never covers the
 * screen or steals the page's scroll gesture on mobile), validates required
 * keys, and wires the Copy button.
 */
window.CopyBack = (function () {
  var lastToken = '';

  function ensurePanel() {
    var panel = document.getElementById('copyback');
    if (panel) return panel;
    panel = document.createElement('div');
    panel.id = 'copyback';
    panel.className = 'copyback';
    panel.innerHTML =
      '<button class="btn primary" id="cb-copy" type="button">Copy answers</button>' +
      '<span class="cb-msg" id="cb-msg"></span>' +
      '<button class="cb-toggle" id="cb-toggle" type="button">Show token</button>' +
      '<textarea id="cb-out" class="cb-out" readonly spellcheck="false" hidden></textarea>';
    document.querySelector('.wrap').appendChild(panel);
    return panel;
  }

  function setMsg(text) {
    var m = document.getElementById('cb-msg');
    if (m) m.textContent = text;
  }

  function init(cfg) {
    var required = cfg.required || [];

    function refresh() {
      ensurePanel();
      var data = cfg.collect() || {};
      var missing = required.filter(function (k) {
        var v = data[k];
        return v === undefined || v === null || v === '' ||
               (Array.isArray(v) && v.length === 0);
      });
      // Fenced marker so the agent can reliably find the payload.
      lastToken = 'ANSWERS<<<\n' + JSON.stringify(data, null, 2) + '\n>>>ANSWERS';
      document.getElementById('cb-out').value = lastToken;
      var btn = document.getElementById('cb-copy');
      if (missing.length) {
        btn.disabled = true;
        setMsg('Still needed: ' + missing.join(', '));
      } else {
        btn.disabled = false;
        setMsg('Ready — copy, then paste into the chat.');
      }
    }

    function revealToken() {
      var out = document.getElementById('cb-out');
      out.hidden = false;
      var t = document.getElementById('cb-toggle');
      if (t) t.textContent = 'Hide token';
    }

    document.addEventListener('input', refresh);
    document.addEventListener('change', refresh);
    document.addEventListener('click', function (e) {
      var id = e.target && e.target.id;
      if (id === 'cb-copy') {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(lastToken).then(
            function () { setMsg('Copied ✓ — paste it into the chat.'); },
            function () { manualCopy(); }
          );
        } else {
          manualCopy();
        }
      } else if (id === 'cb-toggle') {
        var out = document.getElementById('cb-out');
        out.hidden = !out.hidden;
        e.target.textContent = out.hidden ? 'Show token' : 'Hide token';
      }
    });

    // Fallback when the async clipboard API is blocked (e.g. file://):
    // reveal the token and select it so the user can copy by hand.
    function manualCopy() {
      revealToken();
      var out = document.getElementById('cb-out');
      out.focus(); out.select();
      try { document.execCommand('copy'); setMsg('Copied ✓ — paste it into the chat.'); }
      catch (_) { setMsg('Select the token above and copy it manually.'); }
    }

    refresh();
  }
  return { init: init };
})();
