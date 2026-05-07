#!/usr/bin/env python3
"""Drive chatgpt.com Deep Research end-to-end via playwright-cli.

One-time headed login seeds a persistent Chromium profile. All subsequent
commands run headless against the same profile, so cookies/localStorage/
device fingerprint survive across runs and SSO isn't re-triggered.

Subcommands (in typical order of use):
    login                       one-time headed login, saves profile
    status                      check if session is still logged in
    start-research              submit a research prompt, leave browser open
    wait-plan                   poll for plan card, print plan text
    approve-plan                click approval button to start research
    wait-complete               poll for completion, print RESEARCH_PROGRESS lines
    extract                     pull the finished report as markdown
    close                       shut the named session

Exit codes:
    0   success
    10  login required
    20  timeout
    30  extraction failure
    40  DOM mismatch (a named element was not found — chatgpt.com changed)

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

DEFAULT_SESSION = "chatgpt-research"
DEFAULT_PROFILE = Path.home() / ".cache" / "chatgpt-chrome-profile"
DEFAULT_BROWSER = "chrome"  # real Chrome channel — lowest bot-detection risk
DEFAULT_CDP_PORT = 9225  # distinct from claude-ai (9223) and other Chromium forks

# We launch Google Chrome ourselves (not via Playwright) so it doesn't carry
# `navigator.webdriver=true` or `--enable-automation`, which Cloudflare
# Turnstile and Google OAuth use to block logins. The driver then attaches
# via CDP, which is transparent to the page.
CHROME_BIN = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# Spoofed UA for headless runs: headless Chrome's default UA contains
# "HeadlessChrome/..." which invalidates cookies that were seeded during a
# headed login. Matching the headed UA keeps cookies valid across modes.
# Update the major version (currently 146) when bumping Chrome.
HEADED_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/146.0.0.0 Safari/537.36"
)

URL_ROOT = "https://chatgpt.com/deep-research"
URL_NEW = "https://chatgpt.com/deep-research"

NAV_TIMEOUT = 45
ACTION_TIMEOUT = 30
POLL_INTERVAL_S = 60           # research completion poll interval
PROGRESS_EVERY = 5             # emit RESEARCH_PROGRESS every N polls
PLAN_POLL_INTERVAL_S = 5

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
            # Spoof UA — see HEADED_UA comment above. Without this, cookies
            # seeded by the headed login may be rejected.
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

    def eval_json_in_root_frame(self, js: str, timeout: int = ACTION_TIMEOUT):
        """Evaluate JS inside the nested `root` iframe that hosts ChatGPT
        Deep Research UI (conversation plan, progress, report).

        ChatGPT moved the deep-research UI into a sandboxed cross-origin
        iframe (connector_openai_deep_research.web-sandbox.oaiusercontent.com)
        which contains a nested `about:blank` iframe with `name="root"`. The
        parent page cannot reach into it via DOM access (SOP), but Playwright
        can address it through `page.frames()`.

        `js` must be a statement block ending in a `return <value>` — exactly
        the same shape as what `eval_json` accepts. It runs as the body of an
        arrow function inside the frame.
        """
        work_dir = Path(os.getcwd()) / ".work"
        work_dir.mkdir(parents=True, exist_ok=True)
        wrapper = (
            "async (page) => {\n"
            "  const rootFrame = page.frames().find(f => f.name() === 'root');\n"
            "  if (!rootFrame) {\n"
            "    return { __pwdriver_err: 'no_root_frame', "
            "frames: page.frames().map(f => ({ url: f.url(), name: f.name() })) };\n"
            "  }\n"
            "  try {\n"
            "    return await rootFrame.evaluate(() => {\n"
            f"{js}\n"
            "    });\n"
            "  } catch (e) {\n"
            "    return { __pwdriver_err: 'eval_failed', msg: String(e) };\n"
            "  }\n"
            "}\n"
        )
        fn_path = work_dir / ".pwdriver-frame-eval.js"
        fn_path.write_text(wrapper)
        r = self._run("--raw", "run-code", "--filename", str(fn_path), timeout=timeout)
        out = r.stdout.strip()
        if not out:
            return None
        return json.loads(out)

    # ---- locators / clicks ----

    def click(self, locator: str, timeout: int = ACTION_TIMEOUT) -> None:
        """Click via a Playwright locator string (e.g. getByRole('button', { name: 'X' }))."""
        self._run("click", locator, timeout=timeout)

    def fill(self, locator: str, value: str, timeout: int = ACTION_TIMEOUT) -> None:
        self._run("fill", locator, value, timeout=timeout)

    def exists(self, locator: str) -> bool:
        """Return True if a Playwright locator currently matches >=1 element."""
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
const bodyText = (document.body && document.body.innerText || '').slice(0, 2000);
// Cloudflare bot-check intercept
if (/Just a moment/i.test(title) || /security verification/i.test(bodyText) || /challenges\.cloudflare\.com/.test(url)) {
  return { state: 'cloudflare_challenge', url, title };
}
// Logged out indicators. The anonymous homepage at chatgpt.com/ shows a
// "Log in" button, "Sign up for free", and "Log in to get answers based on
// saved chats" alongside a textbox — so the presence of a textbox alone is
// NOT a reliable logged-in signal. Check these explicitly first.
const logInBtn = !!findByRole('button', 'Log in');
const signUpBtn = !!findByRole('button', 'Sign up for free');
if (/Log in to get answers/i.test(bodyText) || /Welcome back/i.test(bodyText) ||
    url.includes('/auth/login') || url.includes('login.chatgpt.com') ||
    (logInBtn && signUpBtn)) {
  return { state: 'logged_out', url };
}
// Logged-in: profile menu visible, or an authenticated-only path, or the
// deep-research input placeholder. "Open profile menu" appears on the top-
// left when signed in; the anonymous home instead shows "Log in".
const profileMenu = !!findByRole('button', 'Open profile menu');
const hasInputPlaceholder = /Get a detailed report/i.test(bodyText);
const onAuthedPath = /chatgpt\.com\/(c\/|g\/|gpts\/|settings\/|deep-research(\/|$))/.test(url);
if (profileMenu || hasInputPlaceholder || onAuthedPath) {
  return { state: 'logged_in', url };
}
return { state: 'unknown', url, title, sample: bodyText.slice(0, 200) };
"""


