"""browse.py's Omnigent sign-in: the token it hands the browser, and when it refreshes."""

from __future__ import annotations

import json
import runpy
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "browsing" / "scripts" / "browse.py"
ORIGIN = "https://omnigent.example:6767"


@pytest.fixture
def browse(tmp_path, monkeypatch):
    mod = runpy.run_path(str(SCRIPT))
    token = mod["omnigent_token"]
    monkeypatch.setitem(token.__globals__, "TOKENS", tmp_path / "auth_tokens.json")
    return token


def write(path: Path, token: str, expires_at: float) -> None:
    path.write_text(json.dumps({ORIGIN: {"token": token, "expires_at": expires_at}}))


def test_fresh_token_is_used_without_refresh_or_output(browse, capsys, monkeypatch):
    write(browse.__globals__["TOKENS"], "fresh", time.time() + 3600)
    monkeypatch.setattr("subprocess.run", lambda *a, **k: pytest.fail("refreshed a fresh token"))
    assert browse(ORIGIN) == "fresh"
    assert capsys.readouterr() == ("", "")


def test_expiring_token_refreshes_through_the_cli_interpreter(browse, tmp_path, monkeypatch):
    tokens = browse.__globals__["TOKENS"]
    write(tokens, "old", time.time() + 30)
    cli = tmp_path / "omnigent"
    cli.write_text("#!/opt/omnigent/bin/python\n")
    monkeypatch.setattr("shutil.which", lambda name: str(cli))

    def refresh(argv, **kwargs):
        assert argv[0] == "/opt/omnigent/bin/python" and argv[-1] == ORIGIN
        write(tokens, "new", time.time() + 3600)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("subprocess.run", refresh)
    assert browse(ORIGIN) == "new"


@pytest.mark.parametrize("which", [None, "refused"])
def test_unrefreshable_token_exits_with_advice(browse, tmp_path, monkeypatch, which):
    write(browse.__globals__["TOKENS"], "expired-7f3c9a", 0)
    cli = tmp_path / "omnigent"
    cli.write_text("#!/opt/omnigent/bin/python\n")
    monkeypatch.setattr("shutil.which", lambda name: which and str(cli))
    monkeypatch.setattr("subprocess.run", lambda *a, **k: SimpleNamespace(returncode=1))
    with pytest.raises(SystemExit, match="omnigent login") as exc:
        browse(ORIGIN)
    assert "expired-7f3c9a" not in str(exc.value)


def test_missing_login_exits(browse):
    with pytest.raises(SystemExit, match="no Omnigent login"):
        browse(ORIGIN)
