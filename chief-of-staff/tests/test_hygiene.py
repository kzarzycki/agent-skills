from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1] / "skills" / "chief-of-staff" / "scripts" / "hygiene.py"
)
TODAY = "2026-11-25"


def run(home: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPT), "--home", str(home), "--today", TODAY, *args],
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": os.environ["PATH"], "GIT_CONFIG_GLOBAL": "/dev/null"},
    )


def scan(home: Path, *args: str) -> tuple[int, dict]:
    if "--installed-cmd" not in args:  # a host is reached: it has nothing installed
        empty = home / "empty-installed.py"
        empty.write_text("print('{}')\n")
        repo = home / "empty-pack.git"
        if not repo.exists():
            repo.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        args += ("--pack-repo", str(repo), "--installed-cmd", f"{sys.executable} {empty}")
    r = run(home, "--json", *args)
    assert r.returncode in (0, 1), r.stderr
    return r.returncode, json.loads(r.stdout)


def old(path: Path, text: str = "x", days: int = 30) -> Path:
    path.write_text(text)
    ts = (date(2026, 11, 25) - date(1970, 1, 1)).days * 86400 - days * 86400
    os.utime(path, (ts, ts))
    return path


@pytest.fixture
def home(tmp_path):
    (tmp_path / "tmp" / "loop").mkdir(parents=True)
    (tmp_path / "tmp" / "loop" / "chief-of-staff.md").write_text("# Board\n")
    return tmp_path


def values(home: Path, text: str) -> None:
    (home / "cos-values.yml").write_text(text)


def test_clean_setup_exits_zero_and_reports_none(home):
    code, rep = scan(home)
    assert code == 0
    assert rep["board"] == rep["retention"] == rep["decisions"] == rep["not reached"] == []


def test_board_over_4kb_is_reported_and_never_rewritten(home):
    board = home / "tmp" / "loop" / "chief-of-staff.md"
    board.write_text("x" * 5000)
    before = (board.read_bytes(), board.stat().st_mtime_ns)
    code, rep = scan(home)
    assert code == 1
    assert "5000" not in rep["board"][0] and "4 KB" in rep["board"][0]
    assert (board.read_bytes(), board.stat().st_mtime_ns) == before
    assert not list(board.parent.glob("*archive*"))


def test_old_report_of_a_reaped_lead_is_archived(home):
    rep_dir = home / "tmp" / "loop"
    gone = old(rep_dir / "lead-1-report.md", "done")
    fresh = rep_dir / "lead-2-report.md"
    fresh.write_text("new")
    code, _ = scan(home)
    assert code == 1
    assert not gone.exists() and (rep_dir / "archive" / "lead-1-report.md").read_text() == "done"
    assert fresh.exists()


def test_report_a_registry_names_is_never_archived(home):
    rep_dir = home / "tmp" / "loop"
    live = old(rep_dir / "lead-live-report.md", "running")
    (rep_dir / "leads.registry").write_text(f"session-1={live}\tbrief.md\tfollow\n")
    _, rep = scan(home)
    assert live.exists() and not (rep_dir / "archive").exists()
    assert rep["retention"] == []


def test_report_a_managers_registry_or_state_names_is_never_archived(home):
    rep_dir = home / "tmp" / "loop"
    a = old(rep_dir / "managed-report.md")
    b = old(rep_dir / "state-report.md")
    (rep_dir / "repo-a-leads.registry").write_text(f"session-2={a.name}\n")
    (rep_dir / "leads.state.json").write_text(json.dumps({"session-3": {"report": b.name}}))
    values(home, "managers:\n  - {scope: [repo-a], registry: repo-a-leads.registry, board: b.md}\n")
    scan(home)
    assert a.exists() and b.exists()


def test_unreadable_registry_archives_nothing(home):
    rep_dir = home / "tmp" / "loop"
    f = old(rep_dir / "lead-1-report.md")
    reg = rep_dir / "leads.registry"
    reg.write_text("session-1=other.md\n")
    reg.chmod(0)
    if os.access(reg, os.R_OK):  # running as root: permissions do not apply
        reg.unlink()
        reg.mkdir()  # a directory in the registry's place cannot be read as a file
    _, rep = scan(home)
    assert f.exists() and "nothing archived" in rep["retention"][0]


def test_no_archive_reports_and_moves_nothing(home):
    f = old(home / "tmp" / "loop" / "lead-1-report.md")
    _, rep = scan(home, "--no-archive")
    assert f.exists() and "would archive" in rep["retention"][0]