JS_ACTIVATE_RESEARCH = r"""
// ChatGPT Deep Research is already active when navigating to /deep-research
// (the URL itself is the mode). The old "Deep research" chip in the input
// bar has been removed — the /deep-research landing page just has a single
// input that always runs as deep research. So the only thing we need to
// verify is that we landed on that path and there is a prompt textbox.
const url = location.href;
const onPath = /chatgpt\.com\/deep-research(\/|$|\?)/.test(url);
const textbox = document.querySelector('[contenteditable="true"], textarea');
if (onPath && textbox) return { ok: true, detail: 'deep_research_page_ready' };
// Fallback by legacy body text markers in case the UI flips back
const bodyText = (document.body && document.body.innerText || '').slice(0, 2000);
if (/Get a full report/i.test(bodyText) || /Get a detailed report/i.test(bodyText)) {
  if (textbox) return { ok: true, detail: 'deep_research_text_match' };
}
return { ok: false, reason: 'deep_research_mode_not_detected', url, hasTextbox: !!textbox };
"""


JS_FILL_PROMPT = r"""
const textbox = document.querySelector('[contenteditable="true"]') || document.querySelector('textarea');
if (!textbox) return { ok: false, reason: 'no_textbox' };
textbox.focus();
// For contenteditable (ChatGPT uses a ProseMirror-like editor), use execCommand
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
// ChatGPT uses obfuscated CSS classes — find send button by accessible name
// Try multiple candidate names
const candidates = ['Send message', 'Send', 'Send prompt'];
let btn = null;
for (const name of candidates) {
  btn = findByRole('button', name);
  if (btn) break;
}
// Fallback: look for any button near the input area with a send-like icon
// (SVG path with arrow shape). ChatGPT's send button is typically a small
// circular button with an arrow icon.
if (!btn) {
  const allBtns = Array.from(document.querySelectorAll('button, [role="button"]'));
  btn = allBtns.find(b => {
    const svg = b.querySelector('svg');
    if (!svg) return false;
    // Send buttons are typically small and near the bottom of the page
    const rect = b.getBoundingClientRect();
    return rect.bottom > window.innerHeight * 0.7 && rect.width < 60;
  });
}
if (!btn) return { ok: false, reason: 'no_send_button' };
if (btn.disabled) return { ok: false, reason: 'send_button_disabled' };
btn.click();
return { ok: true };
"""


