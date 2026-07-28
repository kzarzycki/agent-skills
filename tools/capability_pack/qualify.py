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

VENDIR_MANIFESTS = (
    ("vendir.yml", "vendir.lock.yml"),
    ("vendir.grilling.yml", "vendir.grilling.lock.yml"),
)


class QualificationError(RuntimeError):
    """The staged package could not be reproduced or qualified."""


class ConfigurationError(QualificationError):
    """The package path or vendir policy is invalid."""


class BreakingDriftError(QualificationError):
    """An imported skill disappeared or was renamed upstream."""


def _mapping(value: object, label: str) -> dict:
    if not isinstance(value, dict):
        raise ConfigurationError(f"{label} must be a mapping")
    return value


def _sequence(value: object, label: str) -> list:
    if not isinstance(value, list):
        raise ConfigurationError(f"{label} must be a list")
    return value


def _load_manifest(path: Path) -> dict:
    try:
        config = _mapping(yaml.safe_load(path.read_text()), path.name)
        directories = _sequence(config.get("directories"), f"{path.name} directories")
        for index, raw_directory in enumerate(directories):
            directory = _mapping(raw_directory, f"{path.name} directory {index}")
            if not isinstance(directory.get("path"), str):
                raise ConfigurationError(f"{path.name} directory {index} path must be a string")
            contents = _sequence(
                directory.get("contents"), f"{path.name} directory {index} contents"
            )
            for content_index, raw_content in enumerate(contents):
                content = _mapping(
                    raw_content, f"{path.name} directory {index} content {content_index}"
                )
                for field in ("ignorePaths", "excludePaths", "legalPaths"):
                    values = content.get(field, [])
                    if not isinstance(values, list) or any(
                        not isinstance(value, str) for value in values
                    ):
                        raise ConfigurationError(
                            f"{path.name} {field} in content {content_index} must be a string list"
                        )
        return config
    except FileNotFoundError as error:
        raise ConfigurationError(f"missing vendir manifest: {path.name}") from error
    except yaml.YAMLError as error:
        raise ConfigurationError(f"invalid vendir manifest {path.name}: {error}") from error


def _source_commit(package: Path) -> str:
    commits = []
    for _, lock_name in VENDIR_MANIFESTS:
        try:
            lock = _mapping(yaml.safe_load((package / lock_name).read_text()), lock_name)
            directories = _sequence(lock.get("directories"), f"{lock_name} directories")
            for raw_directory in directories:
                directory = _mapping(raw_directory, f"{lock_name} directory")
                for raw_content in _sequence(directory.get("contents"), f"{lock_name} contents"):
                    content = _mapping(raw_content, f"{lock_name} content")
                    if "git" in content:
                        git = _mapping(content["git"], f"{lock_name} git lock")
                        commits.append(git.get("sha"))
        except (OSError, yaml.YAMLError) as error:
            raise ConfigurationError(f"invalid vendir lock {lock_name}: {error}") from error
    if not commits or any(not isinstance(commit, str) for commit in commits):
        raise ConfigurationError("vendir locks contain no Git source commit")
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


def _excluded_skills(configs: tuple[dict, ...]) -> tuple[str, ...]:
    patterns = [
        pattern
        for config in configs
        for directory in config["directories"]
        for content in directory["contents"]
        for pattern in content.get("excludePaths", [])
    ]
    names = {
        parts[index + 2]
        for pattern in patterns
        for parts in (PurePosixPath(pattern).parts,)
        for index, part in enumerate(parts[:-2])
        if part == "skills"
    }
    return tuple(sorted(names))


def _owned_skills(configs: tuple[dict, ...]) -> tuple[str, ...]:
    ignored = {
        PurePosixPath(pattern).parts[0]
        for directory in configs[0]["directories"]
        for content in directory["contents"]
        for pattern in content.get("ignorePaths", [])
        if PurePosixPath(pattern).parts
    }
    separately_managed = {
        PurePosixPath(directory["path"]).parts[1]
        for config in configs[1:]
        for directory in config["directories"]
        if len(PurePosixPath(directory["path"]).parts) > 1
        and PurePosixPath(directory["path"]).parts[0] == "skills"
    }
    return tuple(sorted(ignored - separately_managed))


