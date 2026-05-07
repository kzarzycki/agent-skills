#!/usr/bin/env python3
"""Drive claude.ai Research end-to-end via playwright-cli.

One-time headed login seeds a persistent Chromium profile. All subsequent
commands run headless against the same profile, so cookies/localStorage/
device fingerprint survive across runs and SSO isn't re-triggered.

Subcommands (in typical order of use):
    login                       one-time headed login, saves profile
    status                      check if session is still logged in
    start-research              submit a research prompt, leave browser open
    wait-plan                   poll for plan card, print plan text
    wait-complete               poll for completion, print RESEARCH_PROGRESS lines
    extract                     pull the finished report as markdown
    close                       shut the named session

Exit codes:
    0   success
    10  login required
    20  timeout
    30  extraction failure
    40  DOM mismatch (a named element was not found — claude.ai changed)

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

DEFAULT_SESSION = "cai-research"  # macOS Unix-socket path cap is ~104 chars
DEFAULT_PROFILE = Path.home() / ".cache" / "claude-ai-chrome-profile"
DEFAULT_BROWSER = "chrome"  # real Chrome channel — lowest bot-detection risk
DEFAULT_CDP_PORT = 9223  # 9222 often taken by Brave / other Chromium forks

# We launch Google Chrome ourselves (not via Playwright) so it doesn't carry
# `navigator.webdriver=true` or `--enable-automation`, which Cloudflare
# Turnstile and Google OAuth use to block logins. The driver then attaches
# via CDP, which is transparent to the page.
CHROME_BIN = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# Spoofed UA for headless runs: headless Chrome's default UA contains
# "HeadlessChrome/..." which invalidates cf_clearance cookies that were
# seeded during a headed login. Matching the headed UA keeps the cookie
# valid across modes. Update the major version (currently 146) when
# bumping Chrome; Cloudflare checks UA + cookie together.
HEADED_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/146.0.0.0 Safari/537.36"
)

URL_NEW = "https://claude.ai/new"
URL_ROOT = "https://claude.ai/"

NAV_TIMEOUT = 45
ACTION_TIMEOUT = 30
POLL_INTERVAL_S = 60           # research completion poll interval
PROGRESS_EVERY = 5             # emit RESEARCH_PROGRESS every N polls
PLAN_POLL_INTERVAL_S = 5
CONNECTORS_DIALOG_WAIT_S = 2

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
    `--enable-automation` flag, so Cloudflare Turnstile and Google OAuth
    treat it as an ordinary user browser. playwright-cli's `attach --cdp`
    is transparent to the page — it just talks DevTools protocol."""

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
            # Spoof UA — see HEADED_UA comment above. Without this, Cloudflare
            # rejects the cf_clearance cookie seeded by the headed login.
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
        return self.eval_json("window.location.href")

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
        """Click via a Playwright locator string (e.g. getByRole('button', { name: 'X' }))."""
        self._run("click", locator, timeout=timeout)

    def fill(self, locator: str, value: str, timeout: int = ACTION_TIMEOUT) -> None:
        self._run("fill", locator, value, timeout=timeout)

    def exists(self, locator: str) -> bool:
        """Return True if a Playwright locator currently matches >=1 element."""
        js = (
            "return document.body ? "
            "Array.from(document.querySelectorAll('*')).length >= 0 : false;"
        )
        # We don't use this dummy JS — instead, use Playwright's own count via eval.
        # But eval runs in page context, so we can't call getByRole. Use a JS
        # equivalent keyed on aria-label / role + accessible name.
        raise NotImplementedError("use js_exists() with explicit query")


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
    textbox: 'textarea, input[type="text"], input[type="search"], [role="textbox"], [contenteditable="true"]',
    menuitemcheckbox: '[role="menuitemcheckbox"]',
    dialog: '[role="dialog"]',
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
const bodyText = (document.body && document.body.innerText || '').slice(0, 500);
// Cloudflare bot-check intercept — common on cold profiles before any login
if (/Just a moment/i.test(title) || /security verification/i.test(bodyText) || /challenges\.cloudflare\.com/.test(url)) {
  return { state: 'cloudflare_challenge', url, title };
}
if (url.includes('/login')) return { state: 'logged_out', url };
const hasInput = !!document.querySelector('[contenteditable="true"], textarea');
const greeted = /Welcome|Good (morning|afternoon|evening)|Afternoon,|Morning,|Evening,/i.test(bodyText);
if (hasInput || greeted) return { state: 'logged_in', url };
return { state: 'unknown', url, title, sample: bodyText.slice(0, 200) };
"""


JS_ACTIVATE_RESEARCH = r"""
const report = { steps: [] };
const step = (name, ok, detail) => report.steps.push({ name, ok, detail: detail || null });

