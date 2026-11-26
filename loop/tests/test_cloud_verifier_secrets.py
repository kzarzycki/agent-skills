"""scripts/cloud_verifier.py prints no secret: with fake secrets in every place the script reads one, each output path
(seed, a refused refresh, verify, a command's stderr, a traceback, the verifier's own output, a thread error, a debug
print) shows neither a value nor any 8-character slice of one on stdout or stderr (#1095)."""

from __future__ import annotations

import base64
import importlib.util
import io
import json
import os
import secrets
import subprocess
import time
import urllib.error
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "engineering-loop"
    / "scripts"
    / "cloud_verifier.py"
)
SPEC = importlib.util.spec_from_file_location("cloud_verifier_secrets", SCRIPT)
assert SPEC and SPEC.loader
cv = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cv)

VAR = "CODEX_AUTH_JSON"


def fake() -> str:
    return secrets.token_urlsafe(30)


def jwt(days: float) -> str:
    claims = base64.urlsafe_b64encode(json.dumps({"exp": time.time() + days * 86400}).encode())
    return f"{fake()}.{claims.decode().rstrip('=')}.{fake()}"


def login(days: float, refresh: bool = True) -> dict:
    return {
        "OPENAI_API_KEY": None,
        "tokens": {
            "id_token": fake(),
            "access_token": jwt(days),
            "refresh_token": fake() if refresh else "",
            "account_id": fake(),
        },
        "last_refresh": "2026-01-01T00:00:00Z",
    }


def values(auth: dict) -> list[str]:
    return [v for v in auth["tokens"].values() if v]


@pytest.fixture
def world(tmp_path, monkeypatch):
    """Fake secrets everywhere the script reads one: the seeded variable, the host's and the seed home's logins and
    the Claude Code login; `shown` lists every value the output must not hold."""
    vm = login(5, refresh=False)
    seeded = base64.b64encode(json.dumps(vm).encode()).decode()
    host, seed = login(9), login(9)
    claude = {
        "accessToken": fake(),
        "refreshToken": fake(),
        "expiresAt": (time.time() + 3600) * 1000,
    }
    for name, auth in (("codex", host), ("codex-cloud", seed)):
        (tmp_path / name).mkdir()
        (tmp_path / name / "auth.json").write_text(json.dumps(auth))
    (tmp_path / "home/.claude").mkdir(parents=True)
    (tmp_path / "home/.claude/.credentials.json").write_text(json.dumps({"claudeAiOauth": claude}))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    monkeypatch.setenv("CODEX_CLOUD_HOME", str(tmp_path / "codex-cloud"))
    monkeypatch.setenv(VAR, seeded)
    monkeypatch.setattr(
        cv.sys, "platform", "linux"
    )  # no keychain: the token comes from the file above
    real_run = cv.run

    def run(*cmd: str, check: bool = True, **kw):
        if cmd[:3] == ("claude", "auth", "status"):
            return subprocess.CompletedProcess(cmd, 0, '{"orgId": "org"}', "")
        return real_run(*cmd, check=check, **kw)

    monkeypatch.setattr(cv, "run", run)
    shown = [
        seeded,
        *values(vm),
        *values(host),
        *values(seed),
        claude["accessToken"],
        claude["refreshToken"],
    ]
    return {
        "vm": vm,
        "seeded": seeded,
        "host": host,
        "seed": seed,
        "claude": claude,
        "shown": shown,
    }


def assert_clean(capfd, shown: list[str]) -> str:
    """Everything printed, at the file descriptors too (a child's output), once no secret's slice is in it."""
    got = capfd.readouterr()
    out = got.out + got.err
    for n, value in enumerate(shown):
        leaks = [i for i in range(len(value) - 7) if value[i : i + 8] in out]
        assert not leaks, f"secret {n} shows at its characters {leaks[:5]}"
    return out


