"""The wizard template's library: .env writes that read back and parse whole, and prompts that end at EOF."""

from __future__ import annotations

import os
import select
import shutil
import stat
import subprocess
import time
from pathlib import Path

import pytest

TEMPLATE = Path(__file__).parents[1] / "skills" / "wizard" / "template.sh"
MARKER = "# STAGES:"


@pytest.fixture
def library(tmp_path: Path) -> Path:
    """The template's library part, everything above the STAGES marker, as a file bash can source."""
    text = TEMPLATE.read_text()
    assert MARKER in text, "template.sh lost its STAGES marker"
    lib = tmp_path / "library.sh"
    lib.write_text(text[: text.index(MARKER)])
    return lib


def bash(
    library: Path, cwd: Path, script: str, stdin: str = "", env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", f'source "$1"\n{script}', "wizard", str(library)],
        cwd=cwd,
        env=env,
        input=stdin,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def round_trip(library: Path, cwd: Path, value: str) -> subprocess.CompletedProcess[str]:
    """write_env KEY "$value", its messages to stderr, then _existing KEY to stdout."""
    return subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"\nwrite_env KEY "$VALUE" >&2; _existing KEY',
            "wizard",
            str(library),
        ],
        cwd=cwd,
        env={**os.environ, "VALUE": value},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("plain value", id="no-quote"),
        pytest.param("it's ready", id="apostrophe"),
        pytest.param('it\'s "quoted"', id="apostrophe-and-double-quote"),
    ],
)
def test_existing_reads_back_each_form_write_env_writes(
    library: Path, tmp_path: Path, value: str
) -> None:
    result = round_trip(library, tmp_path, value)
    assert result.returncode == 0, result.stderr
    assert result.stdout == value


def test_an_apostrophe_value_is_double_quoted_since_dotenv_parsers_cut_the_shell_escape(
    library: Path, tmp_path: Path
) -> None:
    assert round_trip(library, tmp_path, "it's ready").returncode == 0
    assert (tmp_path / ".env").read_text() == 'KEY="it\'s ready"\n'


def test_a_value_dotenv_cannot_hold_keeps_shell_quoting_and_warns(
    library: Path, tmp_path: Path
) -> None:
    result = round_trip(library, tmp_path, 'it\'s "x"')
    assert result.returncode == 0, result.stderr
    assert (tmp_path / ".env").read_text() == "KEY='it'\\''s \"x\"'\n"
    assert "parsers other than a shell" in result.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not on PATH")
