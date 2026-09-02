#!/usr/bin/env python3
"""Drive Gemini Deep Research end-to-end via playwright-cli.

One-time headed login seeds a persistent Chromium profile. All subsequent
commands run headless against the same profile, so cookies/localStorage/
device fingerprint survive across runs and SSO isn't re-triggered.

Subcommands (in typical order of use):
    login                       one-time headed login, saves profile
    status                      check if session is still logged in
    start-research              submit a research prompt, leave browser open
    wait-plan                   poll for plan text in chat area
    approve-plan                click "Start research" to launch deep research
    wait-complete               poll for completion signal
    extract                     pull the finished report as markdown
    close                       shut the named session

Exit codes:
    0   success
    10  login required
    20  timeout
    30  extraction failure
    40  DOM mismatch (a named element was not found — Gemini changed)

The driver deliberately does no retries of its own beyond short polling
loops. Higher-level retry/error handling lives in the browser-researcher
agent, which reads exit codes and dispatches SendMessage prefixes.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

# -------------------------------------------------------------------------
# Defaults
# -------------------------------------------------------------------------

DEFAULT_SESSION = "gemini-research"
DEFAULT_PROFILE = Path.home() / ".cache" / "gemini-chrome-profile"
DEFAULT_BROWSER = "chrome"  # real Chrome channel — lowest bot-detection risk
DEFAULT_CDP_PORT = 9224  # 9222 often taken by Brave, 9223 by claude-ai driver

# We launch Google Chrome ourselves (not via Playwright) so it doesn't carry
# `navigator.webdriver=true` or `--enable-automation`, which Google OAuth
# uses to block logins. The driver then attaches via CDP, which is
# transparent to the page.
CHROME_BIN = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# Spoofed UA for headless runs: headless Chrome's default UA contains
# "HeadlessChrome/..." which invalidates cookies seeded during a headed
# login. Matching the headed UA keeps the cookie valid across modes.
HEADED_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/146.0.0.0 Safari/537.36"
)

URL_ROOT = "https://gemini.google.com/app"
URL_NEW = "https://gemini.google.com/app"

NAV_TIMEOUT = 45
ACTION_TIMEOUT = 30
POLL_INTERVAL_S = 60           # research completion poll interval
PROGRESS_EVERY = 5             # emit RESEARCH_PROGRESS every N polls
PLAN_POLL_INTERVAL_S = 3

# Exit codes (kept as module-level so callers can reference them)
EXIT_OK = 0
EXIT_LOGIN_REQUIRED = 10
EXIT_TIMEOUT = 20
EXIT_EXTRACTION_FAIL = 30
EXIT_DOM_MISMATCH = 40


# -------------------------------------------------------------------------
# playwright-cli wrapper
# -------------------------------------------------------------------------


class Pw:
    """Lifecycle wrapper that launches Chrome itself (no Playwright control)
    and then attaches via CDP.

    Key trick: a Chrome launched with `--remote-debugging-port=N` by
    subprocess.Popen carries no `navigator.webdriver=true` and no
    `--enable-automation` flag, so Google OAuth treats it as an ordinary
    user browser. playwright-cli's `attach --cdp` is transparent to the
    page — it just talks DevTools protocol."""

    def __init__(
        self,
        session: str,
        profile: Path,
        browser: str = DEFAULT_BROWSER,
        port: int = DEFAULT_CDP_PORT,
    ):
        self.session = session
        self.profile = Path(profile).expanduser()
        self.browser = browser
        self.port = port
        self.chrome_proc: subprocess.Popen | None = None

    def _run(self, *args, timeout=ACTION_TIMEOUT, check=True, capture=True):
        cmd = ["playwright-cli", f"-s={self.session}", *args]
        r = subprocess.run(cmd, capture_output=capture, text=True, timeout=timeout)
        if check and r.returncode != 0:
            raise RuntimeError(
                f"playwright-cli {args[0] if args else ''} failed (exit {r.returncode})\n"
                f"cmd: {' '.join(cmd)}\n"
                f"stderr: {r.stderr.strip()[:800]}\n"
                f"stdout: {r.stdout.strip()[:800]}"
            )
        return r

    # ---- lifecycle ----

    def is_running(self) -> bool:
        """True only if THIS session's stanza in `playwright-cli list` is open."""
        r = subprocess.run(["playwright-cli", "list"], capture_output=True, text=True)
        lines = r.stdout.splitlines()
        marker = f"- {self.session}:"
        in_stanza = False
        stanza_indent = None
        for line in lines:
            if line.startswith(marker):
                in_stanza = True
                stanza_indent = len(line) - len(line.lstrip())
                continue
            if in_stanza:
                stripped = line.lstrip()
                indent = len(line) - len(stripped)
                if not stripped:
                    in_stanza = False
                    continue
                if stripped.startswith("- ") and indent <= (stanza_indent or 0):
                    in_stanza = False
                    continue
                if "status: open" in stripped:
                    return True
                if "status: closed" in stripped:
                    in_stanza = False
        return False

    def _port_open(self) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            try:
                s.connect(("127.0.0.1", self.port))
                return True
            except OSError:
                return False

    def chrome_alive(self) -> bool:
        """True iff our Chrome subprocess (or an existing one on the port) is up."""
        if self.chrome_proc is not None and self.chrome_proc.poll() is None:
            return self._port_open()
        # No child process, but an existing Chrome may already own the port.
        return self._port_open()

    def list_targets(self) -> list[dict]:
        """Enumerate all Chrome tabs/targets via CDP's /json/list HTTP endpoint.

        Each element is a dict with at least `type`, `url`, `title`, `id`.
        We only care about `type == "page"` entries. Returns [] on any
        network error (Chrome briefly offline, port not yet listening, etc).
        """
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{self.port}/json/list", timeout=2
            ) as r:
                return json.loads(r.read())
        except Exception:
            return []

    def launch_chrome(self, headed: bool = True, landing_url: str = URL_NEW) -> None:
        """Launch a user-facing Chrome via subprocess with a debug port.

        This Chrome has no Playwright fingerprint. We keep a handle on the
        subprocess so the caller can watch it exit (user closing the window
        becomes a signal)."""
        self.profile.mkdir(parents=True, exist_ok=True)
        if self._port_open():
            # Something else already listens — assume it's a previous run we
            # can reuse, skip launching.
            print(f"(debug port {self.port} already in use — reusing)", file=sys.stderr)
            return
        # Remove stale singleton lock files left by a crash.  Chrome refuses
        # to start if these exist but the process is gone.
        for name in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
            p = self.profile / name
            if p.exists():
                p.unlink(missing_ok=True)
                print(f"(removed stale {name})", file=sys.stderr)
        if not Path(CHROME_BIN).exists():
            raise RuntimeError(f"Chrome binary not found at {CHROME_BIN}")
        args = [
            CHROME_BIN,
            f"--remote-debugging-port={self.port}",
            f"--user-data-dir={self.profile}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-features=InfiniteSessionRestore",
            "--restore-last-session=false",
        ]
        if not headed:
            # Chrome's native headless mode ("new" headless) — not Playwright's.
            # Less automation-detectable than Playwright-driven Chromium.
            args.append("--headless=new")
            # Spoof UA — see HEADED_UA comment above.
            args.append(f"--user-agent={HEADED_UA}")
        args.append(landing_url)
        self.chrome_proc = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        # Wait for the CDP port to open
        deadline = time.time() + 30
        while time.time() < deadline:
            if self._port_open():
                return
            time.sleep(0.3)
        raise RuntimeError(f"Chrome did not open debug port {self.port} within 30s")

    def attach(self) -> None:
        """Attach playwright-cli session to our Chrome via CDP."""
        if self.is_running():
            return
        self._run(
            "attach",
            "--cdp",
            f"http://localhost:{self.port}",
            timeout=30,
        )

    def open(self, headed: bool = True) -> None:
        """Compatibility wrapper: launch Chrome + attach."""
        self.launch_chrome(headed=headed)
        self.attach()

    def detach(self) -> None:
        """Detach playwright-cli session without killing Chrome."""
        if self.is_running():
            self._run("close", check=False, timeout=15)

    def kill_chrome(self) -> None:
        """Kill the Chrome subprocess we launched."""
        if self.chrome_proc is not None and self.chrome_proc.poll() is None:
            try:
                self.chrome_proc.terminate()
                try:
                    self.chrome_proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.chrome_proc.kill()
            except Exception as e:
                print(f"(kill_chrome: {e})", file=sys.stderr)
        self.chrome_proc = None

    def close(self) -> None:
        """Full shutdown: detach playwright, kill Chrome."""
        self.detach()
        self.kill_chrome()

    # ---- navigation ----

    def goto(self, url: str, timeout: int = NAV_TIMEOUT) -> None:
        self._run("goto", url, timeout=timeout)

    def current_url(self) -> str | None:
        return self.eval_json("return window.location.href")

    def resize(self, w: int, h: int) -> None:
        self._run("resize", str(w), str(h), check=False, timeout=15)

    # ---- eval ----

    def eval_json(self, js: str, timeout: int = ACTION_TIMEOUT):
        """Run JS in the current tab; JSON-decode the result.

        `playwright-cli --raw eval` prints the return value as JSON, so we
        can return any JS object/string/array from the IIFE and decode it
        with json.loads on the Python side.
        """
        wrapped = f"(() => {{ {js} }})()"
        r = self._run("--raw", "eval", wrapped, timeout=timeout)
        out = r.stdout.strip()
        if not out:
            return None
        return json.loads(out)

    def eval_raw(self, js: str, timeout: int = ACTION_TIMEOUT) -> str:
        """Run JS and return raw stdout (no JSON parse)."""
        r = self._run("--raw", "eval", js, timeout=timeout)
        return r.stdout.strip()

    # ---- locators / clicks ----

    def click(self, locator: str, timeout: int = ACTION_TIMEOUT) -> None:
        """Click via a Playwright locator string."""
        self._run("click", locator, timeout=timeout)

    def fill(self, locator: str, value: str, timeout: int = ACTION_TIMEOUT) -> None:
        self._run("fill", locator, value, timeout=timeout)