// Click the "+" button that opens the attach/tools menu. Claude has
// renamed this button multiple times: "Toggle menu" (early 2026),
// "Add files, connectors, and more" (current). Try them in order.
const candidates = [
  'Add files, connectors, and more',
  'Toggle menu',
  'Add attachment',
];
let toggle = null;
for (const name of candidates) {
  toggle = findByRole('button', name);
  if (toggle) break;
}
if (!toggle) { step('toggle_menu', false, 'not found; candidates=' + candidates.join('|')); return report; }
toggle.click();
step('toggle_menu', true);
return report;
"""


JS_CLICK_RESEARCH = r"""
const el = findByRole('menuitemcheckbox', 'Research');
if (!el) return { ok: false, reason: 'no_research_item' };
el.click();
return { ok: true };
"""


JS_DISMISS_CONNECTORS = r"""
// The connectors dialog shows after clicking Send on a Research prompt.
// Don't gate on role="dialog" — the dialog may not use that role. Instead,
// key off the presence of the two unambiguous buttons: "Disable all tools"
// and "Confirm". If both exist, it's the connectors dialog.
const disable = findByRole('button', 'Disable all tools');
const confirm = findByRole('button', 'Confirm');
if (!disable && !confirm) return { dismissed: false, reason: 'no_dialog' };
if (disable) disable.click();
if (confirm) confirm.click();
return { dismissed: true, clickedDisable: !!disable, clickedConfirm: !!confirm };
"""


JS_VERIFY_RESEARCH_ACTIVE = r"""
// After activation, the "Research mode" indicator button should be present.
const indicator = findByRole('button', 'Research mode');
return { active: !!indicator };
"""


JS_FILL_PROMPT = r"""
const textbox = document.querySelector('[contenteditable="true"]') || document.querySelector('textarea');
if (!textbox) return { ok: false, reason: 'no_textbox' };
textbox.focus();
// For contenteditable (Claude.ai is a ProseMirror editor), use execCommand
if (textbox.getAttribute('contenteditable') === 'true') {
  // Clear existing content first
  textbox.innerHTML = '';
  document.execCommand('insertText', false, __PROMPT__);
} else {
  textbox.value = __PROMPT__;
  textbox.dispatchEvent(new Event('input', { bubbles: true }));
}
return { ok: true, len: __PROMPT__.length };
"""


JS_CLICK_SEND = r"""
const btn = findByRole('button', 'Send message');
if (!btn) return { ok: false, reason: 'no_send_button' };
if (btn.disabled) return { ok: false, reason: 'send_button_disabled' };
btn.click();
return { ok: true };
"""


JS_PLAN_CARD_STATUS = r"""
// claude.ai now shows a dynamic "Open research panel" button whose aria-label is
// "{title}: {N} sources and counting.... Open research panel". Match the static suffix.
function findPlanBtn() {
  var btns = Array.from(document.querySelectorAll('button,[role="button"]'));
  return btns.find(function(b) {
    var lbl = (b.getAttribute('aria-label') || b.innerText || '').trim();
    return /open research panel/i.test(lbl);
  }) || null;
}
var card = findPlanBtn();
if (!card) return { state: 'no_card' };
var lbl = (card.getAttribute('aria-label') || card.innerText || '').trim();
return { state: 'found', label: lbl };
"""


JS_EXPAND_PLAN = r"""
// Click "Open research panel" button to reveal the side panel
function findPlanBtn() {
  var btns = Array.from(document.querySelectorAll('button,[role="button"]'));
  return btns.find(function(b) {
    var lbl = (b.getAttribute('aria-label') || b.innerText || '').trim();
    return /open research panel/i.test(lbl);
  }) || null;
}
var card = findPlanBtn();
if (!card) return { ok: false };
card.click();
return { ok: true };
"""


JS_EXTRACT_PLAN_TEXT = r"""
// After clicking "Open research panel", the plan appears in the aria-label itself
// (e.g. "My Topic: 309 sources and counting. Open research panel") — extract the
// title + source count from there, and also grab any visible panel text.
function findPlanBtn() {
  var btns = Array.from(document.querySelectorAll('button,[role="button"]'));
  return btns.find(function(b) {
    var lbl = (b.getAttribute('aria-label') || b.innerText || '').trim();
    return /open research panel/i.test(lbl);
  }) || null;
}
var btn = findPlanBtn();
var label = btn ? (btn.getAttribute('aria-label') || btn.innerText || '').trim() : '';
// Also try to grab text from an opened side panel (aria-label="Research panel" or similar)
var panel = document.querySelector('[aria-label*="research" i][role="complementary"], [aria-label*="research" i][role="dialog"], aside');
var panelText = panel ? panel.innerText.trim().substring(0, 2000) : '';
return { ok: true, text: panelText || label };
"""


JS_CHECK_COMPLETION = r"""
// Completion signal: a "Copy" button appears below the assistant response.
// Multiple Copy buttons may exist; the last one is the research response.
const copyBtns = Array.from(document.querySelectorAll('button, [role="button"]'))
  .filter(b => /^copy$/i.test(accName(b)));
