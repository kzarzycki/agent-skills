from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from tools.capability_pack.qualify import QualificationError, qualify


def _write_package(package: Path) -> None:
    package.mkdir()
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