# NOTE: The JS blobs below run inside the nested `root` iframe (via
# _run_js_in_frame), not the main chatgpt.com page. That iframe holds
# ChatGPT Deep Research's plan card, live progress, and the completed
# report — the main page contains only the prompt composer and sidebar.
JS_PLAN_STATUS = r"""
// Plan signal inside the root frame: the plan card is the first block of
// structured content rendered after submission. It shows the numbered
// research steps plus a "Stop research" button while research is running.
// Either is enough to consider the plan "ready".
const bodyText = (document.body && document.body.innerText || '').slice(0, 6000);
const stopBtn = Array.from(document.querySelectorAll('button, [role="button"]'))
  .find(b => /stop research/i.test((b.innerText || b.getAttribute('aria-label') || '').trim()));
const hasStopBtn = !!stopBtn;
// Text-based signals for the plan — match ChatGPT's standard plan phrasing.
const hasPlanText = /research plan|research steps|I'll (investigate|research|explore|look into|analyze|examine)/i.test(bodyText)
  || /^\s*\d+\.\s+\S/m.test(bodyText);
if (hasStopBtn || hasPlanText) {
  return { state: 'found', text: bodyText.slice(0, 3000) };
}
return { state: 'no_plan', bodyLen: bodyText.length };
"""


JS_APPROVE_PLAN = r"""
// ChatGPT Deep Research auto-starts after submission — there is no gated
// "Start research" approval step. If research is visibly running (Stop
// research button present) or already complete, treat as success. This
// subcommand exists for protocol symmetry with gemini/claude-ai.
const stopBtn = Array.from(document.querySelectorAll('button, [role="button"]'))
  .find(b => /stop research/i.test((b.innerText || b.getAttribute('aria-label') || '').trim()));
const bodyText = (document.body && document.body.innerText || '').slice(0, 3000);
const autoStarted = !!stopBtn || /Research completed in/i.test(bodyText)
  || /searching|browsing|reading|analyzing/i.test(bodyText);
if (autoStarted) return { ok: true, detail: 'auto_started' };
// Fallback: look for any explicit start/approve button inside the frame.
const candidates = ['Start research', 'Approve', "Let's go", 'Begin research', 'Start'];
for (const name of candidates) {
  const btn = findByRole('button', name);
  if (btn) { btn.click(); return { ok: true, detail: 'clicked', name }; }
}
return { ok: false, reason: 'no_approve_button' };
"""


