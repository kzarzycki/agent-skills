"""Two PRs that each add an Unreleased entry merge without a conflict and keep both (#244)."""

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = "engineering/CHANGELOG.md"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def add_entry(repo: Path, entry: str) -> None:
    log = repo / LOG
    log.write_text(log.read_text().replace("## Unreleased\n\n", f"## Unreleased\n\n{entry}", 1))
    git(repo, "commit", "-qam", entry)


def test_two_unreleased_entries_merge_cleanly(tmp_path: Path) -> None:
    git(tmp_path, "init", "-q", "-b", "main")
    shutil.copy(ROOT / ".gitattributes", tmp_path)
    (tmp_path / LOG).parent.mkdir()
    (tmp_path / LOG).write_text("# Changelog\n\n## Unreleased\n\n- Old entry.\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "base")
    git(tmp_path, "switch", "-qc", "a")
    add_entry(tmp_path, "- Entry A,\n  over two lines.\n")
    git(tmp_path, "switch", "-qc", "b", "main")
    add_entry(tmp_path, "- Entry B.\n")
    git(tmp_path, "merge", "-q", "--no-edit", "a")  # check=True: a conflict exits 1
    log = (tmp_path / LOG).read_text()
    assert "<<<<<<<" not in log
    for entry in ("- Entry A,\n  over two lines.\n", "- Entry B.\n", "- Old entry.\n"):
        assert log.count(entry) == 1, log
