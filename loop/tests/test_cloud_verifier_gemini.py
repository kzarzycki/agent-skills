"""scripts/cloud_verifier.py verify --harness gemini: the Gemini verifier runs in the worker's cloud VM when the
environment holds a Gemini login, says so in one line and exits 5 (use a host) when it does not, and is left to the
worker's own host outside the cloud (#2694)."""

from __future__ import annotations

import pytest
from test_cloud_verifier import checkout, cv  # noqa: F401 - `checkout` is a fixture


def verify_gemini(brief, capsys, monkeypatch, env: dict[str, str], ran: list) -> tuple[int, str]:
    for name in ("CLAUDE_CODE_REMOTE", "GEMINI_OAUTH_JSON", "GEMINI_CLI_HOME"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)

    def relay(cmd, text, keep=None):
        ran.append(cmd)
        keep.write_text("# Report\nSATISFIED: yes\n")
        return 0

    monkeypatch.setattr(cv, "relay_exec", relay)
    monkeypatch.setattr(cv, "ensure_gemini", lambda: None, raising=False)
    code = command(["verify", "--pr", "7", "--brief", str(brief), "--harness", "gemini"])
    return code, capsys.readouterr().err


def command(argv: list[str]) -> int:
    """`cv.command`'s exit code, an argparse refusal (SystemExit) included, so a missing choice fails an assertion."""
    try:
        return cv.command(argv)
    except SystemExit as stop:
        return int(stop.code or 0)


@pytest.mark.parametrize(
    ("env", "tmp_home", "code", "runs", "line"),
    [
        # cloud with a login: the pass runs here, on the worker's checkout
        ({"CLAUDE_CODE_REMOTE": "true", "GEMINI_OAUTH_JSON": "e30="}, False, 0, 1, False),
        # cloud without one: one line, exit 5, nothing ran
        ({"CLAUDE_CODE_REMOTE": "true"}, False, 5, 0, True),
        # a host worker: the host route's, with no line from here
        ({}, False, 5, 0, False),
    ],
    ids=["cloud with a login", "cloud without a login", "host worker"],
)
def test_gemini_route_choice(
    checkout,  # noqa: F811
    capsys,
    monkeypatch,
    tmp_path,
    env,
    tmp_home,
    code,
    runs,
    line,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "no-home"))  # no ~/.gemini login on the machine
    ran: list = []
    got, err = verify_gemini(checkout[2], capsys, monkeypatch, env, ran)
    assert (got, len(ran)) == (code, runs)
    lines = [x for x in err.splitlines() if "Gemini login" in x]
    assert len(lines) == int(line)
    if line:
        assert "host verifier" in lines[0]
    if runs:
        assert ran[0][:3] == ["gemini", "--approval-mode", "yolo"]
        assert len(checkout[3]) == 1  # the report was posted


def test_gemini_login_file_counts_as_a_login(checkout, capsys, monkeypatch, tmp_path) -> None:  # noqa: F811
    home = tmp_path / "home"
    (home / ".gemini").mkdir(parents=True)
    (home / ".gemini/oauth_creds.json").write_text("{}")
    monkeypatch.setenv("HOME", str(home))
    ran: list = []
    got, _ = verify_gemini(checkout[2], capsys, monkeypatch, {"CLAUDE_CODE_REMOTE": "true"}, ran)
    assert got == 0 and len(ran) == 1


def test_gemini_with_an_effort_is_refused(checkout, capsys) -> None:  # noqa: F811
    argv = [
        "verify",
        "--pr",
        "7",
        "--brief",
        str(checkout[2]),
        "--harness",
        "gemini",
        "--effort",
        "high",
    ]
    assert command(argv) == 2
    assert "--effort" in capsys.readouterr().err


def test_a_login_in_the_report_is_redacted_before_it_is_posted(monkeypatch, tmp_path) -> None:
    home = tmp_path / "home"
    (home / ".gemini").mkdir(parents=True)
    (home / ".gemini/oauth_creds.json").write_text('{"access_token": "ya29.secret-access-token"}')
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("GEMINI_OAUTH_JSON", raising=False)
    monkeypatch.delenv("GEMINI_CLI_HOME", raising=False)
    monkeypatch.setattr(cv, "REDACT", cv.Redactor())
    monkeypatch.setattr(cv.shutil, "which", lambda name: "/bin/gemini")
    cv.ensure_gemini()
    sent: list[str] = []

    def run(*cmd, **kw):
        sent.append(kw["input"])
        return type("R", (), {"stdout": "u\n1"})()

    monkeypatch.setattr(cv, "run", run)
    cv.post(7, "report ya29.secret-access-token end")
    assert sent == ["report [secret] end"]


def test_a_non_object_login_variable_is_refused(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("GEMINI_CLI_HOME", raising=False)
    monkeypatch.setenv("GEMINI_OAUTH_JSON", "WzFd")  # base64 of [1]
    monkeypatch.setattr(cv.shutil, "which", lambda name: "/bin/gemini")
    with pytest.raises(cv.Refused, match="not a base64 Gemini login"):
        cv.ensure_gemini()


def test_a_report_with_links_and_dates_survives_post_with_both_logins_loaded(
    monkeypatch, tmp_path
) -> None:
    gemini = {
        "access_token": "ya29.secret-access-token",
        "refresh_token": "1//secret-refresh-token",
        "scope": "https://www.googleapis.com/auth/cloud-platform https://www.googleapis.com/auth/userinfo.email",
        "token_type": "Bearer",
        "expiry_date": 1788000000000,
    }
    codex = {
        "tokens": {"access_token": "codex-secret-access", "refresh_token": "codex-secret-refresh"},
        "last_refresh": "2026-11-26T15:00:00.000000Z",
    }
    redact = cv.Redactor()
    redact.gemini(gemini)
    redact.login(codex)
    monkeypatch.setattr(cv, "REDACT", redact)
    sent: list[str] = []

    def run(*cmd, **kw):
        sent.append(kw["input"])
        return type("R", (), {"stdout": "u\n1"})()

    monkeypatch.setattr(cv, "run", run)
    report = (
        "see https://github.com/x and https://www.googleapis.com/auth/cloud-platform, "
        "refreshed 2026-11-26T15:00:00.000000Z, Bearer, 1788000000000\n"
    )
    cv.post(7, report)
    cv.post(7, report + "leak ya29.secret-access-token codex-secret-refresh")
    assert sent == [report, report + "leak [secret] [secret]"]


def test_the_post_time_edit_does_not_undo_the_redaction(monkeypatch) -> None:
    redact = cv.Redactor()
    redact.gemini({"access_token": "ya29.secret-access-token"})
    monkeypatch.setattr(cv, "REDACT", redact)
    sent: list[tuple] = []

    def run(*cmd, **kw):
        sent.append((cmd, kw["input"]))
        return type("R", (), {"stdout": "https://example.com/c/1\n12345"})()

    monkeypatch.setattr(cv, "run", run)
    cv.publish(
        7,
        "report ya29.secret-access-token end",
        {"start": 1, "setup": 2, "review": 3, "post": None},
    )
    assert len(sent) == 2 and "PATCH" in sent[1][0]
    assert all("ya29.secret-access-token" not in text for _, text in sent)