# -------------------------------------------------------------------------
# Page-context helpers (pure JS that runs via eval_json)
# -------------------------------------------------------------------------


JS_HELPERS = r"""
const norm = s => (s || '').replace(/\s+/g, ' ').trim();
const accName = el => {
  if (!el) return '';
  const aria = el.getAttribute('aria-label');
  if (aria) return norm(aria);
  const labelledby = el.getAttribute('aria-labelledby');
  if (labelledby) {
    const parts = labelledby.split(/\s+/).map(id => {
      const n = document.getElementById(id);
      return n ? n.innerText || n.textContent || '' : '';
    });
    return norm(parts.join(' '));
  }
  return norm(el.innerText || el.textContent || '');
};
const findByRole = (role, name, { last = false } = {}) => {
  const roleSelectors = {
    button: 'button, [role="button"]',
    link: 'a, [role="link"]',
    textbox: 'textarea, input[type="text"], input[type="search"], [role="textbox"], [contenteditable="true"]',
    menuitemcheckbox: '[role="menuitemcheckbox"]',
    dialog: '[role="dialog"]',
    menuitem: '[role="menuitem"], [role="option"]',
  };
  const sel = roleSelectors[role] || `[role="${role}"]`;
  const wanted = norm(name).toLowerCase();
  const matches = Array.from(document.querySelectorAll(sel)).filter(el => {
    if (!wanted) return true;
    const n = accName(el).toLowerCase();
    return n === wanted || n.includes(wanted);
  });
  if (!matches.length) return null;
  return last ? matches[matches.length - 1] : matches[0];
};
"""