// Also check for explicit "Stop response" button disappearing (weaker signal)
const stopping = Array.from(document.querySelectorAll('button'))
  .some(b => /stop\s+response/i.test(accName(b)));
return { copyCount: copyBtns.length, stillRunning: stopping };
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


# Regex for claude.ai tab URLs that imply a logged-in session.
# We list the URLs that the app only serves to authenticated users:
# /new, /chat/<id>, /chats, /projects, /recents, /settings. The root
# `/` is deliberately excluded because unauthed visits transiently sit
# there before redirecting to /login.
_LOGGED_IN_PATH_RE = re.compile(
    r"^https://claude\.ai/(new|chat(/|$)|chats(/|$)|projects(/|$)|recents(/|$)|settings(/|$))"
)


def _scan_targets_for_login(targets: list[dict]) -> dict | None:
    """Scan Chrome targets for any claude.ai page that looks logged in.

    Returns the matching target dict or None. This is how we handle the
    'magic link opens in a new tab' flow: login cookies land in the
    profile, and the new tab shows claude.ai/new (or similar). We don't
    need to attach to that tab — its URL in /json/list is enough.
    """
    for t in targets:
        if t.get("type") != "page":
            continue
        url = t.get("url") or ""
        if "claude.ai" not in url:
            continue
        if "/login" in url:
            continue
        if _LOGGED_IN_PATH_RE.match(url):
            return t
    return None


