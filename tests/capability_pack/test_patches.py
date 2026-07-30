from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import yaml

from tools.capability_pack import cli
from tools.capability_pack.qualify import QualificationError, qualify


def _write_package(package: Path) -> None:
    package.mkdir()
    (package / "skills").mkdir()
    (package / "vendir.yml").write_text(
        yaml.safe_dump(
            {
                "apiVersion": "vendir.k14s.io/v1alpha1",
                "kind": "Config",
                "directories": [],
            },
            sort_keys=False,
        )
    )
    (package / "vendir.lock.yml").write_text(
        yaml.safe_dump(
            {
                "apiVersion": "vendir.k14s.io/v1alpha1",
                "kind": "LockConfig",
                "directories": [
                    {
                        "path": "skills",
                        "contents": [
                            {
                                "path": ".upstream/engineering",
                                "git": {"sha": "a" * 40},
                            }
                        ],
                    }
                ],
            },
            sort_keys=False,
        )
    )
    (package / "patches").mkdir()


def _install_noop_vendir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    vendir = bin_dir / "vendir"
    vendir.write_text("#!/bin/sh\nexit 0\n")
    vendir.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")


def _patch(path: str, before: str, after: str) -> str:
    return (
        f"diff --git a/{path} b/{path}\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        "@@ -1 +1 @@\n"
        f"-{before}\n"
        f"+{after}\n"
    )


def _tree_bytes(root: Path) -> dict[str, bytes | str]:
    snapshot: dict[str, bytes | str] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            snapshot[relative] = f"symlink:{os.readlink(path)}"
        elif path.is_dir():
            snapshot[relative] = "directory"
        else:
            snapshot[relative] = path.read_bytes()
    return snapshot


def test_patch_series_is_applied_in_declared_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Catch sorting patches instead of honoring the integration series."""
    package = tmp_path / "engineering"
    _write_package(package)
    _install_noop_vendir(tmp_path, monkeypatch)
    target = package / "value.txt"
    target.write_text("one\n")
    first = package / "patches" / "z-first.patch"
    second = package / "patches" / "a-second.patch"
    first.write_text(_patch("value.txt", "one", "two"))
    second.write_text(_patch("value.txt", "two", "three"))
    (package / "patches" / "series").write_text("patches/z-first.patch\npatches/a-second.patch\n")

    qualify(package, "update")

    assert target.read_text() == "three\n"


def test_patch_in_nested_git_worktree_changes_only_staged_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Catch git apply discovering a parent worktree instead of using the stage root."""
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init"], cwd=repository, check=True, capture_output=True)
    package = repository / "engineering"
    _write_package(package)
    _install_noop_vendir(tmp_path, monkeypatch)
    target = package / "value.txt"
    target.write_text("one\n")
    parent_target = repository / "value.txt"
    parent_target.write_text("parent\n")
    patch = package / "patches" / "change.patch"
    patch.write_text(_patch("value.txt", "one", "two"))
    (package / "patches" / "series").write_text("patches/change.patch\n")

    qualify(package, "update")

    assert target.read_text() == "two\n"
    assert parent_target.read_text() == "parent\n"


