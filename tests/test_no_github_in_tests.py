"""No test reaches GitHub through the real gh (#2035): the root conftest puts a refusing `gh` first on PATH, in a temp
folder its run removes, one trap however many xdist workers run; a test's own fake still goes ahead of it, and a
`live_agent` test or a run with GH_REAL_IN_TESTS=1 keeps the real one."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from tools.gh_trap import NO_GH, install_trap, without_trap


def test_gh_in_a_test_is_the_trap() -> None:
    done = subprocess.run(["gh", "api", "user"], capture_output=True, text=True, check=False)
    assert (done.returncode, done.stdout, done.stderr.strip()) == (1, "", NO_GH)


def test_path_holds_one_trap_and_none_in_the_checkout() -> None:
    """An xdist worker reuses its controller's trap; the folder is a temp one, never under the checkout."""
    trap = os.environ["GH_NO_GITHUB_TRAP"]
    assert os.environ["PATH"].split(os.pathsep).count(trap) == 1
    assert not [
        entry
        for entry in os.environ["PATH"].split(os.pathsep)
        if "no-gh-" in entry and entry != trap
    ]
    assert not Path(trap).resolve().is_relative_to(Path(__file__).resolve().parents[1])


def test_a_tests_own_fake_goes_ahead_of_the_trap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "gh").write_text("#!/bin/sh\necho fake\n")
    (tmp_path / "gh").chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    assert subprocess.run(["gh"], capture_output=True, text=True, check=False).stdout == "fake\n"


def test_install_trap_honours_the_opt_out_and_reuses_a_trap_on_path(tmp_path: Path) -> None:
    assert install_trap({"PATH": "/usr/bin", "GH_REAL_IN_TESTS": "1"}, str(tmp_path)) is None
    env = {"PATH": "/usr/bin"}
    made = install_trap(env, str(tmp_path))
    assert made is not None and env["PATH"] == f"{made}{os.pathsep}/usr/bin"
    assert env["GH_NO_GITHUB_TRAP"] == str(made) and (made / "gh").is_file()
    assert (
        install_trap(env, str(tmp_path)) is None
    )  # a worker under its controller: the same trap, once
    assert env["PATH"].split(os.pathsep).count(str(made)) == 1
    stale = {
        "PATH": "/usr/bin",
        "GH_NO_GITHUB_TRAP": str(tmp_path / "gone"),
    }  # named, but not on PATH: a new one
    assert install_trap(stale, str(tmp_path)) is not None


def test_without_trap_drops_every_copy() -> None:
    assert without_trap(os.pathsep.join(["/t", "/a", "/t", "/b"]), "/t") == os.pathsep.join(
        ["/a", "/b"]
    )


@pytest.mark.live_agent
def test_a_live_agent_test_has_no_trap_on_path() -> None:
    trap = os.environ["GH_NO_GITHUB_TRAP"]
    assert trap not in os.environ["PATH"].split(os.pathsep)
    assert "no-gh-" not in os.environ["PATH"]