# The big JS blobs below all assume JS_HELPERS is prepended.


JS_LOGIN_STATUS = r"""
const url = window.location.href;
const title = document.title || '';
const bodyText = (document.body && document.body.innerText || '').slice(0, 1000);
// Check for Google sign-in page
if (/accounts\.google\.com/.test(url)) return { state: 'logged_out', url };
// Check for explicit sign-in button/link
const signInBtn = Array.from(document.querySelectorAll('a, button')).find(el =>
  /^sign\s*in$/i.test((el.innerText || '').trim())
);
if (signInBtn) return { state: 'logged_out', url };
// Check for logged-in state: "Hi " greeting in page text
if (/gemini\.google\.com/.test(url) && /Hi\s+\w+/i.test(bodyText)) {
  return { state: 'logged_in', url };
}
// Check for prompt input as secondary logged-in signal
const hasInput = !!document.querySelector('[contenteditable="true"], textarea');
if (/gemini\.google\.com/.test(url) && hasInput) {
  return { state: 'logged_in', url };
}
return { state: 'unknown', url, title, sample: bodyText.slice(0, 200) };
"""


# ---- Research Mode Activation (multi-step) ----

JS_CLICK_TOOLS = r"""
// Step 1: Click the Tools/settings button near the prompt area.
// Try multiple candidate names — Google renames these frequently.
const candidates = [
  'Tools',
  'Settings',
  'More options',
];
let toggle = null;
// First try accessible-name match on buttons
for (const name of candidates) {
  toggle = findByRole('button', name);
  if (toggle) break;
}
// Fallback: look for a button with a tune/settings icon near the prompt area
if (!toggle) {
  const btns = Array.from(document.querySelectorAll('button, [role="button"]'));
  toggle = btns.find(b => {
    const label = accName(b).toLowerCase();
    return /tool|setting|tune|slider|option/i.test(label);
  });
}
if (!toggle) return { ok: false, reason: 'no_tools_button', candidates: candidates };
toggle.click();
return { ok: true, clicked: accName(toggle) };
"""


JS_CLICK_DEEP_RESEARCH = r"""
// Step 2: After Tools dropdown is open, click "Deep research" menu item.
const items = Array.from(document.querySelectorAll(
  'button, [role="button"], [role="menuitem"], [role="option"], [role="menuitemcheckbox"], li, div[tabindex]'
));
const dr = items.find(el => {
  const text = (el.innerText || el.textContent || '').trim().toLowerCase();
  return /deep\s*research/i.test(text);
});
if (!dr) return { ok: false, reason: 'no_deep_research_item' };
dr.click();
return { ok: true, clicked: (dr.innerText || '').trim() };
"""


JS_EXPAND_MORE_TOOLS = r"""
// Step 2b: Gemini (verified Sept 2026) nests "Deep research" behind a
// "More tools" expander inside the "Upload & tools" menu. Click it so the
// Deep research item is rendered, then step 2 can be retried.
const items = Array.from(document.querySelectorAll(
  'button, [role="button"], [role="menuitem"], [role="option"], li, div[tabindex]'
)).filter(e => e.offsetParent);
const more = items.find(el =>
  /more tools/i.test(accName(el)) ||
  /^more tools$/i.test((el.innerText || '').replace(/\s+/g, ' ').trim())
);
if (!more) return { ok: false, reason: 'no_more_tools' };
more.click();
return { ok: true, clicked: accName(more) || (more.innerText || '').trim() };
"""


