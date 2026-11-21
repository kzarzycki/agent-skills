"""Prepare a release tree: fold `changelog.d/` into `CHANGELOG.md` and set the version.

It writes files only; committing, pushing, tagging and the PR are the caller's.
"""

from __future__ import annotations

import datetime
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import yaml

from tools.capability_pack.qualify import (
    ConfigurationError,
    _mapping,
    _next_version,
    _semver,
    write_package_version,
)

_HEADING = re.compile(r"^## ", re.MULTILINE)


@dataclass(frozen=True)
class Release:
    version: str
    section: str  # the CHANGELOG section as it reads after the fold
    entries: tuple[Path, ...]


def _tagged(package: Path, version: str) -> bool:
    tag = f"{package.name}-v{version}"
    result = subprocess.run(
        ["git", "tag", "--list", tag],
        cwd=package,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if result.returncode != 0:
        raise ConfigurationError(f"git tag --list failed: {result.stderr.strip()}")
    return tag in result.stdout.split()


def release_version(package: Path, requested: str | None = None) -> str:
    """`requested`, else apm.yml's version, or the next patch when that one is already tagged."""
    if requested is not None:
        _semver(requested)
        if _tagged(package, requested):
            raise ConfigurationError(f"{package.name}-v{requested} is already tagged")
        return requested
    apm = _mapping(yaml.safe_load((package / "apm.yml").read_text()), "apm.yml")
    current = str(apm.get("version"))
    _semver(current)
    return _next_version(current, "patch") if _tagged(package, current) else current


def _entries(package: Path) -> tuple[Path, ...]:
    folder = package / "changelog.d"
    files = [path for path in folder.glob("*.md") if path.name != "README.md"]
    named = [path for path in files if not path.stem.isdigit()]
    if named:
        names = ", ".join(sorted(path.name for path in named))
        raise ConfigurationError(f"changelog.d entries must be named <issue>.md: {names}")
    if not files:
        raise ConfigurationError(f"nothing to release: {folder} holds no entries")
    return tuple(sorted(files, key=lambda path: int(path.stem)))


def _fold(changelog: str, version: str, bullets: str, date: str) -> tuple[str, str]:
    """Return the new CHANGELOG text and the version's section in it."""
    existing = re.search(rf"^## {re.escape(version)}(?: - .*)?$", changelog, re.MULTILINE)
    if existing:
        # The routine's intake may already have written this version's entry: extend it.
        following = _HEADING.search(changelog, existing.end())
        end = following.start() if following else len(changelog)
        body = changelog[existing.start() : end].rstrip("\n")
        section = f"{body}\n{bullets}\n"
        start = existing.start()
    else:
        unreleased = re.search(r"^## Unreleased$", changelog, re.MULTILINE)
        following = _HEADING.search(changelog, unreleased.end() if unreleased else 0)
        start = end = following.start() if following else len(changelog)
        section = f"## {version} - {date}\n\n{bullets}\n"
    before = changelog[:start].rstrip("\n")
    after = changelog[end:].lstrip("\n")
    text = f"{before}\n\n{section}" + (f"\n{after}" if after else "")
    return text, section


def cut_release(
    package_root: Path,
    *,
    version: str | None = None,
    dry_run: bool = False,
    today: datetime.date | None = None,
) -> Release:
    package = package_root.resolve()
    entries = _entries(package)
    chosen = release_version(package, version)
    bullets = "\n".join(path.read_text().strip() for path in entries)
    date = (today or datetime.datetime.now(datetime.UTC).date()).isoformat()
    changelog_path = package / "CHANGELOG.md"
    text, section = _fold(changelog_path.read_text(), chosen, bullets, date)
    if not dry_run:
        write_package_version(package, chosen)
        changelog_path.write_text(text)
        for path in entries:
            path.unlink()
    return Release(chosen, section, entries)
