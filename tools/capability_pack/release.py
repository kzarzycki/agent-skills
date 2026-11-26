"""Cut a release of every package with pending `changelog.d/` entries, and check a tree is exactly that cut.

`cut_release` folds each package's entries into its `CHANGELOG.md` and sets its version; it writes files only, and
committing, pushing, tagging and the PR are the caller's (the release workflow, or a person). `verify_release` reruns
that fold on a base tree and requires the head tree to be identical, which is what lets a release PR skip the
verifier: nothing in it is a hand edit (#1861).
"""

from __future__ import annotations

import datetime
import json
import re
import shutil
import subprocess
import tarfile
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from tools.capability_pack.qualify import ConfigurationError, _next_version, _semver

MAGNITUDES = ("patch", "minor")
OWNER_REPO = "kzarzycki/agent-skills"
_HEADING = re.compile(r"^## ", re.MULTILINE)
_APM_VERSION = re.compile(r"^(version:[ \t]*['\"]?)([^'\"\s#]+)", re.MULTILINE)
_PLUGIN_VERSION = re.compile(r'("version"[ \t]*:[ \t]*")([^"]*)(")')


@dataclass(frozen=True)
class Release:
    package: str
    version: str
    section: str  # the CHANGELOG section as it reads after the fold
    entries: tuple[str, ...]  # the issue numbers folded, in order


def packages(root: Path) -> list[Path]:
    """The released packages: top-level directories with `changelog.d/` and `apm.yml`. A Claude Code plugin manifest is optional: an APM-only
    package (`engineering-hooks`) has none, and its `apm.yml` alone carries the version."""
    return sorted(
        path
        for path in root.iterdir()
        if (path / "changelog.d").is_dir() and (path / "apm.yml").is_file()
    )


def _released(package: Path) -> bool:
    """Whether a top-level directory is a released package: it has an `apm.yml` and a `changelog.d/`."""
    return (package / "apm.yml").is_file() and (package / "changelog.d").is_dir()