JS_CLICK_MODEL_PICKER = r"""
// Step 3: Click the model picker button (shows current model name).
// Look for "Open mode picker" or a button showing the model name.
let picker = findByRole('button', 'Open mode picker');
if (!picker) {
  // Fallback: button whose text contains "Pro" or "Flash" or "model"
  const btns = Array.from(document.querySelectorAll('button, [role="button"]'));
  picker = btns.find(b => {
    const t = accName(b).toLowerCase();
    return /mode picker|model|pro|flash/i.test(t) && t.length < 60;
  });
}
if (!picker) return { ok: false, reason: 'no_model_picker' };
picker.click();
return { ok: true, clicked: accName(picker) };
"""


JS_SELECT_PRO_MODEL = r"""
// Step 4: Select the "Pro" model from the picker dropdown.
// Look for an option/button containing "Pro" (but not "Flash").
const items = Array.from(document.querySelectorAll(
  'button, [role="button"], [role="menuitem"], [role="option"], [role="radio"], li, div[tabindex]'
));
// Check if Pro is already selected (blue checkmark / aria-selected)
const proItem = items.find(el => {
  const text = (el.innerText || el.textContent || '').trim().toLowerCase();
  return /\bpro\b/i.test(text) && !/flash/i.test(text);
});
if (!proItem) return { ok: false, reason: 'no_pro_option' };
const isSelected = proItem.getAttribute('aria-selected') === 'true'
  || proItem.getAttribute('aria-checked') === 'true'
  || proItem.classList.contains('selected');
if (isSelected) {
  // Already selected — dismiss the picker by pressing Escape
  document.activeElement && document.activeElement.dispatchEvent(
    new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', keyCode: 27, bubbles: true })
  );
  return { ok: true, already_selected: true };
}
proItem.click();
return { ok: true, selected: (proItem.innerText || '').trim() };
"""


JS_FILL_PROMPT = r"""
// Find the prompt textbox. Gemini wraps a contenteditable div inside
// <rich-textarea>, protected by a Trusted Types CSP — so `innerHTML = ''`
// throws. Clear via selection+delete or textContent instead.
let textbox = findByRole('textbox', 'Enter a prompt for Gemini');
if (!textbox) textbox = findByRole('textbox', 'prompt');
if (!textbox) textbox = document.querySelector('rich-textarea [contenteditable="true"]');
if (!textbox) textbox = document.querySelector('[contenteditable="true"]');
if (!textbox) textbox = document.querySelector('textarea');
if (!textbox) return { ok: false, reason: 'no_textbox' };
textbox.focus();
if (textbox.getAttribute('contenteditable') === 'true') {
  // Clear existing content: select-all then delete via execCommand, which
  // respects the editor's model and is allowed under the Trusted Types CSP.
  try {
    const sel = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(textbox);
    sel.removeAllRanges();
    sel.addRange(range);
    document.execCommand('delete', false);
  } catch (e) { /* best-effort clear */ }
  document.execCommand('insertText', false, __PROMPT__);
} else {
  textbox.value = __PROMPT__;
  textbox.dispatchEvent(new Event('input', { bubbles: true }));
}
return { ok: true, len: __PROMPT__.length };
"""


JS_SUBMIT_ENTER = r"""
// Submit the prompt by dispatching Enter keypress on the active element.
const el = document.activeElement;
if (!el) return { ok: false, reason: 'no_active_element' };
el.dispatchEvent(new KeyboardEvent('keydown', {
  key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true
}));
el.dispatchEvent(new KeyboardEvent('keypress', {
  key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true
}));
el.dispatchEvent(new KeyboardEvent('keyup', {
  key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true
}));
return { ok: true };
"""


JS_PLAN_STATUS = r"""
// Most reliable signal that Gemini has produced a plan and is waiting for
// the user: the "Start research" button appears in the plan card. We also
// pull nearby text for the PLAN_READY message, but presence of the button
// is the primary trigger.
const startBtn = findByRole('button', 'Start research');
const editBtn = findByRole('button', 'Edit the research plan');
if (startBtn || editBtn) {
  // Walk up from the button to find the plan container, then grab its text.
  let container = startBtn || editBtn;
  for (let i = 0; i < 8 && container && container.parentElement; i++) {
    container = container.parentElement;
    if ((container.innerText || '').length > 400) break;
  }
  const text = (container && container.innerText || document.body.innerText || '').slice(0, 4000);
  return { state: 'found', text };
}
return { state: 'no_plan', textLen: (document.body.innerText || '').length };
"""


JS_APPROVE_PLAN = r"""
// Find and click the "Start research" button to launch deep research.
let btn = findByRole('button', 'Start research');
if (!btn) {
  // Broader search: any button whose text contains "start research"
  const btns = Array.from(document.querySelectorAll('button, [role="button"]'));
  btn = btns.find(b => /start\s*research/i.test(accName(b)));
}
if (!btn) return { ok: false, reason: 'no_start_button' };
btn.click();
return { ok: true };
"""


JS_CHECK_COMPLETION = r"""
// Completion signal: page body contains "I've completed your research"
const text = document.body.innerText || '';
const complete = /I[''\u2019]ve completed your research/i.test(text);
return { complete: complete };
"""