JS_CHECK_COMPLETION = r"""
// Completion signal inside the root frame: the "Stop research" button
// disappears and the status line "Research completed in Nm" appears. The
// final report replaces the live progress view — look for both the text
// and the absence of the stop button to be sure.
const stopBtn = Array.from(document.querySelectorAll('button, [role="button"]'))
  .find(b => /stop research/i.test((b.innerText || b.getAttribute('aria-label') || '').trim()));
const bodyText = (document.body && document.body.innerText || '').slice(0, 6000);
const statsPresent = /Research completed in/i.test(bodyText);
const hasExport = !!Array.from(document.querySelectorAll('button, [role="button"]'))
  .find(b => /^export$/i.test((b.innerText || b.getAttribute('aria-label') || '').trim()));
const stillRunning = !!stopBtn;
return {
  complete: (statsPresent || hasExport) && !stillRunning,
  hasStats: statsPresent,
  hasExport,
  stillRunning,
};
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


# Regex for chatgpt.com tab URLs that imply a logged-in session.
# /deep-research or /c/<id> (conversation pages) indicate authenticated state.
_LOGGED_IN_PATH_RE = re.compile(
    r"^https://chatgpt\.com/(deep-research|c(/|$)|g(/|$)|gpts(/|$)|settings(/|$))"
)


def _scan_targets_for_login(targets: list[dict]) -> dict | None:
    """Scan Chrome targets for any chatgpt.com page that looks logged in.

    Returns the matching target dict or None. This is how we handle the
    'magic link opens in a new tab' flow: login cookies land in the
    profile, and the new tab shows chatgpt.com/deep-research (or similar).
    We don't need to attach to that tab — its URL in /json/list is enough.
    """
    for t in targets:
        if t.get("type") != "page":
            continue
        url = t.get("url") or ""
        if "chatgpt.com" not in url:
            continue
        if "/auth/login" in url or "login.chatgpt.com" in url:
            continue
        if _LOGGED_IN_PATH_RE.match(url):
            return t
    return None


class DomMismatch(Exception):
    pass


def _run_js(pw: Pw, js: str, timeout: int = ACTION_TIMEOUT):
    return pw.eval_json(JS_HELPERS + "\n" + js, timeout=timeout)


def _run_js_in_frame(pw: Pw, js: str, timeout: int = ACTION_TIMEOUT):
    """Like _run_js, but runs inside the nested `root` iframe that hosts the
    ChatGPT Deep Research UI (plan, progress, completed report)."""
    return pw.eval_json_in_root_frame(JS_HELPERS + "\n" + js, timeout=timeout)


def cmd_login(pw: Pw, args) -> int:
    """Launch a real Chrome (no Playwright control), attach via CDP, and
    poll login state across ALL tabs. Termination signals:
      - any chatgpt.com tab lands on a logged-in URL -> success
      - attached tab JS reports state=logged_in -> success
      - Chrome process exits (user closed the window) -> exit with last state
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
    print("Launching Chrome for chatgpt.com login...", flush=True)
    print(f"(profile: {pw.profile})", flush=True)
    pw.launch_chrome(headed=True, landing_url=URL_ROOT)
    # Give Chrome a moment to fully paint before attaching.
    time.sleep(2)
    pw.attach()
    print("Attached via CDP. Complete login in the window; auto-detecting...", flush=True)
    print("(you can open the magic link in a new tab -- all tabs are monitored)", flush=True)
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
        chatgpt_pages = [
            (t.get("url") or "") for t in targets
            if t.get("type") == "page" and "chatgpt.com" in (t.get("url") or "")
        ]
        sig = tuple(sorted(chatgpt_pages))
        if sig != last_url_signature:
            if chatgpt_pages:
                print(f"tabs: {list(chatgpt_pages)}", flush=True)
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


def cmd_status(pw: Pw, args) -> int:
    pw.open(headed=False)
    try:
        pw.goto(URL_ROOT)
        # Give ChatGPT's SPA plus any Cloudflare JS challenge a chance to settle.
        time.sleep(4)
        result = _run_js(pw, JS_LOGIN_STATUS)
        # If we're sitting on a Cloudflare challenge, poll for up to ~20s to see
        # if it auto-clears.
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
    print(state)
    if state != "logged_in":
        hint = {k: v for k, v in result.items() if k != "state"}
        if hint:
            print(f"hint: {json.dumps(hint)}", file=sys.stderr)
    return EXIT_OK if state == "logged_in" else EXIT_LOGIN_REQUIRED


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

    # Verify deep research mode is active
    r = _run_js(pw, JS_ACTIVATE_RESEARCH)
    if not r or not r.get("ok"):
        print(f"DOM_MISMATCH: deep research mode not detected ({r})", file=sys.stderr)
        return EXIT_DOM_MISMATCH

    # Fill prompt (inject the prompt via JSON-encoded literal)
    prompt_js = JS_FILL_PROMPT.replace("__PROMPT__", json.dumps(prompt_text))
    r = _run_js(pw, prompt_js)
    if not r or not r.get("ok"):
        print(f"DOM_MISMATCH: prompt textbox not found ({r})", file=sys.stderr)
        return EXIT_DOM_MISMATCH
    time.sleep(0.5)

    # Click send button
    r = _run_js(pw, JS_CLICK_SEND)
    if not r or not r.get("ok"):
        print(f"DOM_MISMATCH: send button not clickable ({r})", file=sys.stderr)
        return EXIT_DOM_MISMATCH

    print("research_started")
    return EXIT_OK