def environment_api(world, fail: str = "", echo: dict | None = None):
    """The environment API: `fail` names an environment whose store fails with an error echoing what was sent."""

    refreshed: list[str] = []

    def post_json(url: str, body: dict | None, headers: dict) -> dict:
        if url == cv.REFRESH_URL:
            if echo is not None:
                raise urllib.error.HTTPError(
                    url, 400, "bad", {}, io.BytesIO(json.dumps(echo).encode())
                )
            new = {"access_token": jwt(10), "refresh_token": fake(), "id_token": fake()}
            world["shown"].extend(new.values())
            refreshed.extend(new.values())
            return new
        if body is not None:  # the copy stored in the environment is a secret too
            world["shown"].append(body["config"]["environment"][VAR])
        if fail and fail in url and body is not None:
            raise ValueError(f"rejected {headers} {json.dumps(body)} after {refreshed}")
        return {"name": "dev", "config": {"environment": {}, "network_config": {}}}

    return post_json


def test_a_seed_that_refreshes_and_one_whose_store_fails_print_no_secret(
    world, monkeypatch, capfd
) -> None:
    host = login(2)  # under --host-refresh-days: refreshed first
    (Path(os.environ["CODEX_HOME"]) / "auth.json").write_text(json.dumps(host))
    world["shown"].extend(values(host))
    monkeypatch.setattr(cv, "post_json", environment_api(world, fail="env_B"))
    assert cv.main(["seed", "--env", "env_A", "--env", "env_B"]) == 1
    out = assert_clean(capfd, world["shown"])
    assert (
        "refreshed the host login" in out and "seeded dev (env_A)" in out and "env_B failed" in out
    )


def test_a_refused_refresh_that_echoes_the_refresh_token_prints_no_secret(
    world, monkeypatch, capfd
) -> None:
    host = login(2)
    (Path(os.environ["CODEX_HOME"]) / "auth.json").write_text(json.dumps(host))
    world["shown"].extend(values(host))
    echo = {
        "error": {
            "code": host["tokens"]["refresh_token"],
            "message": world["claude"]["accessToken"],
        }
    }
    monkeypatch.setattr(cv, "post_json", environment_api(world, echo=echo))
    assert cv.main(["seed", "--env", "env_A"]) == 2
    assert "was refused (HTTP 400" in assert_clean(capfd, world["shown"])


def test_a_seed_home_whose_refresh_is_refused_prints_no_secret(world, monkeypatch, capfd) -> None:
    (
        Path(os.environ["CODEX_HOME"]) / "auth.json"
    ).unlink()  # no host login: the seed home's is used
    seed = login(2)  # under --min-days: refreshed first
    (Path(os.environ["CODEX_CLOUD_HOME"]) / "auth.json").write_text(json.dumps(seed))
    world["shown"].extend(values(seed))
    echo = {
        "error": {"code": seed["tokens"]["refresh_token"], "message": seed["tokens"]["id_token"]}
    }
    monkeypatch.setattr(cv, "post_json", environment_api(world, echo=echo))
    assert cv.main(["seed", "--env", "env_A"]) == 2
    assert "no usable Codex login" in assert_clean(capfd, world["shown"])


