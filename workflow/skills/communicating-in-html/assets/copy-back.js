/* copy-back.js — the bridge that turns a static HTML page into a two-way channel.
 *
 * A standalone .html file can't POST answers to the agent. Instead the page
 * gathers the user's input, serializes it to a compact token, and the user
 * pastes that token back into the chat. Inline this whole file into generated
 * interview/option pages (inside a <script> tag), then call:
 *
 *   CopyBack.init({ collect: () => ({ ... }), required: ['name'] });
 *
 * `collect` returns a plain object of answers. CopyBack renders the sticky
 * panel, validates required keys, and wires the Copy button.
 */
window.CopyBack = (function () {
  function render(token) {
    var panel = document.getElementById('copyback');
    if (!panel) {
      panel = document.createElement('div');
      panel.id = 'copyback';
      panel.className = 'copyback';
      panel.innerHTML =
        '<div class="row"><strong>Step 2 — paste this back into the chat</strong>' +
        '<button class="btn primary" id="cb-copy" type="button">Copy answers</button></div>' +
        '<textarea id="cb-out" readonly spellcheck="false"></textarea>' +
        '<div class="muted" id="cb-msg" style="margin-top:8px;font-size:13px"></div>';
      document.querySelector('.wrap').appendChild(panel);
    }
    document.getElementById('cb-out').value = token;
  }

  function init(cfg) {
    var required = cfg.required || [];
    function refresh() {
      var data = cfg.collect() || {};
      var missing = required.filter(function (k) {
        var v = data[k];
        return v === undefined || v === null || v === '' ||
               (Array.isArray(v) && v.length === 0);
      });
      // Wrap in a fenced marker so the agent can reliably find the payload.
      var token = 'ANSWERS<<<\n' + JSON.stringify(data, null, 2) + '\n>>>ANSWERS';
      render(token);
      var btn = document.getElementById('cb-copy');
      var msg = document.getElementById('cb-msg');
      if (missing.length) {
        btn.disabled = true;
        msg.textContent = 'Still needed: ' + missing.join(', ');
      } else {
        btn.disabled = false;
        msg.textContent = 'Looks complete. Click copy, then paste into the chat.';
      }
    }
    document.addEventListener('input', refresh);
    document.addEventListener('change', refresh);
    document.addEventListener('click', function (e) {
      if (e.target && e.target.id === 'cb-copy') {
        var out = document.getElementById('cb-out');
        out.select();
        navigator.clipboard.writeText(out.value).then(function () {
          document.getElementById('cb-msg').textContent = 'Copied. Paste it into the chat now.';
        }, function () {
          document.execCommand('copy'); // fallback for file:// without clipboard API
        });
      }
    });
    refresh();
  }
  return { init: init };
})();