def released_versions(repository: Path) -> dict[str, str]:
    """The newest `<package>-vX.Y.Z` tag of each package in `repository`'s local tags."""
    result = subprocess.run(
        ["git", "tag", "--list", "*-v*"],
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    if result.returncode != 0:
        raise ConfigurationError(f"git tag --list failed: {result.stderr.strip()}")
    newest: dict[str, tuple[int, int, int]] = {}
    for tag in result.stdout.split():
        match = re.fullmatch(r"(.+)-v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", tag)
        if match:
            version = tuple(int(part) for part in match.groups()[1:])
            newest[match.group(1)] = max(newest.get(match.group(1), version), version)  # type: ignore[arg-type]
    return {name: ".".join(map(str, version)) for name, version in newest.items()}


def _entries(package: Path) -> list[Path]:
    files = [path for path in (package / "changelog.d").glob("*.md") if path.name != "README.md"]
    named = sorted(path.name for path in files if not path.stem.isdigit())
    if named:
        raise ConfigurationError(
            f"{package.name}/changelog.d entries must be named <issue>.md: {', '.join(named)}"
        )
    return sorted(files, key=lambda path: int(path.stem))


def _current_version(package: Path) -> str:
    match = _APM_VERSION.search((package / "apm.yml").read_text())
    manifest = package / ".claude-plugin" / "plugin.json"
    plugin = json.loads(manifest.read_text()) if manifest.is_file() else None
    if not match or (plugin is not None and match.group(2) != plugin.get("version")):
        raise ConfigurationError(f"{package.name}: apm.yml and plugin.json versions disagree")
    _semver(match.group(2))
    return match.group(2)


def next_version(current: str, released: str | None, magnitude: str) -> str:
    """The release's version: the last tag bumped by `magnitude`, or apm.yml's own when it is already further (an
    `update` that bumped it), or apm.yml's own when the package was never tagged."""
    if magnitude not in MAGNITUDES:
        raise ConfigurationError(f"magnitude must be one of {', '.join(MAGNITUDES)}: {magnitude}")
    if released is None:
        return current
    proposed = _next_version(released, magnitude)
    return current if _semver(current) > _semver(proposed) else proposed


def _fold(changelog: str, version: str, bullets: str, date: str) -> tuple[str, str]:
    """The new CHANGELOG text and the version's section in it: the entries go under `## <version> - <date>` after
    `## Unreleased`, or extend an existing `## <version>` heading."""
    existing = re.search(rf"^## {re.escape(version)}(?: - .*)?$", changelog, re.MULTILINE)
    if existing:
        following = _HEADING.search(changelog, existing.end())
        end = following.start() if following else len(changelog)
        section = f"{changelog[existing.start() : end].rstrip()}\n{bullets}\n"
        start = existing.start()
    else:
        unreleased = re.search(r"^## Unreleased$", changelog, re.MULTILINE)
        following = _HEADING.search(changelog, unreleased.end() if unreleased else 0)
        start = end = following.start() if following else len(changelog)
        section = f"## {version} - {date}\n\n{bullets}\n"
    before = changelog[:start].rstrip("\n")
    after = changelog[end:].lstrip("\n")
    return f"{before}\n\n{section}" + (f"\n{after}" if after else ""), section


def _set_ref(text: str, package: str, old: str, new: str) -> str:
    """Point a `ref: ^<old>` that follows this package's `git:` line at `^<new>`."""
    pattern = re.compile(
        rf"(git:[ \t]*{re.escape(OWNER_REPO)}/{re.escape(package)}[ \t]*\n[ \t]*(?:-[ \t]+)?ref:[ \t]*)"
        rf"\^{re.escape(old)}\b"
    )
    return pattern.sub(rf"\g<1>^{new}", text)


def write_version(package: Path, version: str) -> None:
    """Set `version` where a release sets it, changing only those lines: both manifests, and the `ref:` pins of the
    package in its README and consumer fixture."""
    current = _current_version(package)
    apm = package / "apm.yml"
    apm.write_text(_APM_VERSION.sub(rf"\g<1>{version}", apm.read_text(), count=1))
    plugin = package / ".claude-plugin" / "plugin.json"
    if plugin.is_file():
        plugin.write_text(_PLUGIN_VERSION.sub(rf"\g<1>{version}\g<3>", plugin.read_text(), count=1))
    for path in (package / "README.md", package / "tests" / "consumer" / "apm.yml"):
        if path.is_file():
            text = path.read_text()
            changed = _set_ref(text, package.name, current, version)
            if changed != text:
                path.write_text(changed)


def cut_package(package: Path, version: str, date: str, *, dry_run: bool = False) -> Release | None:
    entries = _entries(package)
    if not entries:
        return None
    bullets = "\n".join(path.read_text().strip() for path in entries)
    changelog = package / "CHANGELOG.md"
    text, section = _fold(changelog.read_text(), version, bullets, date)
    if not dry_run:
        write_version(package, version)
        changelog.write_text(text)
        for path in entries:
            path.unlink()
    return Release(package.name, version, section, tuple(path.stem for path in entries))


def cut_release(
    root: Path,
    *,
    magnitude: str = "patch",
    released: Mapping[str, str] | None = None,
    versions: Mapping[str, str] | None = None,
    dates: Mapping[str, str] | None = None,
    today: datetime.date | None = None,
    dry_run: bool = False,
) -> list[Release]:
    """Cut every package under `root` with pending entries. `released` maps a package to its newest tagged version
    (default: `root`'s git tags); `versions` and `dates` pin a package's version or heading date (the gate's rerun)."""
    root = root.resolve()
    released = released_versions(root) if released is None else released
    date = (today or datetime.datetime.now(datetime.UTC).date()).isoformat()
    cut = []
    for package in packages(root):
        if not _entries(package):
            continue
        version = (versions or {}).get(package.name) or next_version(
            _current_version(package), released.get(package.name), magnitude
        )
        if released.get(package.name) and _semver(version) <= _semver(released[package.name]):
            raise ConfigurationError(f"{package.name}-v{version} is not after the last release")
        release = cut_package(
            package, version, (dates or {}).get(package.name, date), dry_run=dry_run
        )
        if release:
            cut.append(release)
    if not cut:
        raise ConfigurationError("nothing to release: no package's changelog.d holds an entry")
    return cut


def _export(repository: Path, commit: str, destination: Path) -> None:
    """Write `commit`'s tracked tree to `destination` (no checkout, no write under .git)."""
    with tempfile.TemporaryFile() as archive:
        subprocess.run(
            ["git", "archive", "--format=tar", commit],
            cwd=repository,
            check=True,
            stdout=archive,
            timeout=300,
        )
        archive.seek(0)
        with tarfile.open(fileobj=archive) as tar:
            tar.extractall(destination, filter="tar")


def _tree(root: Path) -> dict[str, tuple[bytes, bool]]:
    return {
        path.relative_to(root).as_posix(): (
            path.read_bytes() if not path.is_symlink() else str(path.readlink()).encode(),
            bool(path.lstat().st_mode & 0o111),
        )
        for path in root.rglob("*")
        if path.is_file() or path.is_symlink()
    }


def _head_dates(head: Path, releases: Mapping[str, str]) -> dict[str, str]:
    dates = {}
    for name, version in releases.items():
        changelog = head / name / "CHANGELOG.md"
        text = changelog.read_text() if changelog.is_file() else ""
        match = re.search(
            rf"^## {re.escape(version)} - (\d{{4}}-\d{{2}}-\d{{2}})$", text, re.MULTILINE
        )
        if match:
            datetime.date.fromisoformat(match.group(1))
            dates[name] = match.group(1)
    return dates


def verify_release(
    repository: Path, base: str, head: str = "HEAD", released: Mapping[str, str] | None = None
) -> list[Release]:
    """Refuse unless `head`'s tree is exactly the release cut of `base` (their merge base): the same packages, each
    at the last tag's next patch or minor (or apm.yml's further version), each heading dated as `head` dates it, and
    no other change. Returns the releases it reproduced."""
    repository = repository.resolve()
    released = released_versions(repository) if released is None else released
    merge_base = subprocess.run(
        ["git", "merge-base", base, head],
        cwd=repository,
        check=True,
        text=True,
        capture_output=True,
        timeout=60,
    ).stdout.strip()
    work = Path(tempfile.mkdtemp(prefix="release-verify-"))
    try:
        base_tree, head_tree = work / "base", work / "head"
        _export(repository, merge_base, base_tree)
        _export(repository, head, head_tree)
        versions = {
            package.name: _current_version(head_tree / package.name)
            for package in packages(base_tree)
            if (head_tree / package.name / "apm.yml").is_file()
        }
        dates = _head_dates(head_tree, versions)
        expected = _tree(head_tree)
        failures = []
        for magnitude in MAGNITUDES:
            attempt = work / magnitude
            shutil.copytree(base_tree, attempt, symlinks=True)
            pinned = {}
            for package in packages(attempt):
                wanted = next_version(
                    _current_version(package), released.get(package.name), magnitude
                )
                if versions.get(package.name) == wanted:
                    pinned[package.name] = wanted
            releases = cut_release(
                attempt, magnitude=magnitude, released=released, versions=pinned, dates=dates
            )
            actual = _tree(attempt)
            if actual == expected:
                return releases
            differing = sorted(
                path
                for path in expected.keys() | actual.keys()
                if expected.get(path) != actual.get(path)
            )
            failures.append(f"{magnitude}: {', '.join(differing[:20])}")
        raise ConfigurationError(
            f"{head} is not the release cut of {merge_base}; files that differ from the cut: "
            + "; ".join(failures)
        )
    finally:
        shutil.rmtree(work, ignore_errors=True)


def release_tags(repository: Path, commit: str = "HEAD") -> list[str]:
    """`<package>-v<version>` for each package whose plugin manifest, `apm.yml` or `CHANGELOG.md` `commit` changes, at
    the version it sets. A package with no plugin manifest (`engineering-hooks`) and one on its first release, whose
    version no release moves, show only in the `CHANGELOG.md` a cut always rewrites."""
    repository = repository.resolve()
    changed = subprocess.run(
        ["git", "diff-tree", "--root", "--no-commit-id", "--name-only", "-r", commit],
        cwd=repository,
        check=True,
        text=True,
        capture_output=True,
        timeout=60,
    ).stdout.split()
    tags = []
    for path in changed:
        manifest = re.fullmatch(
            r"([^/]+)/(?:\.claude-plugin/plugin\.json|apm\.yml|CHANGELOG\.md)", path
        )
        if manifest and _released(repository / manifest.group(1)):
            tags.append(f"{manifest.group(1)}-v{_current_version(repository / manifest.group(1))}")
    return sorted(set(tags))
