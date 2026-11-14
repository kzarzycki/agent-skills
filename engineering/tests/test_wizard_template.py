"""The wizard template's library: .env writes that read back and parse whole, and prompts that end at EOF."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
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
    library: Path, cwd: Path, script: str, stdin: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", f'source "$1"\n{script}', "wizard", str(library)],
        cwd=cwd,
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