JS_REVISE_PLAN = r"""
// Open Gemini's plan editor, type the user's revision, and submit. Gemini's
// plan card has two primary buttons: "Edit the research plan" (opens the
// editor) and "Start research" (approves as-is). After clicking Edit, the
// card flips to an editable contenteditable + a confirmation button whose
// label varies ("Update plan", "Save plan", or similar).
const editBtn = findByRole('button', 'Edit the research plan')
  || Array.from(document.querySelectorAll('button, [role="button"]'))
      .find(b => /edit\s+(the\s+)?research\s+plan|edit\s+plan/i.test(accName(b)));
if (!editBtn) return { ok: false, reason: 'no_edit_button' };
editBtn.click();
return { ok: true, step: 'edit_clicked' };
"""


JS_FILL_REVISION = r"""
// Find the revision editor (a textbox that appeared after Edit was clicked)
// and fill it with the supplied text. Reuses the same Trusted Types
// workaround as the main prompt (select + delete + insertText) because the
// same CSP applies across the app.
let textbox = findByRole('textbox', 'revise')
  || findByRole('textbox', 'edit')
  || findByRole('textbox', 'plan');
if (!textbox) {
  // Fallback: the last contenteditable that became visible. Skip the main
  // composer if we're still seeing it (it's pinned to the bottom).
  const editables = Array.from(document.querySelectorAll(
    '[contenteditable="true"], textarea'
  )).filter(el => el.offsetParent);
  // Prefer the one nearest the plan card: largest that is NOT the composer.
  textbox = editables.reverse().find(el => {
    const placeholder = (el.getAttribute('aria-label') || el.getAttribute('placeholder') || '');
    return !/Enter a prompt for Gemini/i.test(placeholder);
  }) || editables[0];
}
if (!textbox) return { ok: false, reason: 'no_revision_textbox' };
textbox.focus();
if (textbox.getAttribute('contenteditable') === 'true') {
  try {
    const sel = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(textbox);
    sel.removeAllRanges();
    sel.addRange(range);
    document.execCommand('delete', false);
  } catch (e) { /* best-effort clear */ }
  document.execCommand('insertText', false, __REVISION__);
} else {
  textbox.value = __REVISION__;
  textbox.dispatchEvent(new Event('input', { bubbles: true }));
}
return { ok: true, len: __REVISION__.length };
"""


# -------------------------------------------------------------------------
# Extraction JS (adapted from extract-report.js)
# -------------------------------------------------------------------------

# Lives in extract-report-pw.js next to this file. We read it at runtime so
# updates don't require touching this driver.
EXTRACT_SCRIPT_PATH = Path(__file__).parent / "extract-report-pw.js"


# -------------------------------------------------------------------------
# Subcommands
# -------------------------------------------------------------------------


# Regex for Gemini tab URLs that imply a logged-in session.
_LOGGED_IN_PATH_RE = re.compile(
    r"^https://gemini\.google\.com/app"
)


def _scan_targets_for_login(targets: list[dict]) -> dict | None:
    """Scan Chrome targets for any gemini.google.com page that looks logged in.

    Returns the matching target dict or None.
    """
    for t in targets:
        if t.get("type") != "page":
            continue
        url = t.get("url") or ""
        if "gemini.google.com" not in url:
            continue
        if "accounts.google.com" in url:
            continue
        if _LOGGED_IN_PATH_RE.match(url):
            return t
    return None


