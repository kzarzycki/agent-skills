"""No test reaches GitHub through the real gh (#2035): the root conftest puts a refusing `gh` first on PATH, which a
test's own fake still goes ahead of, and a `live_agent` test keeps the real one."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from conftest import NO_GH


def test_gh_in_a_test_is_the_trap() -> None:
    done = subprocess.run(["gh", "api", "user"], capture_output=True, text=True, check=False)
    assert (done.returncode, done.stdout, done.stderr.strip()) == (1, "", NO_GH)


def test_a_tests_own_fake_goes_ahead_of_the_trap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "gh").write_text("#!/bin/sh\necho fake\n")
    (tmp_path / "gh").chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    assert subprocess.run(["gh"], capture_output=True, text=True, check=False).stdout == "fake\n"


@pytest.mark.live_agent
def test_a_live_agent_test_has_no_trap_on_path() -> None:
    trap = os.environ["GH_NO_GITHUB_TRAP"]
    assert trap not in os.environ["PATH"].split(os.pathsep)