def cmd_login(pw: Pw, args) -> int:
    """Launch a real Chrome (no Playwright control), attach via CDP, and
    poll login state across ALL tabs. Termination signals:
      - any claude.ai tab lands on a logged-in URL → success
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
    print("Launching Chrome for claude.ai login…", flush=True)
    print(f"(profile: {pw.profile})", flush=True)
    pw.launch_chrome(headed=True, landing_url=URL_ROOT)
    # Give Chrome a moment to fully paint before attaching.
    time.sleep(2)
    pw.attach()
    print("Attached via CDP. Complete login in the window; auto-detecting…", flush=True)
    print("(you can open the magic link in a new tab — all tabs are monitored)", flush=True)
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

        # 1) Tab-enumeration check: scan every open tab, not just the
        #    attached one. Handles the magic-link-in-new-tab flow.
        targets = pw.list_targets()
        # Log URL changes so the user can see what we're seeing.
        claude_pages = [
            (t.get("url") or "") for t in targets
            if t.get("type") == "page" and "claude.ai" in (t.get("url") or "")
        ]
        sig = tuple(sorted(claude_pages))
        if sig != last_url_signature:
            if claude_pages:
                print(f"tabs: {list(claude_pages)}", flush=True)
            last_url_signature = sig

        hit = _scan_targets_for_login(targets)
        if hit:
            print(f"logged_in (via tab: {hit.get('url')})", flush=True)
            reached_logged_in = True
            break

        # 2) Fallback: also check the attached tab via JS. Catches the
        #    rare case where login lands back on the same tab.
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
        # Give claude.ai's SPA plus any Cloudflare JS challenge a chance to settle.
        # Cloudflare's interstitial usually clears itself in 3-8 seconds when the
        # profile already has a valid cf_clearance cookie.
        time.sleep(4)
        result = _run_js(pw, JS_LOGIN_STATUS)
        # If we're sitting on a Cloudflare challenge, poll for up to ~20s to see
        # if it auto-clears. After that, give up — the profile likely needs
        # a fresh headed visit to re-seed cf_clearance.
        attempts = 0
        while result and result.get("state") == "cloudflare_challenge" and attempts < 4:
            time.sleep(5)
            result = _run_js(pw, JS_LOGIN_STATUS)
            attempts += 1
    finally:
        if args.close:
            pw.close()
    if not result:
        print("unknown", file=sys.stderr)
        return EXIT_LOGIN_REQUIRED
    state = result.get("state", "unknown")
    # Print state on stdout; any extra hints on stderr so callers parsing
    # stdout get exactly one token.
    print(state)
    if state != "logged_in":
        hint = {k: v for k, v in result.items() if k != "state"}
        if hint:
            print(f"hint: {json.dumps(hint)}", file=sys.stderr)
    return EXIT_OK if state == "logged_in" else EXIT_LOGIN_REQUIRED


def _activate_research_mode(pw: Pw) -> None:
    """Open the + menu, toggle Research, verify."""
    # Step 1: click toggle menu
    r = _run_js(pw, JS_ACTIVATE_RESEARCH)
    if not r or not r.get("steps") or not r["steps"][0].get("ok"):
        raise DomMismatch(f"Toggle menu button not found: {r}")
    time.sleep(0.3)

    # Step 2: click Research menuitemcheckbox
    r = _run_js(pw, JS_CLICK_RESEARCH)
    if not r or not r.get("ok"):
        raise DomMismatch(f"Research menu item not found: {r}")
    time.sleep(0.5)

    # Step 3: verify Research mode is active
    r = _run_js(pw, JS_VERIFY_RESEARCH_ACTIVE)
    if not r or not r.get("active"):
        raise DomMismatch("Research mode indicator did not appear after activation")


def _dismiss_connectors_dialog(pw: Pw, attempts: int = 5) -> bool:
    """Poll for the connectors dialog up to `attempts` times and dismiss it.

    The dialog appears ~1-3 seconds after clicking Send on a Research
    prompt. It has two unambiguous buttons — "Disable all tools" and
    "Confirm" — that we use to detect and dismiss it.
    """
    for _ in range(attempts):
        r = _run_js(pw, JS_DISMISS_CONNECTORS)
        if r and r.get("dismissed"):
            time.sleep(1)
            return True
        time.sleep(1)
    return False


class DomMismatch(Exception):
    pass


def cmd_start_research(pw: Pw, args) -> int:
    prompt_text = Path(args.prompt_file).read_text().strip()
    # Collapse whitespace — same rule the agent used to apply to Chrome MCP input.
    prompt_text = " ".join(prompt_text.split())
    if not prompt_text:
        print("ERROR: prompt file is empty", file=sys.stderr)
        return EXIT_EXTRACTION_FAIL

    pw.open(headed=False)
    pw.resize(1440, 900)
    pw.goto(URL_NEW)
    time.sleep(3)

    # Login check
    status = _run_js(pw, JS_LOGIN_STATUS)
    if not status or status.get("state") != "logged_in":
        print(f"not_logged_in url={status}", file=sys.stderr)
        return EXIT_LOGIN_REQUIRED

    # Activate research
    try:
        _activate_research_mode(pw)
    except DomMismatch as e:
        print(f"DOM_MISMATCH: {e}", file=sys.stderr)
        return EXIT_DOM_MISMATCH

    # Fill prompt (inject the prompt via JSON-encoded literal)
    prompt_js = JS_FILL_PROMPT.replace("__PROMPT__", json.dumps(prompt_text))
    r = _run_js(pw, prompt_js)
    if not r or not r.get("ok"):
        print(f"DOM_MISMATCH: prompt textbox not found ({r})", file=sys.stderr)
        return EXIT_DOM_MISMATCH
    time.sleep(0.5)

    # Click send
    r = _run_js(pw, JS_CLICK_SEND)
    if not r or not r.get("ok"):
        print(f"DOM_MISMATCH: send button not clickable ({r})", file=sys.stderr)
        return EXIT_DOM_MISMATCH

    # The connectors dialog appears AFTER Send on every research start.
    # Dismiss it so the plan card can surface. Not fatal if absent —
    # some accounts may not see it.
    dismissed = _dismiss_connectors_dialog(pw, attempts=8)
    if dismissed:
        print("connectors_dismissed", file=sys.stderr)

    print("research_started")
    return EXIT_OK


def cmd_wait_plan(pw: Pw, args) -> int:
    pw.attach()  # idempotent — reattach if the sidecar lost us
    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        status = _run_js(pw, JS_PLAN_CARD_STATUS)
        if status and status.get("state") == "found":
            _run_js(pw, JS_EXPAND_PLAN)
            time.sleep(1)
            plan = _run_js(pw, JS_EXTRACT_PLAN_TEXT)
            if plan and plan.get("ok"):
                text = plan.get("text", "").strip()
                if text:
                    print(text)
                    return EXIT_OK
        time.sleep(PLAN_POLL_INTERVAL_S)
    print("ERROR: plan card did not appear within timeout", file=sys.stderr)
    return EXIT_TIMEOUT


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

        if r and r.get("copyCount", 0) > 0 and not r.get("stillRunning"):
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

    # Script body is a plain block of statements ending in a `return`. It
    # gets prepended with JS_HELPERS and wrapped in an IIFE by eval_json.
    # Max subprocess arg size is generous (>128KB) — enough for a full
    # claude.ai research report plus the helper/extractor preamble.
    # Step 1: open the artifact/document panel if one exists, then wait for
    # the DOM to settle before extracting.
    _run_js(
        pw,
        r"""
        var btn = Array.from(document.querySelectorAll('button,[role="button"]'))
          .find(function(b) {
            return /open artifact/i.test(b.getAttribute('aria-label') || b.innerText || '');
          });
        if (btn) { btn.click(); return { clicked: true }; }
        return { clicked: false };
        """,
        timeout=15,
    )
    time.sleep(2)  # give the artifact panel time to render

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
    p = argparse.ArgumentParser(description="playwright-cli driver for claude.ai research")
    p.add_argument("--session", default=DEFAULT_SESSION)
    p.add_argument("--profile", default=str(DEFAULT_PROFILE))
    p.add_argument("--browser", default=DEFAULT_BROWSER)
    p.add_argument("--port", type=int, default=DEFAULT_CDP_PORT, help="Chrome DevTools remote debugging port")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("login", help="one-time headed login")
    sp.add_argument("--timeout", type=int, default=600, help="max seconds to wait for SSO completion")

    sp = sub.add_parser("status", help="check login state")
    sp.add_argument("--close", action="store_true", help="close session after check")

    sp = sub.add_parser("start-research", help="submit a prompt, activate Research mode")
    sp.add_argument("--prompt-file", required=True)

    sp = sub.add_parser("wait-plan", help="wait for research plan card, print text")
    sp.add_argument("--timeout", type=int, default=120)

    sp = sub.add_parser("wait-complete", help="poll for completion")
    sp.add_argument("--timeout", type=int, default=3900)  # 65 min

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
        "wait-complete": cmd_wait_complete,
        "extract": cmd_extract,
        "close": cmd_close,
    }
    return handlers[args.cmd](pw, args)


if __name__ == "__main__":
    sys.exit(main())