def test_decisions_past_their_end_date_are_named_and_the_file_is_unchanged(home):
    text = (
        "budget:\n  weekly_limit: 100\n  until: 2026-01-31\n"
        "parked:\n  - {item: cleanup, until: 2026-06-01}\n  - {item: later, until: 2030-01-01}\n"
        "  - {item: open-ended}\n"
        "models:\n  tiers:\n    lead: model-a\n    worker: {model: model-b, until: 2026-11-01}\n"
    )
    values(home, text)
    code, rep = scan(home)
    joined = "\n".join(rep["decisions"])
    assert code == 1
    assert "budget: ended 2026-01-31" in joined
    assert "cleanup" in joined and "later" not in joined
    assert "open-ended" in joined and "no end date" in joined
    assert "models.tiers.worker: ended 2026-11-01" in joined
    assert "models.tiers.lead" not in joined
    assert (home / "cos-values.yml").read_text() == text


def make_pack_repo(root: Path, tags: list[str]) -> Path:
    repo = root / "pack.git"
    repo.mkdir()
    env = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null"}
    for cmd in (
        ["git", "init", "-q"],
        [
            "git",
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@e.invalid",
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "x",
        ],
        *(["git", "tag", t] for t in tags),
    ):
        subprocess.run(cmd, cwd=repo, check=True, env=env, capture_output=True)
    return repo


def installer(root: Path, versions: dict[str, dict]) -> str:
    """A command printing each host's installed versions; host `down` fails."""
    f = root / "installed.py"
    f.write_text(
        "import json, sys\n"
        f"v = {versions!r}\n"
        "h = sys.argv[1]\n"
        "sys.exit(3) if h not in v else print(json.dumps(v[h]))\n"
    )
    return f"{sys.executable} {f} {{host}}"


def test_pack_lag_names_any_package_behind_its_latest_release(home, tmp_path):
    pack = make_pack_repo(tmp_path, ["engineering-v0.2.0", "engineering-v0.10.0", "loop-v1.0.0"])
    values(home, "hosts:\n  table:\n    repo-a: [host-1]\n")
    cmd = installer(tmp_path, {"host-1": {"engineering": "0.2.0", "loop": "1.0.0", "other": "1"}})
    code, rep = scan(home, "--pack-repo", str(pack), "--installed-cmd", cmd)
    assert code == 1
    assert rep["pack lag"] == ["host-1: engineering 0.2.0 is behind the release 0.10.0"]
    assert rep["not reached"] == []


def test_a_host_the_scan_did_not_reach_is_named(home, tmp_path):
    pack = make_pack_repo(tmp_path, ["engineering-v1.0.0"])
    values(home, "hosts:\n  table:\n    repo-a: [host-1, down]\n")
    cmd = installer(tmp_path, {"host-1": {"engineering": "1.0.0"}})
    code, rep = scan(home, "--pack-repo", str(pack), "--installed-cmd", cmd)
    assert code == 1  # a skipped host never looks like a clean one
    assert rep["pack lag"] == []
    assert len(rep["not reached"]) == 1 and rep["not reached"][0].startswith("down ")


def test_without_an_installed_command_every_host_is_not_reached(home):
    values(home, "hosts:\n  table:\n    repo-a: [host-1, host-2]\n")
    r = run(home, "--json")
    code, rep = r.returncode, json.loads(r.stdout)
    assert code == 1
    assert [h.split()[0] for h in rep["not reached"]] == ["host-1", "host-2"]


RULE = "A lead never merges its own change without the proof the gate asks for on the forge."


def test_setup_file_restating_a_pack_rule_is_reported(home, tmp_path):
    pack = tmp_path / "pack"
    (pack / "plug" / "skills" / "loop-skill").mkdir(parents=True)
    (pack / "plug" / "skills" / "loop-skill" / "SKILL.md").write_text(
        f"---\nname: loop-skill\n---\n\n# T\n\n{RULE} Short line.\n"
    )
    co = tmp_path / "checkouts"
    (co / "repo-a" / "docs" / "agents").mkdir(parents=True)
    (co / "repo-a" / "docs" / "agents" / "loop.md").write_text(f"- **{RULE.lower()}**\n")
    (co / "repo-a" / "CLAUDE.md").write_text("Our own rule: ship on Fridays.\n")
    values(home, "hygiene:\n  repos: [owner-a/repo-a, owner-a/repo-b]\n")
    code, rep = scan(home, "--pack", str(pack), "--checkouts", str(co))
    assert code == 1
    assert len(rep["restate"]) == 1
    assert "docs/agents/loop.md restates the loop-skill skill" in rep["restate"][0]
    assert [r.split()[0] for r in rep["not reached"]] == ["owner-a/repo-b"]


def test_the_values_file_is_the_only_source_of_settings(home):
    values(home, "hygiene:\n  board_max_kb: 100\n")
    r = run(home)
    assert r.returncode == 2 and "board_max_kb" in r.stderr
