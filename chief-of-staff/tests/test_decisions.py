from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1] / "skills" / "chief-of-staff" / "scripts" / "decisions.py"
)


def run(home: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPT), "--home", str(home), *args],
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": "/usr/bin:/bin"},
    )


def log(home, n=1, **kw):
    a = {"what": f"decided {n}", "why": "reason", "undo": f"revert {n}", **kw}
    args = [x for k, v in a.items() for x in (f"--{k}", v)]
    return run(home, "--now", f"2026-11-25T0{n}:00Z", "log", *args)


@pytest.fixture
def home(tmp_path):
    (tmp_path / "tmp" / "loop").mkdir(parents=True)
    (tmp_path / "tmp" / "loop" / "chief-of-staff.md").write_text(
        "# Board\n\n## Needs the owner\n- Approve spec 12\n  - detail\n- Pick a date\n\n## Closed\n- x\n"
    )
    return tmp_path


def test_log_appends_what_why_and_undo(home):
    assert log(home).returncode == 0
    text = (home / "tmp" / "loop" / "decisions.md").read_text()
    assert "## 2026-11-25T01:00Z decided 1" in text
    assert "- Undo: revert 1" in text and "- Why: reason" in text


@pytest.mark.parametrize("missing", ["undo", "why", "what"])
def test_entry_without_undo_why_or_what_is_refused(home, missing):
    r = log(home, **{missing: "  "})
    assert r.returncode == 1 and f"--{missing}" in r.stderr
    assert not (home / "tmp" / "loop" / "decisions.md").exists()


def test_digest_lists_entries_with_undo_and_the_boards_asks(home):
    log(home, 1, by="cos", ref="https://example.test/1")
    log(home, 2)
    out = run(home, "digest").stdout
    assert "- Approve spec 12" in out and "- Pick a date" in out and "detail" not in out
    assert "decided 1" in out and "Undo: revert 1" in out and "Undo: revert 2" in out
    assert "https://example.test/1" in out
    assert "Not sent" in out


def test_digest_flags_a_hand_edited_entry_with_no_undo(home):
    (home / "tmp" / "loop" / "decisions.md").write_text("## 2026-11-25T01:00Z bare\n- Why: x\n")
    assert "NO UNDO LINE" in run(home, "digest").stdout


def test_digest_reads_cos_session_and_cos_line_from_values(home):
    (home / "cos-values.yml").write_text(
        "cos_session: sess-1\ndecisions:\n  cos_line: Chief of staff, sess-1\n"
    )
    out = run(home, "digest").stdout
    assert "Chief of staff, sess-1" in out and "Reply in session sess-1." in out


def test_decisions_file_comes_from_the_values(home):
    (home / "cos-values.yml").write_text("decisions:\n  file: other.md\n")
    log(home)
    assert (home / "tmp" / "loop" / "other.md").exists()


def test_sent_marks_the_log_and_the_next_digest_skips_what_went_out(home):
    log(home, 1)
    assert run(home, "--now", "2026-11-25T07:00Z", "sent", "--via", "chat").returncode == 0
    log(home, 2)
    out = run(home, "digest").stdout
    assert "decided 2" in out and "decided 1" not in out and "Since the digest sent" in out
    assert "decided 1" in run(home, "digest", "--all").stdout


def test_sent_needs_a_log_and_a_way_it_was_sent(home):
    assert run(home, "sent", "--via", "chat").returncode == 1
    log(home)
    assert run(home, "sent", "--via", " ").returncode == 1


def test_digest_changes_nothing_and_the_script_cannot_send():
    tree = ast.parse(SCRIPT.read_text())
    imported = {
        a.name.split(".")[0]
        for n in ast.walk(tree)
        if isinstance(n, ast.Import | ast.ImportFrom)
        for a in (n.names if isinstance(n, ast.Import) else [ast.alias(n.module or "")])
    }
    assert not imported & {"socket", "smtplib", "subprocess", "urllib", "http", "requests"}


def test_digest_writes_nothing(home):
    log(home)
    p = home / "tmp" / "loop" / "decisions.md"
    before = p.read_text()
    run(home, "digest")
    assert p.read_text() == before
