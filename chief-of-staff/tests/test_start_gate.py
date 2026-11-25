from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1] / "skills" / "chief-of-staff" / "scripts" / "start_gate.py"
)


def gate(home: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPT), "--home", str(home), "check", *args],
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": "/usr/bin:/bin"},
    )


@pytest.fixture
def home(tmp_path):
    def write(text: str) -> Path:
        (tmp_path / "cos-values.yml").write_text(text)
        return tmp_path

    return write


def test_no_table_allows_any_host(tmp_path):
    r = gate(tmp_path, "--repo", "a/b", "--host", "h1")
    assert r.returncode == 0, r.stdout + r.stderr


def test_owner_requested_only_host_refused_unless_asked(home):
    h = home("hosts:\n  owner_requested_only: [h2]\n")
    r = gate(h, "--repo", "a/b", "--host", "h2")
    assert r.returncode == 1 and "owner asked for" in r.stdout
    assert gate(h, "--repo", "a/b", "--host", "h2", "--owner-requested").returncode == 0
    assert gate(h, "--repo", "a/b", "--host", "h1").returncode == 0


def test_table_refuses_a_host_it_does_not_list(home):
    h = home("hosts:\n  table:\n    a/b: [h1]\n    c/d: h2\n")
    assert gate(h, "--repo", "a/b", "--host", "h1").returncode == 0
    assert gate(h, "--repo", "c/d", "--host", "h2").returncode == 0
    r = gate(h, "--repo", "a/b", "--host", "h2")
    assert r.returncode == 1 and "not allowed for a/b" in r.stdout


def test_table_refuses_an_unlisted_repo(home):
    h = home("hosts:\n  table:\n    a/b: [h1]\n")
    r = gate(h, "--repo", "x/y", "--host", "h1")
    assert r.returncode == 1 and "not in hosts.table" in r.stdout


def test_managed_repo_needs_its_managers_registry(home):
    h = home("managers:\n  - scope: [a/b]\n    registry: pm.registry\n    board: pm.md\n")
    r = gate(h, "--repo", "a/b", "--host", "h1")
    assert r.returncode == 1 and "pm.registry" in r.stdout
    assert gate(h, "--repo", "a/b", "--host", "h1", "--registry", "other").returncode == 1
    assert gate(h, "--repo", "a/b", "--host", "h1", "--registry", "pm.registry").returncode == 0
    assert gate(h, "--repo", "x/y", "--host", "h1").returncode == 0


def test_reasons_add_up(home):
    h = home(
        "hosts:\n  owner_requested_only: [h2]\n  table:\n    a/b: [h1]\n"
        "managers:\n  - scope: [a/b]\n    registry: r\n    board: b\n"
    )
    r = gate(h, "--repo", "a/b", "--host", "h2")
    assert r.stdout.count("REFUSED") == 3


def test_bad_values_file_exits_2(home):
    r = gate(home("hosts:\n  tabel: {}\n"), "--repo", "a/b", "--host", "h1")
    assert r.returncode == 2 and "hosts.tabel" in r.stderr