@pytest.fixture
def vm(world, tmp_path, monkeypatch):
    """A checkout at the PR's head, `gh` stubbed and a fake `codex` that, run as the verifier, prints its whole
    environment and the token file `verify` wrote."""
    work = tmp_path / "work"
    work.mkdir()
    for args in (
        ["init", "-q"],
        [
            "-c",
            "user.email=t@example.com",
            "-c",
            "user.name=t",
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "one",
        ],
    ):
        subprocess.run(["git", *args], cwd=work, check=True)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=work, check=True, capture_output=True, text=True
    ).stdout.strip()
    (Path(os.environ["CODEX_HOME"]) / "auth.json").unlink()  # the VM has no login of its own
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "codex").write_text(
        "#!/bin/bash\n"
        'if [ "$1" = login ]; then test -z "$FAKE_REFUSE" && test -f "$CODEX_HOME/auth.json"; exit; fi\n'
        "cat >/dev/null\n"
        "env\n"
        'cat "$CODEX_HOME/auth.json"; echo\n'
        f'echo "the variable: ${{{VAR}:-unset}}"\n'
        'while [ "$1" != -o ]; do shift; done\n'
        "printf 'final\\nSATISFIED: yes\\n' > \"$2\"\n"
    )
    (bin_dir / "codex").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.chdir(work)
    stub = cv.run
    seen: dict = {}

    def run(*cmd: str, check: bool = True, **kw):
        if cmd[:2] == ("gh", "api") and "/pulls/" in cmd[2]:
            if "stderr" in seen:  # a command that fails echoing secrets on its stderr
                return stub("sh", "-c", seen["stderr"], check=check)
            return subprocess.CompletedProcess(
                cmd, 0, json.dumps({"head": {"sha": head, "ref": "pr"}}), ""
            )
        if cmd[:2] == ("gh", "api"):
            seen["posted"] = kw["input"]
            return subprocess.CompletedProcess(cmd, 0, "https://example.com/c/1\n", "")
        return stub(*cmd, check=check, **kw)

    monkeypatch.setattr(cv, "run", run)
    monkeypatch.setattr(
        cv, "EVENTS", None
    )  # this clone has no origin: the event's push warning is not under test
    brief = tmp_path / "brief.md"
    brief.write_text("Review PR #7.\n")
    return ["verify", "--pr", "7", "--brief", str(brief)], seen


def test_a_verifier_that_prints_its_environment_and_the_token_file_shows_no_secret(
    world, vm, capfd
) -> None:
    argv, seen = vm
    assert cv.main(argv) == 0
    out = assert_clean(capfd, world["shown"])
    assert "the variable: unset" in out  # Codex ran without it
    assert '"access_token": "[secret]' in out and "PATH=" in out  # the relay passed its output on
    assert out.rstrip().endswith("https://example.com/c/1") and "SATISFIED: yes" in seen["posted"]


def test_a_refused_seed_is_described_by_length_hash_and_days_left(
    world, vm, monkeypatch, capfd
) -> None:
    argv, _ = vm
    monkeypatch.setenv("FAKE_REFUSE", "1")
    assert cv.main(argv) == 2
    out = assert_clean(capfd, world["shown"])
    assert cv.describe(VAR, world["seeded"]) in out and "days left" in out


def test_a_refused_command_whose_stderr_echoes_secrets_prints_none(world, vm, capfd) -> None:
    argv, seen = vm
    seen["stderr"] = (
        f'printf "%s\\n%s\\n" "${VAR}" "{world["vm"]["tokens"]["access_token"]}" >&2; exit 1'
    )
    assert cv.main(argv) == 2
    assert "exited 1" in assert_clean(capfd, world["shown"])


def test_an_unexpected_exception_prints_its_traceback_redacted_and_exits_1(
    world, monkeypatch, capfd
) -> None:
    def verify(*_):
        raise RuntimeError(f"boom {world['seeded']} {world['vm']['tokens']['access_token']}")

    monkeypatch.setattr(cv, "verify", verify)
    assert cv.main(["verify", "--pr", "1", "--brief", "b.md"]) == 1
    out = assert_clean(capfd, world["shown"])
    assert "Traceback" in out and "RuntimeError: boom [secret]" in out


def test_a_debug_print_of_the_variables_opening_is_masked(world, monkeypatch, capfd) -> None:
    token = world["vm"]["tokens"]["access_token"]
    monkeypatch.setattr(cv, "verify", lambda *_: print(os.environ[VAR][:30], token[5:15]) or 0)
    assert cv.main(["verify", "--pr", "1", "--brief", "b.md"]) == 0
    assert "[secret]" in assert_clean(capfd, world["shown"])