def test_an_apostrophe_value_parses_whole_under_node_env_file(
    library: Path, tmp_path: Path
) -> None:
    assert round_trip(library, tmp_path, "it's ready").returncode == 0
    env = {k: v for k, v in os.environ.items() if k != "KEY"}
    node = subprocess.run(
        ["node", "--env-file=.env", "-e", "process.stdout.write(process.env.KEY)"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert node.returncode == 0, node.stderr
    assert node.stdout == "it's ready"


def test_a_new_env_file_is_created_private_since_it_holds_secrets(
    library: Path, tmp_path: Path
) -> None:
    assert round_trip(library, tmp_path, "secret").returncode == 0
    assert stat.S_IMODE((tmp_path / ".env").stat().st_mode) == 0o600


def test_a_write_through_a_symlink_keeps_the_link(library: Path, tmp_path: Path) -> None:
    target = tmp_path / "shared.env"
    target.write_text("OTHER='kept'\n")
    (tmp_path / ".env").symlink_to(target.name)
    assert round_trip(library, tmp_path, "new").returncode == 0
    assert (tmp_path / ".env").is_symlink()
    assert target.read_text() == "OTHER='kept'\nKEY='new'\n"


def test_ask_fails_at_eof_with_no_input_so_a_closed_stdin_stops_the_wizard(
    library: Path, tmp_path: Path
) -> None:
    result = bash(
        library,
        tmp_path,
        'if ask KEY "Value:" </dev/null; then echo returned-0; else echo returned-$?; fi',
    )
    assert result.stdout.strip().endswith("returned-1"), result.stdout + result.stderr


def test_ask_secret_fails_at_eof_with_no_input_so_a_closed_stdin_stops_the_wizard(
    library: Path, tmp_path: Path
) -> None:
    result = bash(
        library,
        tmp_path,
        'if ask_secret KEY "Secret:" </dev/null; then echo returned-0; else echo returned-$?; fi',
    )
    assert result.stdout.strip().endswith("returned-1"), result.stdout + result.stderr


def stub_bin(tmp_path: Path, scripts: dict[str, str]) -> Path:
    """A directory of stub commands, each a bash script, to put first on PATH."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name, body in scripts.items():
        stub = bin_dir / name
        stub.write_text(f"#!/usr/bin/env bash\n{body}\n")
        stub.chmod(0o755)
    return bin_dir


@pytest.mark.parametrize(
    "openers",
    [
        pytest.param({}, id="no-opener"),
        pytest.param(
            {name: "exit 1" for name in ("wslview", "explorer.exe", "xdg-open", "open")},
            id="every-opener-fails",
        ),
    ],
)
def test_open_url_warns_with_the_url_when_no_browser_opens_so_the_human_visits_it(
    library: Path, tmp_path: Path, openers: dict[str, str]
) -> None:
    bin_dir = stub_bin(tmp_path, openers)
    # Only the stubs and bash itself on PATH, so no real opener on the host is found.
    (bin_dir / "bash").symlink_to(shutil.which("bash"))
    url = "https://example.test/keys"
    result = bash(library, tmp_path, f'open_url "{url}"', env={"PATH": str(bin_dir)})
    assert result.returncode == 0, result.stderr
    assert f"couldn't open a browser, so visit it manually: {url}" in result.stdout


def on_a_pty(
    library: Path,
    cwd: Path,
    script: str,
    env: dict[str, str],
    keys: bytes = b"",
    after: bytes = b"",
) -> bytes:
    """Run the script with a terminal on stdin, stdout and stderr; once `after` shows, type `keys`."""
    leader, follower = os.openpty()
    proc = subprocess.Popen(
        ["bash", "-c", f'source "$1"\n{script}', "wizard", str(library)],
        cwd=cwd,
        env=env,
        stdin=follower,
        stdout=follower,
        stderr=follower,
        start_new_session=True,
    )
    os.close(follower)
    out, typed, deadline = b"", not keys, time.monotonic() + 30
    try:
        while time.monotonic() < deadline:
            ready, _, _ = select.select([leader], [], [], 0.1)
            if ready:
                try:
                    chunk = os.read(leader, 4096)
                except OSError:  # the follower closed: the script ended
                    break
                if not chunk:
                    break
                out += chunk
            if not typed and after in out:
                os.write(leader, keys)
                typed = True
            if proc.poll() is not None and not ready:
                break
    finally:
        proc.kill()
        proc.wait()
        os.close(leader)
    return out


def pty_env(tmp_path: Path, bin_dir: Path) -> dict[str, str]:
    return {
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "TERM": "xterm",
        "INPUTRC": "/dev/null",
    }


def test_clear_falls_back_to_the_ansi_sequence_when_tput_clear_fails(
    library: Path, tmp_path: Path
) -> None:
    bin_dir = stub_bin(tmp_path, {"tput": "exit 1"})
    out = on_a_pty(library, tmp_path, "_clear; echo cleared", pty_env(tmp_path, bin_dir))
    assert b"\033[2J\033[3J\033[H" in out, out
    assert b"cleared" in out, out


def test_clear_uses_tput_clear_when_it_works(library: Path, tmp_path: Path) -> None:
    bin_dir = stub_bin(tmp_path, {"tput": '[ "$1" = clear ] && echo TPUT-CLEAR; exit 0'})
    out = on_a_pty(library, tmp_path, "_clear; echo cleared", pty_env(tmp_path, bin_dir))
    assert b"TPUT-CLEAR" in out, out
    assert b"\033[2J" not in out, out


def test_ask_edits_with_readline_and_prints_no_raw_prompt_markers(
    library: Path, tmp_path: Path
) -> None:
    # "ac", cursor left, "b", Enter: only Readline (read -e) turns that into "abc", and only
    # Readline consumes the \001..\002 markers around the prompt's colour codes.
    bin_dir = stub_bin(tmp_path, {})
    out = on_a_pty(
        library,
        tmp_path,
        'ask KEY "Value:"; printf "<%s>\\n" "$KEY"',
        pty_env(tmp_path, bin_dir),
        keys=b"ac\x1b[Db\r",
        after=b"Value:",
    )
    assert b"<abc>" in out, out
    assert b"\x01" not in out and b"\x02" not in out, out


def test_an_edit_to_the_script_mid_run_runs_nothing_since_the_last_line_exits(
    tmp_path: Path,
) -> None:
    # SKILL.md: stages live inside run_wizard and the last line stays as is, so bash has
    # parsed the call and its exit before the first stage; a stage that appends to the
    # script stands for a human editing it mid-run.
    text = TEMPLATE.read_text()
    last = text.rstrip("\n").splitlines()[-1]
    assert last.startswith("run_wizard "), last
    wizard = tmp_path / "wizard.sh"
    wizard.write_text(
        text[: text.index(MARKER)]
        + "run_wizard() {\n"
        + "  printf 'echo APPENDED-RAN\\n' >> \"$0\"\n"
        + '  say "stage done"\n'
        + "}\n"
        + last
        + "\n"
    )
    result = subprocess.run(
        ["bash", str(wizard)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert "stage done" in result.stdout, result.stdout + result.stderr
    assert "APPENDED-RAN" not in result.stdout
    assert "echo APPENDED-RAN" in wizard.read_text()
