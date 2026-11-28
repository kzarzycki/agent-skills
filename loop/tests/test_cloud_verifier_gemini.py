"""scripts/cloud_verifier.py verify --harness gemini: the Gemini verifier (the `agy` CLI) runs in the worker's cloud VM when the
environment holds an agy login, says so in one line and exits 5 (use a host) when it does not, and is left to the
worker's own host outside the cloud (#2694)."""

from __future__ import annotations

import base64
import io
import json
import tarfile
from pathlib import Path

import pytest
from test_cloud_verifier import checkout, cv  # noqa: F401 - `checkout` is a fixture


def verify_gemini(brief, capsys, monkeypatch, env: dict[str, str], ran: list) -> tuple[int, str]:
    for name in ("CLAUDE_CODE_REMOTE", "AGY_OAUTH_JSON"):
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
        ({"CLAUDE_CODE_REMOTE": "true", "AGY_OAUTH_JSON": "e30="}, False, 0, 1, False),
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
    lines = [x for x in err.splitlines() if "agy login" in x]
    assert len(lines) == int(line)
    if line:
        assert "host verifier" in lines[0]
    if runs:
        assert ran[0][:2] == ["agy", "-p"] and "--dangerously-skip-permissions" in ran[0]
        assert len(checkout[3]) == 1  # the report was posted


def test_gemini_login_file_counts_as_a_login(checkout, capsys, monkeypatch, tmp_path) -> None:  # noqa: F811
    home = tmp_path / "home"
    (home / ".gemini/antigravity-cli").mkdir(parents=True)
    (home / ".gemini/antigravity-cli/antigravity-oauth-token").write_text("{}")
    monkeypatch.setenv("HOME", str(home))
    ran: list = []
    got, _ = verify_gemini(checkout[2], capsys, monkeypatch, {"CLAUDE_CODE_REMOTE": "true"}, ran)
    assert got == 0 and len(ran) == 1


def test_gemini_run_passes_model_effort_and_a_print_timeout(
    checkout,  # noqa: F811
    capsys,
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "no-home"))
    ran: list = []
    argv = ["--model", "gemini-4-hydrogen-medium", "--effort", "high"]
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
    monkeypatch.setenv("AGY_OAUTH_JSON", "e30=")
    monkeypatch.setattr(cv, "ensure_gemini", lambda: None)
    monkeypatch.setattr(
        cv,
        "relay_exec",
        lambda cmd, text, keep=None: (ran.append(cmd), keep.write_text("SATISFIED: yes\n"), 0)[2],
    )
    assert (
        command(["verify", "--pr", "7", "--brief", str(checkout[2]), "--harness", "gemini", *argv])
        == 0
    )
    cmd = ran[0]
    assert cmd[cmd.index("--model") + 1] == "gemini-4-hydrogen-medium"
    assert cmd[cmd.index("--effort") + 1] == "high"
    assert cmd[cmd.index("--print-timeout") + 1] == cv.AGY_PRINT_TIMEOUT


def run_gemini(checkout, monkeypatch, tmp_path) -> tuple[list, str]:  # noqa: F811
    """The argv and stdin text of the one `agy` run a gemini `verify` makes (#3052)."""
    monkeypatch.setenv("HOME", str(tmp_path / "no-home"))
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
    monkeypatch.setenv("AGY_OAUTH_JSON", "e30=")
    monkeypatch.setattr(cv, "ensure_gemini", lambda: None)
    seen: list = []

    def relay(cmd, text, keep=None):
        seen.append((cmd, text))
        keep.write_text("SATISFIED: yes\n")
        return 0

    monkeypatch.setattr(cv, "relay_exec", relay)
    assert (
        command(["verify", "--pr", "7", "--brief", str(checkout[2]), "--harness", "gemini"]) == 0
    )
    return seen[0]


def test_agy_gets_the_brief_text_as_its_prompt_argument(checkout, monkeypatch, tmp_path) -> None:  # noqa: F811
    cmd, stdin_text = run_gemini(checkout, monkeypatch, tmp_path)
    assert cmd[:2] == ["agy", "-p"]
    # `agy -p` ignores stdin, so the argument is the whole brief
    assert cmd[2] == stdin_text
    assert "Follow the brief on stdin" not in cmd[2]
    assert cmd[2].startswith("AGENT_SIGNATURE=")


def test_agy_argv_keeps_its_flags_after_the_prompt(checkout, monkeypatch, tmp_path) -> None:  # noqa: F811
    cmd, _ = run_gemini(checkout, monkeypatch, tmp_path)
    assert cmd[3:] == [
        "--dangerously-skip-permissions",
        "--print-timeout",
        cv.AGY_PRINT_TIMEOUT,
        "--output-format",
        "json",
    ]


def login(files: dict[str, bytes], extra: list[tarfile.TarInfo] | None = None) -> str:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        for info in extra or []:
            tar.addfile(info)
    return base64.b64encode(buf.getvalue()).decode()