def test_a_thread_error_that_echoes_its_token_prints_none_of_it(world, monkeypatch, capfd) -> None:
    tokens = world["host"]["tokens"]

    def rpc(token: str):
        raise cv.Unusable(f"refused bearer {token[:20]}... (refresh {tokens['refresh_token']})")

    monkeypatch.setattr(cv, "Rpc", rpc)
    assert cv.main(["thread-exec", "--thread", "t", "--env", "e", "--", "true"]) == 2
    assert "route 2 or the host verifier" in assert_clean(capfd, world["shown"])


def test_a_secret_split_over_two_writes_is_still_masked(capfd) -> None:
    value = fake()
    cv.REDACT.add(value)
    stream = io.StringIO()
    writer = cv.Redacting(stream)
    writer.write(f"a {value[:12]}")
    writer.flush()
    assert stream.getvalue() == ""  # a partial line is held: it may end in half a secret
    writer.write(f"{value[12:]} b\nopen")
    writer.end()
    assert stream.getvalue() == "a [secret] b\nopen"


def test_describe_names_length_and_a_short_hash() -> None:
    assert cv.describe("X", "abc") == "X: 3 chars, sha256 ba7816bf"


@pytest.mark.parametrize(
    "make",
    [
        lambda s: "!" + s + "!?" + s,  # not base64
        lambda s: base64.b64encode(("not json " + s).encode()).decode(),  # base64, not JSON
        lambda s: base64.b64encode(json.dumps({"note": s}).encode()).decode(),  # JSON, no tokens
    ],
    ids=["not-base64", "not-json", "no-tokens"],
)
def test_a_seed_that_is_no_login_is_refused_by_length_and_hash_alone(
    world, vm, monkeypatch, capfd, make
) -> None:
    argv, _ = vm
    value = make(secrets.token_urlsafe(24))
    monkeypatch.setenv(VAR, value)
    assert cv.main(argv) == 2
    out = assert_clean(capfd, [value])
    assert "not a base64 ChatGPT login" in out and cv.describe(VAR, value) in out


def test_a_background_descendant_of_codex_does_not_hold_verify_up(
    world, vm, tmp_path, capfd
) -> None:
    argv, _ = vm
    codex = tmp_path / "bin" / "codex"
    sleeper = tmp_path / "sleeper.pid"
    text = codex.read_text().replace(
        "cat >/dev/null\n", f"cat >/dev/null\nsleep 120 &\necho $! > {sleeper}\necho trailing line\n"
    )
    codex.write_text(text)
    assert cv.main(argv) == 0
    assert "trailing line" in capfd.readouterr().out
    pid = int(sleeper.read_text())
    try:
        os.kill(pid, 0)  # verify returned while the descendant still ran: it did not wait for it
    finally:
        os.kill(pid, 9)


def test_a_line_a_descendant_prints_after_verify_returns_is_still_redacted(
    world, vm, tmp_path, capfd
) -> None:
    argv, _ = vm
    go, done = tmp_path / "go", tmp_path / "done"
    codex = tmp_path / "bin" / "codex"
    text = codex.read_text().replace(
        "cat >/dev/null\n",
        f'cat >/dev/null\n(while [ ! -f "{go}" ]; do sleep 0.1; done;'
        f' cat "$CODEX_HOME/auth.json"; echo; touch "{done}") &\n',
    )
    codex.write_text(text)
    try:
        assert cv.main(argv) == 0
        capfd.readouterr()  # what arrived while `verify` ran is checked by the other tests
    finally:
        go.touch()  # the child prints only now, with the real streams back in place
    deadline = time.monotonic() + 10
    while not done.exists() and time.monotonic() < deadline:
        time.sleep(0.1)
    assert done.exists()
    time.sleep(1)  # the relay thread writes the line it read
    assert_clean(capfd, world["shown"])