def cmd_login(pw: Pw, args) -> int:
    """Launch a real Chrome (no Playwright control), attach via CDP, and
    poll login state across ALL tabs. Termination signals:
      - any gemini.google.com/app tab → success
      - attached tab JS reports state=logged_in → success
      - Chrome process exits (user closed the window) → exit with last state
    """
    pw.detach()  # drop any stale playwright session
    # Kill any existing Chrome on our debug port (e.g. a headless instance
    # left over from a prior `status` call). Otherwise launch_chrome would
    # just reuse it and the user would never see a visible window.
    subprocess.run(
        ["pkill", "-f", f"remote-debugging-port={pw.port}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(1.5)
    print("Launching Chrome for Gemini login...", flush=True)
    print(f"(profile: {pw.profile})", flush=True)
    pw.launch_chrome(headed=True, landing_url=URL_ROOT)
    # Give Chrome a moment to fully paint before attaching.
    time.sleep(2)
    pw.attach()
    print("Attached via CDP. Complete login in the window; auto-detecting...", flush=True)
    print("(Google SSO — sign into your Google account)", flush=True)
    timeout = getattr(args, "timeout", 600) or 600
    deadline = time.time() + timeout
    last_state = None
    last_url_signature = None
    reached_logged_in = False
    while time.time() < deadline:
        # Chrome closed by user?
        if not pw.chrome_alive():
            print("(Chrome closed by user)", flush=True)
            break

        # 1) Tab-enumeration check: scan every open tab
        targets = pw.list_targets()
        gemini_pages = [
            (t.get("url") or "") for t in targets
            if t.get("type") == "page" and "gemini.google.com" in (t.get("url") or "")
        ]
        sig = tuple(sorted(gemini_pages))
        if sig != last_url_signature:
            if gemini_pages:
                print(f"tabs: {list(gemini_pages)}", flush=True)
            last_url_signature = sig

        hit = _scan_targets_for_login(targets)
        if hit:
            # Verify it's actually logged in by checking the URL is /app (not login)
            hit_url = hit.get("url") or ""
            if "/app" in hit_url and "accounts.google.com" not in hit_url:
                print(f"logged_in (via tab: {hit_url})", flush=True)
                reached_logged_in = True
                break

        # 2) Fallback: also check the attached tab via JS
        try:
            result = _run_js(pw, JS_LOGIN_STATUS)
        except Exception as e:
            print(f"(eval error: {e})", file=sys.stderr, flush=True)
            result = None
        state = (result or {}).get("state")
        if state != last_state:
            print(f"attached tab state={state} url={(result or {}).get('url')}", flush=True)
            last_state = state
        if state == "logged_in":
            reached_logged_in = True
            break

        time.sleep(3)
    else:
        print("ERROR: login timeout reached", file=sys.stderr)
        pw.close()
        return EXIT_LOGIN_REQUIRED
    # Clean detach + kill Chrome so profile gets written cleanly.
    pw.close()
    if not reached_logged_in:
        print("ERROR: Chrome closed before login completed", file=sys.stderr)
        return EXIT_LOGIN_REQUIRED
    print(f"Login persisted to {pw.profile}")
    return EXIT_OK


def _run_js(pw: Pw, js: str, timeout: int = ACTION_TIMEOUT):
    return pw.eval_json(JS_HELPERS + "\n" + js, timeout=timeout)


def cmd_status(pw: Pw, args) -> int:
    pw.open(headed=False)
    try:
        pw.goto(URL_ROOT)
        time.sleep(4)
        result = _run_js(pw, JS_LOGIN_STATUS)
    finally:
        if args.close:
            pw.close()
    if not result:
        print("unknown", file=sys.stderr)
        return EXIT_LOGIN_REQUIRED
    state = result.get("state", "unknown")
    print(state)
    if state != "logged_in":
        hint = {k: v for k, v in result.items() if k != "state"}
        if hint:
            print(f"hint: {json.dumps(hint)}", file=sys.stderr)
    return EXIT_OK if state == "logged_in" else EXIT_LOGIN_REQUIRED


class DomMismatch(Exception):
    pass


def _activate_research_mode(pw: Pw) -> None:
    """Activate Deep Research mode via Tools -> Deep Research -> Pro model."""
    # Step 1: click Tools button
    r = _run_js(pw, JS_CLICK_TOOLS)
    if not r or not r.get("ok"):
        raise DomMismatch(f"Tools button not found: {r}")
    time.sleep(0.5)

    # Step 2: click Deep Research in the dropdown
    r = _run_js(pw, JS_CLICK_DEEP_RESEARCH)
    if not r or not r.get("ok"):
        # Newer Gemini builds hide Deep research behind a "More tools" expander.
        exp = _run_js(pw, JS_EXPAND_MORE_TOOLS)
        if exp and exp.get("ok"):
            time.sleep(1.0)
            r = _run_js(pw, JS_CLICK_DEEP_RESEARCH)
        else:
            print(f"(More tools expander not found: {exp})", file=sys.stderr)
    if not r or not r.get("ok"):
        raise DomMismatch(f"Deep Research menu item not found: {r}")
    time.sleep(0.5)

    # Step 3: click model picker
    r = _run_js(pw, JS_CLICK_MODEL_PICKER)
    if not r or not r.get("ok"):
        # Model picker may not appear if Deep Research auto-selects a model.
        # Log but don't fail — the model may already be correct.
        print(f"(model picker not found, continuing: {r})", file=sys.stderr)
        return
    time.sleep(0.3)

    # Step 4: select Pro model
    r = _run_js(pw, JS_SELECT_PRO_MODEL)
    if not r or not r.get("ok"):
        print(f"(Pro model selection failed, continuing: {r})", file=sys.stderr)
    elif r.get("already_selected"):
        print("(Pro model already selected)", file=sys.stderr)
    time.sleep(0.3)


def cmd_start_research(pw: Pw, args) -> int:
    prompt_text = Path(args.prompt_file).read_text().strip()
    # Collapse whitespace
    prompt_text = " ".join(prompt_text.split())
    if not prompt_text:
        print("ERROR: prompt file is empty", file=sys.stderr)
        return EXIT_EXTRACTION_FAIL

    pw.open(headed=False)
    pw.resize(1440, 900)
    # Hard reset: Gemini's SPA restores the last conversation on /app, and
    # an in-page click on the "New chat" link is a no-op when the router
    # already thinks we're at /app. Go through about:blank first so the
    # subsequent navigation starts from an empty page.
    pw.goto("about:blank")
    time.sleep(1)
    pw.goto(URL_NEW)
    time.sleep(3)

    # Login check
    status = _run_js(pw, JS_LOGIN_STATUS)
    if not status or status.get("state") != "logged_in":
        print(f"not_logged_in url={status}", file=sys.stderr)
        return EXIT_LOGIN_REQUIRED

    # Belt-and-braces: if /app landed us in an old conversation, force a
    # fresh chat. Gemini's SPA redirects /app to the last conversation, and
    # a normal `<a href="/app">` click is intercepted by the router, so we
    # reset conversation state directly via the History API + a full
    # document reload. After reload we usually still end up at /app/{id}
    # with the old history, so we also explicitly click "New chat".
    current = pw.current_url() or ""
    for attempt in range(3):
        if not re.search(r"/app/[0-9a-f]+", current):
            break
        # Preferred: click the sidebar "New chat" link — it's an <a href="/app">
        # handled by the SPA router, which reliably resets conversation state.
        _run_js(pw, r"""
            const candidates = Array.from(document.querySelectorAll(
              'a[aria-label="New chat"], button[aria-label="New chat"], [aria-label="New chat"]'
            )).filter(e => e.offsetParent);
            let b = candidates[0];
            if (!b) {
              const all = Array.from(document.querySelectorAll('a,button,[role="button"]'));
              b = all.find(el => /new chat/i.test((el.innerText || '').trim()) && el.offsetParent);
            }
            if (b) b.click();
            return { clicked: !!b };
        """)
        time.sleep(3)
        current = pw.current_url() or ""
    if re.search(r"/app/[0-9a-f]+", current):
        print(f"(warning: still in existing conversation {current}, continuing anyway)",
              file=sys.stderr)

    # Activate research mode (Tools -> Deep Research -> Pro)
    try:
        _activate_research_mode(pw)
    except DomMismatch as e:
        print(f"DOM_MISMATCH: {e}", file=sys.stderr)
        return EXIT_DOM_MISMATCH

    # Fill prompt (inject via JSON-encoded literal)
    prompt_js = JS_FILL_PROMPT.replace("__PROMPT__", json.dumps(prompt_text))
    r = _run_js(pw, prompt_js)
    if not r or not r.get("ok"):
        print(f"DOM_MISMATCH: prompt textbox not found ({r})", file=sys.stderr)
        return EXIT_DOM_MISMATCH
    time.sleep(0.5)

    # Submit via Enter key dispatch
    r = _run_js(pw, JS_SUBMIT_ENTER)
    if not r or not r.get("ok"):
        print(f"DOM_MISMATCH: enter key dispatch failed ({r})", file=sys.stderr)
        return EXIT_DOM_MISMATCH

    print("research_started")
    return EXIT_OK


def cmd_wait_plan(pw: Pw, args) -> int:
    pw.attach()  # idempotent — reattach if the sidecar lost us
    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        status = _run_js(pw, JS_PLAN_STATUS)
        if status and status.get("state") == "found":
            text = status.get("text", "").strip()
            if text:
                print(text)
                return EXIT_OK
        time.sleep(PLAN_POLL_INTERVAL_S)
    print("ERROR: plan did not appear within timeout", file=sys.stderr)
    return EXIT_TIMEOUT


def cmd_approve_plan(pw: Pw, args) -> int:
    pw.attach()
    r = _run_js(pw, JS_APPROVE_PLAN)
    if not r or not r.get("ok"):
        print(f"DOM_MISMATCH: {r}", file=sys.stderr)
        return EXIT_DOM_MISMATCH
    print("plan_approved")
    return EXIT_OK


def cmd_revise_plan(pw: Pw, args) -> int:
    """Click "Edit the research plan", type the revision, press Enter to submit.

    Reads the revision text from --text=<str> or --text-file=<path>. Gemini's
    "Edit plan" affordance just focuses the main prompt composer — there is
    no separate save/confirm button. Submitting the composer (Enter) is what
    re-generates the plan. After this returns, follow up with `wait-plan`
    to capture the revised plan, then approve-plan or revise-plan again.
    """
    pw.attach()
    if args.text:
        revision = args.text
    elif args.text_file:
        revision = Path(args.text_file).read_text()
    else:
        print("ERROR: --text or --text-file required", file=sys.stderr)
        return EXIT_EXTRACTION_FAIL
    revision = " ".join(revision.split())  # collapse whitespace
    if not revision:
        print("ERROR: revision text is empty", file=sys.stderr)
        return EXIT_EXTRACTION_FAIL

    # Step 1: open the plan editor
    r = _run_js(pw, JS_REVISE_PLAN)
    if not r or not r.get("ok"):
        print(f"DOM_MISMATCH: edit button not found ({r})", file=sys.stderr)
        return EXIT_DOM_MISMATCH
    time.sleep(1.5)  # editor animation / focus

    # Step 2: fill the revision textbox
    fill_js = JS_FILL_REVISION.replace("__REVISION__", json.dumps(revision))
    r = _run_js(pw, fill_js)
    if not r or not r.get("ok"):
        print(f"DOM_MISMATCH: revision textbox not found ({r})", file=sys.stderr)
        return EXIT_DOM_MISMATCH
    time.sleep(0.5)

    # Step 3: submit via Enter (same path as the initial prompt)
    r = _run_js(pw, JS_SUBMIT_ENTER)
    if not r or not r.get("ok"):
        print(f"DOM_MISMATCH: submit failed ({r})", file=sys.stderr)
        return EXIT_DOM_MISMATCH
    print("plan_revised (submitted via Enter)")
    return EXIT_OK


def cmd_wait_complete(pw: Pw, args) -> int:
    pw.attach()  # idempotent — reattach if the sidecar lost us
    start = time.monotonic()
    iteration = 0
    consecutive_errors = 0
    while time.monotonic() - start < args.timeout:
        time.sleep(POLL_INTERVAL_S)
        iteration += 1
        try:
            r = _run_js(pw, JS_CHECK_COMPLETION, timeout=15)
            consecutive_errors = 0
        except Exception as e:
            consecutive_errors += 1
            if consecutive_errors >= 3:
                print(f"ERROR: completion check failed 3x: {e}", file=sys.stderr)
                return EXIT_EXTRACTION_FAIL
            continue

        if r and r.get("complete"):
            elapsed = int((time.monotonic() - start) / 60)
            print(f"RESEARCH_COMPLETE: {elapsed}m elapsed", flush=True)
            return EXIT_OK

        if iteration % PROGRESS_EVERY == 0:
            elapsed = int((time.monotonic() - start) / 60)
            print(f"RESEARCH_PROGRESS: {elapsed}m elapsed", flush=True)

    print(f"ERROR: hard timeout after {args.timeout}s", file=sys.stderr)
    return EXIT_TIMEOUT


def cmd_extract(pw: Pw, args) -> int:
    pw.attach()  # idempotent — reattach if the sidecar lost us
    if not EXTRACT_SCRIPT_PATH.exists():
        print(f"ERROR: extractor script missing at {EXTRACT_SCRIPT_PATH}", file=sys.stderr)
        return EXIT_EXTRACTION_FAIL
    script_body = EXTRACT_SCRIPT_PATH.read_text()

    # Gemini shows reports in a right-side panel that's already visible —
    # no artifact panel to open. Just extract directly.
    try:
        result = _run_js(pw, script_body, timeout=60)
    except Exception as e:
        print(f"ERROR: extractor eval failed: {e}", file=sys.stderr)
        return EXIT_EXTRACTION_FAIL

    if not result or not isinstance(result, dict):
        print(f"ERROR: extractor returned non-object: {result!r}", file=sys.stderr)
        return EXIT_EXTRACTION_FAIL
    if not result.get("ok"):
        print(f"ERROR: extractor: {result.get('reason', 'unknown')}", file=sys.stderr)
        return EXIT_EXTRACTION_FAIL

    markdown = result.get("markdown", "")
    if len(markdown) < 500:
        print(
            f"ERROR: extracted markdown too small ({len(markdown)} chars)",
            file=sys.stderr,
        )
        return EXIT_EXTRACTION_FAIL

    out = Path(args.output).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(markdown)
    size = out.stat().st_size
    lines = markdown.count("\n") + 1
    print(f"{size} bytes, {lines} lines")
    return EXIT_OK


def cmd_close(pw: Pw, args) -> int:
    pw.close()
    print("closed")
    return EXIT_OK


# -------------------------------------------------------------------------
# CLI
# -------------------------------------------------------------------------


def main() -> int:
    p = argparse.ArgumentParser(description="playwright-cli driver for Gemini Deep Research")
    p.add_argument("--session", default=DEFAULT_SESSION)
    p.add_argument("--profile", default=str(DEFAULT_PROFILE))
    p.add_argument("--browser", default=DEFAULT_BROWSER)
    p.add_argument("--port", type=int, default=DEFAULT_CDP_PORT, help="Chrome DevTools remote debugging port")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("login", help="one-time headed login (Google SSO)")
    sp.add_argument("--timeout", type=int, default=600, help="max seconds to wait for SSO completion")

    sp = sub.add_parser("status", help="check login state")
    sp.add_argument("--close", action="store_true", help="close session after check")

    sp = sub.add_parser("start-research", help="submit a prompt, activate Deep Research mode")
    sp.add_argument("--prompt-file", required=True)

    sp = sub.add_parser("wait-plan", help="wait for research plan text in chat")
    sp.add_argument("--timeout", type=int, default=120)

    sub.add_parser("approve-plan", help="click Start Research to launch deep research")

    sp = sub.add_parser(
        "revise-plan",
        help="open Gemini's plan editor, type a revision, click Update plan",
    )
    revise_src = sp.add_mutually_exclusive_group(required=True)
    revise_src.add_argument("--text", help="inline revision text")
    revise_src.add_argument("--text-file", help="path to a file containing the revision")

    sp = sub.add_parser("wait-complete", help="poll for completion")
    sp.add_argument("--timeout", type=int, default=5400)  # 90 min (per SKILL.md hard_timeout)

    sp = sub.add_parser("extract", help="pull finished report as markdown")
    sp.add_argument("--output", required=True)

    sub.add_parser("close", help="close the named browser session")

    args = p.parse_args()
    pw = Pw(session=args.session, profile=Path(args.profile), browser=args.browser, port=args.port)

    handlers = {
        "login": cmd_login,
        "status": cmd_status,
        "start-research": cmd_start_research,
        "wait-plan": cmd_wait_plan,
        "approve-plan": cmd_approve_plan,
        "revise-plan": cmd_revise_plan,
        "wait-complete": cmd_wait_complete,
        "extract": cmd_extract,
        "close": cmd_close,
    }
    return handlers[args.cmd](pw, args)


if __name__ == "__main__":
    sys.exit(main())