def cmd_wait_plan(pw: Pw, args) -> int:
    pw.attach()  # idempotent — reattach if the sidecar lost us
    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        status = _run_js_in_frame(pw, JS_PLAN_STATUS)
        if status and status.get("state") == "found":
            text = status.get("text", "").strip()
            if text:
                print(text)
                return EXIT_OK
        time.sleep(PLAN_POLL_INTERVAL_S)
    print("ERROR: plan text did not appear within timeout", file=sys.stderr)
    return EXIT_TIMEOUT


def cmd_approve_plan(pw: Pw, args) -> int:
    pw.attach()
    r = _run_js_in_frame(pw, JS_APPROVE_PLAN)
    if not r or not r.get("ok"):
        print(f"DOM_MISMATCH: approve button not found ({r})", file=sys.stderr)
        return EXIT_DOM_MISMATCH
    # For ChatGPT, approval is a no-op (research auto-starts); detail explains.
    print(f"plan_approved ({r.get('detail', 'ok')})")
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
            r = _run_js_in_frame(pw, JS_CHECK_COMPLETION, timeout=15)
            consecutive_errors = 0
        except Exception as e:
            consecutive_errors += 1
            if consecutive_errors >= 3:
                print(f"ERROR: completion check failed 3x: {e}", file=sys.stderr)
                return EXIT_EXTRACTION_FAIL
            continue

        if r and r.get("complete") and not r.get("stillRunning"):
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

    # The report lives inside the nested `root` iframe (see eval_json_in_root_frame
    # for context). Give the completed view a moment to fully paint before
    # running the extractor — ChatGPT streams the final markdown in chunks.
    time.sleep(2)

    try:
        result = _run_js_in_frame(pw, script_body, timeout=60)
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
    p = argparse.ArgumentParser(description="playwright-cli driver for chatgpt.com deep research")
    p.add_argument("--session", default=DEFAULT_SESSION)
    p.add_argument("--profile", default=str(DEFAULT_PROFILE))
    p.add_argument("--browser", default=DEFAULT_BROWSER)
    p.add_argument("--port", type=int, default=DEFAULT_CDP_PORT, help="Chrome DevTools remote debugging port")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("login", help="one-time headed login")
    sp.add_argument("--timeout", type=int, default=600, help="max seconds to wait for SSO completion")

    sp = sub.add_parser("status", help="check login state")
    sp.add_argument("--close", action="store_true", help="close session after check")

    sp = sub.add_parser("start-research", help="submit a prompt, activate Deep Research mode")
    sp.add_argument("--prompt-file", required=True)

    sp = sub.add_parser("wait-plan", help="wait for research plan text, print it")
    sp.add_argument("--timeout", type=int, default=120)

    sub.add_parser("approve-plan", help="click approval button to start research")

    sp = sub.add_parser("wait-complete", help="poll for completion")
    sp.add_argument("--timeout", type=int, default=5400)  # 90 min (ChatGPT DR can take longer)

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
        "wait-complete": cmd_wait_complete,
        "extract": cmd_extract,
        "close": cmd_close,
    }
    return handlers[args.cmd](pw, args)


if __name__ == "__main__":
    sys.exit(main())