TOKEN, SCOPE = cv.AGY_FILES
GOOD = {TOKEN: b'{"access_token": "ya29.secret-access-token"}', SCOPE: b"user-scope-secret-value"}


@pytest.fixture
def home(monkeypatch, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(cv, "REDACT", cv.Redactor())
    monkeypatch.setattr(cv.shutil, "which", lambda name: "/bin/agy")
    return home


def test_the_seeded_login_is_written_mode_600_outside_the_workspace(monkeypatch, home) -> None:
    monkeypatch.setenv("AGY_OAUTH_JSON", login(GOOD))
    cv.ensure_gemini()
    for name, data in GOOD.items():
        path = home / name
        assert path.read_bytes() == data
        assert path.stat().st_mode & 0o777 == 0o600
        assert not path.is_relative_to(Path.cwd())


def test_the_seeded_login_is_redacted_from_a_posted_report(monkeypatch, home) -> None:
    monkeypatch.setenv("AGY_OAUTH_JSON", login(GOOD))
    cv.ensure_gemini()
    sent: list[str] = []

    def run(*cmd, **kw):
        sent.append(kw["input"])
        return type("R", (), {"stdout": "u\n1"})()

    monkeypatch.setattr(cv, "run", run)
    cv.post(7, "report ya29.secret-access-token and user-scope-secret-value end")
    assert sent == ["report [secret] and [secret] end"]


def test_the_variable_is_stripped_from_the_childs_environment(monkeypatch) -> None:
    seen: list[dict] = []

    class Stop(Exception):
        pass

    def popen(cmd, **kw):
        seen.append(kw["env"])
        raise Stop

    monkeypatch.setenv("AGY_OAUTH_JSON", "e30=")
    monkeypatch.setattr(cv.subprocess, "Popen", popen)
    with pytest.raises(Stop):
        cv.relay_exec(["agy", "-p", "x"], "brief")
    assert "AGY_OAUTH_JSON" not in seen[0] and seen[0]["AGY_CLI_FORCE_FILE_TOKEN_STORAGE"] == "1"


@pytest.mark.parametrize("kind", ["other path", "absolute", "parent", "symlink"])
def test_a_tar_member_at_any_other_path_is_refused(monkeypatch, home, kind) -> None:
    link = tarfile.TarInfo(TOKEN)
    link.type, link.linkname = tarfile.SYMTYPE, "/etc/passwd"
    seeded = {
        "other path": login({**GOOD, ".bashrc": b"x"}),
        "absolute": login({**GOOD, "/etc/cron.d/x": b"x"}),
        "parent": login({**GOOD, "../escape": b"x"}),
        "symlink": login({}, [link]),
    }[kind]
    monkeypatch.setenv("AGY_OAUTH_JSON", seeded)
    with pytest.raises(cv.Refused):
        cv.ensure_gemini()
    assert not (home / TOKEN).exists() and not (home / ".bashrc").exists()


def test_an_oversized_member_is_refused_even_compressed(monkeypatch, home) -> None:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo(TOKEN)
        info.size = 10 * 1024 * 1024
        tar.addfile(info, io.BytesIO(b"x" * info.size))
    monkeypatch.setenv("AGY_OAUTH_JSON", base64.b64encode(buf.getvalue()).decode())
    with pytest.raises(cv.Refused, match="over"):
        cv.ensure_gemini()
    assert not (home / TOKEN).exists()


@pytest.mark.parametrize(
    ("content", "secret"),
    [
        ('{"session": {"key": "secret-under-another-key"}}', "secret-under-another-key"),
        ('"bare-json-string-secret"', "bare-json-string-secret"),
        ("plain-text-secret-file", "plain-text-secret-file"),
    ],
)
def test_a_secret_under_any_key_or_shape_is_redacted(content, secret) -> None:
    redact = cv.Redactor()
    redact.agy(content)
    assert redact(f"leak {secret} end") == "leak [secret] end"
    assert redact("see https://github.com/x/y end") == "see https://github.com/x/y end"


def test_a_variable_that_is_not_a_tar_is_refused(monkeypatch, home) -> None:
    monkeypatch.setenv("AGY_OAUTH_JSON", "WzFd")  # base64 of [1]
    with pytest.raises(cv.Refused, match="not a base64 tar"):
        cv.ensure_gemini()


def test_a_report_with_links_and_dates_survives_post_with_both_logins_loaded(
    monkeypatch, tmp_path
) -> None:
    agy = json.dumps(
        {
            "access_token": "ya29.secret-access-token",
            "refresh_token": "1//secret-refresh-token",
            "scope": "https://www.googleapis.com/auth/cloud-platform https://www.googleapis.com/auth/userinfo.email",
            "token_type": "Bearer",
            "expiry_date": 1788000000000,
        }
    )
    codex = {
        "tokens": {"access_token": "codex-secret-access", "refresh_token": "codex-secret-refresh"},
        "last_refresh": "2026-11-26T15:00:00.000000Z",
    }
    redact = cv.Redactor()
    redact.agy(agy)
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
    redact.agy('{"access_token": "ya29.secret-access-token"}')
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