def test_rejected_patch_leaves_real_package_byte_identical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Catch applying patches in the committed package before qualification succeeds."""
    package = tmp_path / "engineering"
    _write_package(package)
    _install_noop_vendir(tmp_path, monkeypatch)
    (package / "value.txt").write_text("one\n")
    (package / "patches" / "broken.patch").write_text(_patch("value.txt", "missing", "two"))
    (package / "patches" / "series").write_text("patches/broken.patch\n")
    before = _tree_bytes(package)

    with pytest.raises(QualificationError):
        qualify(package, "update")

    assert _tree_bytes(package) == before


@pytest.mark.parametrize(
    "header_path",
    ["/tmp/escaped.txt", "../escaped.txt", "nested/../../escaped.txt"],
)
def test_unsafe_patch_header_paths_are_rejected_before_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, header_path: str
) -> None:
    """Catch a patch writing outside the staged package."""
    package = tmp_path / "engineering"
    _write_package(package)
    _install_noop_vendir(tmp_path, monkeypatch)
    patch = package / "patches" / "unsafe.patch"
    patch.write_text(
        f"diff --git a/value.txt b/value.txt\n"
        f"--- a/value.txt\n"
        f"+++ b/{header_path}\n"
        "@@ -0,0 +1 @@\n"
        "+escaped\n"
    )
    (package / "patches" / "series").write_text("patches/unsafe.patch\n")

    with pytest.raises(QualificationError, match="unsafe patch path"):
        qualify(package, "update")

    assert not (tmp_path / "escaped.txt").exists()


def test_symlink_escaping_staged_package_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Catch patches reaching outside the stage through an existing symlink."""
    package = tmp_path / "engineering"
    _write_package(package)
    _install_noop_vendir(tmp_path, monkeypatch)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "value.txt").write_text("one\n")
    (package / "linked").symlink_to(outside, target_is_directory=True)
    patch = package / "patches" / "unsafe.patch"
    patch.write_text(_patch("linked/value.txt", "one", "two"))
    (package / "patches" / "series").write_text("patches/unsafe.patch\n")

    with pytest.raises(QualificationError, match="symlink escapes"):
        qualify(package, "update")

    assert (outside / "value.txt").read_text() == "one\n"


def test_patch_failure_writes_deterministic_blocked_summary(
    package: Path, fake_vendir: Path, tmp_path: Path
) -> None:
    """Catch losing review evidence when a staged patch is rejected."""
    patch = package / "patches" / "broken.patch"
    patch.write_text(_patch("skills/alpha/SKILL.md", "# Missing", "# Patched"))
    (package / "patches" / "series").write_text("patches/broken.patch\n")
    summary = tmp_path / "blocked-summary.txt"

    with pytest.raises(QualificationError, match="patch failed"):
        qualify(package, "update", summary)

    first = summary.read_bytes()
    assert b"Previous source commit: 1111111111111111111111111111111111111111" in first
    assert b"Proposed source commit: 2222222222222222222222222222222222222222" in first
    assert b"Patch failures: patches/broken.patch" in first
    assert b"License hashes: LICENSES/mattpocock-skills/LICENSE=" in first
    assert b"Proposed version: BLOCKED" in first
    assert b"Output hashes:" not in first

    with pytest.raises(QualificationError):
        qualify(package, "update", summary)
    assert summary.read_bytes() == first


@pytest.mark.parametrize(
    ("series_entry", "failure"),
    [
        ("../escaped.patch", "unsafe patch series path: ../escaped.patch"),
        ("patches/missing.patch", "missing patch file: patches/missing.patch"),
    ],
)
def test_pre_apply_patch_failure_writes_blocked_summary_and_returns_exit_four(
    package: Path,
    fake_vendir: Path,
    tmp_path: Path,
    series_entry: str,
    failure: str,
) -> None:
    """Catch patch-manifest failures escaping the deterministic evidence boundary."""
    (package / "patches" / "series").write_text(series_entry + "\n")
    summary = tmp_path / "blocked-summary.txt"

    assert cli.main(["update", str(package), "--summary", str(summary)]) == 4

    first = summary.read_bytes()
    assert b"Proposed source commit: 2222222222222222222222222222222222222222" in first
    assert f"Patch failures: {failure}".encode() in first
    assert b"Proposed version: BLOCKED" in first

    assert cli.main(["update", str(package), "--summary", str(summary)]) == 4
    assert summary.read_bytes() == first


def test_invalid_utf8_patch_series_writes_stable_blocked_summary(
    package: Path, fake_vendir: Path, tmp_path: Path
) -> None:
    """Catch patch-series decode failures escaping the evidence boundary."""
    (package / "patches" / "series").write_bytes(b"\xff\xfe")
    summary = tmp_path / "blocked-summary.txt"

    assert cli.main(["update", str(package), "--summary", str(summary)]) == 4

    first = summary.read_bytes()
    assert b"Proposed source commit: 2222222222222222222222222222222222222222" in first
    assert b"Patch failures: unreadable patch series: patches/series" in first
    assert b"Proposed version: BLOCKED" in first

    assert cli.main(["update", str(package), "--summary", str(summary)]) == 4
    assert summary.read_bytes() == first