def _inventory(stage: Path, owned: tuple[str, ...]) -> tuple[str, ...]:
    skills = stage / "skills"
    return tuple(
        sorted(
            path.name
            for path in skills.iterdir()
            if path.is_dir() and path.name not in owned and (path / "SKILL.md").is_file()
        )
    )


def _sync_manifests(stage: Path, mode: Literal["update", "locked"]) -> None:
    for manifest, lock in VENDIR_MANIFESTS:
        command = [
            "vendir",
            "sync",
            "--file",
            manifest,
            "--lock-file",
            lock,
        ]
        if mode == "locked":
            command.append("--locked")
        command.extend(["--chdir", str(stage)])
        try:
            subprocess.run(command, check=True, timeout=120)
        except (OSError, subprocess.SubprocessError) as error:
            raise QualificationError(f"vendir sync failed for {manifest}: {error}") from error


def _owned_manifest(package: Path, owned: tuple[str, ...]) -> tuple[FileHash, ...]:
    paths = [
        path
        for name in owned
        if (package / "skills" / name).exists()
        for path in _manifest_files(package / "skills" / name)
    ]
    return hash_files(package, paths)


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


def _license_manifest(
    stage: Path, previous: Provenance | None, configs: tuple[dict, ...] | None = None
) -> tuple[FileHash, ...]:
    if previous:
        missing = [
            item.path for item in previous.license_files if not (stage / item.path).is_file()
        ]
        if missing:
            raise QualificationError(f"missing legal file: {', '.join(missing)}")
    licenses = stage / "LICENSES"
    manifest = hash_files(stage, _manifest_files(licenses)) if licenses.exists() else ()
    legal_required = bool(configs) and any(
        content.get("legalPaths")
        for config in configs
        for directory in config["directories"]
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
        for path in old.keys() | new.keys()
        if old.get(path) != new.get(path) and len(PurePosixPath(path).parts) > 2
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
    if summary_path and _is_below(summary_path.resolve(strict=False), package):
        raise ConfigurationError("summary path must be outside the package root")
    configs = tuple(_load_manifest(package / manifest) for manifest, _ in VENDIR_MANIFESTS)
    _source_commit(package)
    owned = _owned_skills(configs)
    original_owned = _owned_manifest(package, owned)

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
        _sync_manifests(staged, mode)
        _validate_symlinks(staged)
        if _owned_manifest(staged, owned) != original_owned:
            raise QualificationError("vendir changed a repository-owned skill")
        inventory = _inventory(staged, owned)
        source_files = _output_manifest(staged, inventory)
        removed = tuple(sorted(set(previous.included_skills if previous else ()) - set(inventory)))
        if removed:
            old_commit = previous.source_commit if previous else "unknown"
            raise BreakingDriftError(
                f"removed or renamed imported skill(s) {', '.join(removed)} from {old_commit}"
            )
        source_commit = _source_commit(staged)
        patch_files = _patch_manifest(staged)
        license_files = _license_manifest(staged, previous, configs)
        try:
            _apply_patches(staged)
        except QualificationError as error:
            if summary_path:
                partial = Provenance(
                    source_commit=source_commit,
                    included_skills=inventory,
                    excluded_skills=_excluded_skills(configs),
                    source_files=source_files,
                    patch_files=patch_files,
                    license_files=license_files,
                    output_files=(),
                )
                failure = str(error).split(":", 2)[1].strip()
                summary_path.write_text(
                    render_summary(
                        previous,
                        partial,
                        changed_skills=(),
                        patch_failures=(failure,),
                        test_command="python -m pytest -q -m 'not live_agent' tests",
                        test_result="NOT RUN",
                        setup_contract_changed=False,
                    )
                )
            raise
        proposed = Provenance(
            source_commit=source_commit,
            included_skills=inventory,
            excluded_skills=_excluded_skills(configs),
            source_files=source_files,
            patch_files=patch_files,
            license_files=license_files,
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
            if previous and previous != proposed:
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
