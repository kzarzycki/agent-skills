from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Literal

import yaml

from tools.capability_pack.model import FileHash, Provenance, QualificationResult
from tools.capability_pack.provenance import hash_files, load_provenance, write_provenance
from tools.capability_pack.summary import render_summary


class QualificationError(RuntimeError):
    """The staged package could not be reproduced or qualified."""


class ConfigurationError(QualificationError):
    """The package path or vendir policy is invalid."""


class BreakingDriftError(QualificationError):
    """An imported skill disappeared or was renamed upstream."""


def _source_commit(package: Path) -> str:
    try:
        lock = yaml.safe_load((package / "vendir.lock.yml").read_text())
        commits = [
            content["git"]["sha"]
            for directory in lock["directories"]
            for content in directory["contents"]
            if "git" in content
        ]
    except (KeyError, TypeError, yaml.YAMLError, OSError) as error:
        raise QualificationError(f"invalid vendir lock: {error}") from error
    if not commits or any(not isinstance(commit, str) for commit in commits):
        raise QualificationError("vendir lock contains no Git source commit")
    if len(set(commits)) != 1:
        raise QualificationError("vendir lock Git sources resolved to different commits")
    return commits[0]


def _is_below(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _validate_relative_path(value: str, *, label: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise QualificationError(f"unsafe {label}: {value}")
    return path


def _validate_symlinks(stage: Path) -> None:
    root = stage.resolve()
    for path in stage.rglob("*"):
        if path.is_symlink() and not _is_below(path.resolve(), root):
            relative = path.relative_to(stage).as_posix()
            raise QualificationError(f"symlink escapes staged package: {relative}")


def _header_paths(patch: Path) -> tuple[str, ...]:
    paths: list[str] = []
    try:
        lines = patch.read_text().splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise QualificationError(f"cannot read patch {patch}: {error}") from error
    for line in lines:
        if line.startswith(("--- ", "+++ ")):
            value = line[4:].split("\t", 1)[0].split(" ", 1)[0]
            if value == "/dev/null":
                continue
            if value.startswith(("a/", "b/")):
                value = value[2:]
            paths.append(value)
    if not paths:
        raise QualificationError(f"patch has no file headers: {patch}")
    return tuple(paths)


def _apply_patches(stage: Path) -> None:
    series = stage / "patches" / "series"
    if not series.exists():
        return
    root = stage.resolve()
    for line in series.read_text().splitlines():
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        relative = _validate_relative_path(value, label="patch series path")
        patch = stage.joinpath(*relative.parts)
        if not _is_below(patch.resolve(), root):
            raise QualificationError(f"patch path escapes staged package: {value}")
        for header_path in _header_paths(patch):
            header = _validate_relative_path(header_path, label="patch path")
            destination = stage.joinpath(*header.parts)
            if not _is_below(destination.resolve(strict=False), root):
                raise QualificationError(f"unsafe patch path through symlink: {header_path}")
        try:
            subprocess.run(
                ["git", "apply", "--check", str(patch)],
                cwd=stage,
                check=True,
                timeout=30,
            )
            subprocess.run(
                ["git", "apply", str(patch)],
                cwd=stage,
                check=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise QualificationError(f"patch failed: {value}: {error}") from error


def _manifest_files(root: Path) -> list[Path]:
    return [path for path in root.rglob("*") if path.is_file() and not path.is_symlink()]


def _excluded_skills(package: Path) -> tuple[str, ...]:
    try:
        config = yaml.safe_load((package / "vendir.yml").read_text())
        patterns = [
            pattern
            for directory in config.get("directories", [])
            for content in directory.get("contents", [])
            for pattern in content.get("excludePaths", [])
        ]
    except (AttributeError, OSError, yaml.YAMLError) as error:
        raise QualificationError(f"invalid vendir configuration: {error}") from error
    names = {
        parts[index + 2]
        for pattern in patterns
        for parts in (PurePosixPath(pattern).parts,)
        for index, part in enumerate(parts[:-2])
        if part == "skills"
    }
    return tuple(sorted(names))


def _promote_staged_skills(
    stage: Path, previous: Provenance | None
) -> tuple[tuple[str, ...], tuple[FileHash, ...]]:
    skills = stage / "skills"
    skills.mkdir(exist_ok=True)
    staging = skills / ".upstream"
    roots = sorted(path for path in staging.iterdir() if path.is_dir()) if staging.exists() else []
    source_paths = [path for root in roots for path in _manifest_files(root)]
    source_files = hash_files(stage, source_paths)
    candidates = {
        skill.name: skill
        for root in roots
        for skill in root.iterdir()
        if skill.is_dir() and (skill / "SKILL.md").is_file()
    }
    previous_imports = set(previous.included_skills if previous else ())
    owned = {
        path.name
        for path in skills.iterdir()
        if path.is_dir() and path.name != ".upstream" and path.name not in previous_imports
    }
    collisions = sorted(owned & candidates.keys())
    if collisions:
        raise QualificationError(
            f"upstream skills collide with owned skills: {', '.join(collisions)}"
        )
    for name in previous_imports:
        shutil.rmtree(skills / name, ignore_errors=True)
    for name, source in sorted(candidates.items()):
        shutil.copytree(source, skills / name)
    shutil.rmtree(staging, ignore_errors=True)
    return tuple(sorted(candidates)), source_files


def _patch_manifest(stage: Path) -> tuple[FileHash, ...]:
    series = stage / "patches" / "series"
    if not series.exists():
        return ()
    patches = []
    for line in series.read_text().splitlines():
        value = line.strip()
        if value and not value.startswith("#"):
            relative = _validate_relative_path(value, label="patch series path")
            patches.append(stage.joinpath(*relative.parts))
    return hash_files(stage, patches)


def _license_manifest(stage: Path, previous: Provenance | None) -> tuple[FileHash, ...]:
    if previous:
        missing = [
            item.path for item in previous.license_files if not (stage / item.path).is_file()
        ]
        if missing:
            raise QualificationError(f"missing legal file: {', '.join(missing)}")
    licenses = stage / "LICENSES"
    manifest = hash_files(stage, _manifest_files(licenses)) if licenses.exists() else ()
    config = yaml.safe_load((stage / "vendir.yml").read_text())
    legal_required = any(
        content.get("legalPaths")
        for directory in config.get("directories", [])
        for content in directory.get("contents", [])
    )
    if legal_required and not manifest:
        raise QualificationError("missing legal file declared by vendir configuration")
    return manifest


def _output_manifest(stage: Path, inventory: tuple[str, ...]) -> tuple[FileHash, ...]:
    paths = [path for name in inventory for path in _manifest_files(stage / "skills" / name)]
    return hash_files(stage, paths)


def _changed_skills(previous: Provenance | None, proposed: Provenance) -> tuple[str, ...]:
    if not previous:
        return ()
    old = {item.path: item.sha256 for item in previous.output_files}
    new = {item.path: item.sha256 for item in proposed.output_files}
    names = {
        PurePosixPath(path).parts[1]
        for path in old.keys() & new.keys()
        if old[path] != new[path] and len(PurePosixPath(path).parts) > 2
    }
    return tuple(sorted(names))


def _validate_locked_reproduction(package: Path, proposed: Provenance) -> None:
    actual = _output_manifest(package, proposed.included_skills)
    if actual != proposed.output_files:
        raise QualificationError("locked reproduction differs from committed imported files")
    actual_licenses = _license_manifest(package, None)
    if actual_licenses != proposed.license_files:
        raise QualificationError("locked reproduction differs from committed legal files")


def _run_package_tests(stage: Path) -> tuple[str, str]:
    tests = stage / "tests"
    command_text = "python -m pytest -q -m 'not live_agent' tests"
    if not tests.is_dir():
        return command_text, "NOT RUN (no package tests)"
    try:
        subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-m", "not live_agent", "tests"],
            cwd=stage,
            check=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise QualificationError(f"non-live package tests failed: {error}") from error
    return command_text, "PASS"


def _replace_atomically(package: Path, staged: Path) -> None:
    backup = Path(tempfile.mkdtemp(prefix=f".{package.name}-backup-", dir=package.parent))
    backup.rmdir()
    package.rename(backup)
    try:
        staged.rename(package)
    except BaseException:
        backup.rename(package)
        raise
    shutil.rmtree(backup)


def qualify(
    package_root: Path,
    mode: Literal["update", "locked"],
    summary_path: Path | None = None,
) -> QualificationResult:
    package = package_root.resolve()
    if mode not in {"update", "locked"}:
        raise ValueError(f"unknown qualification mode: {mode}")
    if not package.is_dir():
        raise ConfigurationError(f"package does not exist: {package}")
    if not (package / "vendir.yml").is_file():
        raise ConfigurationError(f"package has no vendir.yml: {package}")

    temporary = Path(tempfile.mkdtemp(prefix=f".{package.name}-stage-", dir=package.parent))
    staged = temporary / package.name
    try:
        shutil.copytree(package, staged, symlinks=True)
        try:
            previous = load_provenance(package / "provenance.yml")
        except FileNotFoundError:
            previous = None
        except (KeyError, TypeError, ValueError, yaml.YAMLError) as error:
            raise QualificationError(f"invalid provenance: {error}") from error
        command = ["vendir", "sync"]
        if mode == "locked":
            command.append("-l")
        command.extend(["--chdir", str(staged)])
        try:
            subprocess.run(command, check=True, timeout=120)
        except (OSError, subprocess.SubprocessError) as error:
            raise QualificationError(f"vendir sync failed: {error}") from error
        _validate_symlinks(staged)
        inventory, source_files = _promote_staged_skills(staged, previous)
        removed = tuple(sorted(set(previous.included_skills if previous else ()) - set(inventory)))
        if removed:
            old_commit = previous.source_commit if previous else "unknown"
            raise BreakingDriftError(
                f"removed or renamed imported skill(s) {', '.join(removed)} from {old_commit}"
            )
        _apply_patches(staged)
        source_commit = _source_commit(staged)
        proposed = Provenance(
            source_commit=source_commit,
            included_skills=inventory,
            excluded_skills=_excluded_skills(staged),
            source_files=source_files,
            patch_files=_patch_manifest(staged),
            license_files=_license_manifest(staged, previous),
            output_files=_output_manifest(staged, inventory),
        )
        added = tuple(sorted(set(inventory) - set(previous.included_skills if previous else ())))
        changed_skills = _changed_skills(previous, proposed)
        test_command, test_result = _run_package_tests(staged)
        summary = render_summary(
            previous,
            proposed,
            changed_skills=changed_skills,
            patch_failures=(),
            test_command=test_command,
            test_result=test_result,
            setup_contract_changed=False,
        )
        write_provenance(staged / "provenance.yml", proposed)
        if mode == "update":
            if summary_path:
                summary_path.write_text(summary)
            _replace_atomically(package, staged)
            changed = previous != proposed
        else:
            _validate_locked_reproduction(package, proposed)
            if previous and (
                previous.source_commit != proposed.source_commit
                or previous.included_skills != proposed.included_skills
                or previous.patch_files != proposed.patch_files
                or previous.license_files != proposed.license_files
            ):
                raise QualificationError("locked reproduction differs from committed provenance")
            if summary_path:
                summary_path.write_text(summary)
            changed = False
        return QualificationResult(
            changed=changed,
            source_commit=source_commit,
            added_skills=added,
            removed_skills=removed,
            summary=summary,
        )
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
