from __future__ import annotations

import copy
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Literal

import yaml

from tools.capability_pack.model import (
    FileHash,
    Provenance,
    QualificationResult,
    SourceMapping,
)
from tools.capability_pack.provenance import hash_files, load_provenance, write_provenance
from tools.capability_pack.summary import render_summary

VENDIR_MANIFEST = "vendir.yml"
VENDIR_LOCK = "vendir.lock.yml"
ENGINEERING_SOURCE_URL = "https://github.com/mattpocock/skills.git"
ENGINEERING_TRACKED_REF = "origin/main"
ENGINEERING_OWNED_SKILLS = (
    "audit-third-party-software",
    "context-extractor",
    "operating-omnigent",
)


class QualificationError(RuntimeError):
    """The staged package could not be reproduced or qualified."""


class ConfigurationError(QualificationError):
    """The package path or vendir policy is invalid."""


class BreakingDriftError(QualificationError):
    """An imported skill disappeared or was renamed upstream."""


def validate_release_candidate(package_root: Path, tag: str) -> None:
    package = package_root.resolve()
    component = r"(?:0|[1-9]\d*)"
    match = re.fullmatch(
        rf"{re.escape(package.name)}-v({component}\.{component}\.{component})", tag
    )
    if not match:
        raise ConfigurationError(f"release tag must match {package.name}-vX.Y.Z: {tag}")
    tag_version = match.group(1)
    try:
        apm = _mapping(yaml.safe_load((package / "apm.yml").read_text()), "apm.yml")
        plugin = _mapping(
            json.loads((package / ".claude-plugin" / "plugin.json").read_text()),
            "plugin.json",
        )
    except (OSError, json.JSONDecodeError, yaml.YAMLError) as error:
        raise ConfigurationError(f"invalid package release metadata: {error}") from error
    versions = {"apm.yml": apm.get("version"), "plugin.json": plugin.get("version")}
    mismatched = [name for name, version in versions.items() if version != tag_version]
    if mismatched:
        raise ConfigurationError(f"release tag {tag} does not match {', '.join(mismatched)}")

    repository = Path(_git_output(["rev-parse", "--show-toplevel"], cwd=package))
    changed = _git_output(
        ["diff-tree", "--root", "--no-commit-id", "--name-only", "-r", "HEAD"],
        cwd=repository,
    ).splitlines()
    other_manifests = sorted(
        path
        for path in changed
        if re.fullmatch(r"[^/]+/\.claude-plugin/plugin\.json", path)
        and not path.startswith(f"{package.name}/")
    )
    if other_manifests:
        raise ConfigurationError(
            "release commit changes other package manifest(s): " + ", ".join(other_manifests)
        )


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


def _validate_source_policy(package: Path, config: dict) -> None:
    if package.name != "engineering":
        return
    sources = [
        content.get("git")
        for directory in config["directories"]
        for content in directory["contents"]
    ]
    if not sources or any(not isinstance(source, dict) for source in sources):
        raise ConfigurationError("engineering source policy requires Git sources only")
    urls = {source.get("url") for source in sources}
    refs = {source.get("ref") for source in sources}
    if urls != {ENGINEERING_SOURCE_URL} or refs != {ENGINEERING_TRACKED_REF}:
        raise ConfigurationError(
            "engineering source policy requires "
            f"{ENGINEERING_SOURCE_URL} at {ENGINEERING_TRACKED_REF}"
        )
    managed = set(_managed_skills(config))
    source_leaves = {
        PurePosixPath(content.get("newRootPath", "")).name
        for directory in config["directories"]
        for content in directory["contents"]
        if content.get("newRootPath")
    }
    claimed = sorted(set(ENGINEERING_OWNED_SKILLS) & (managed | source_leaves))
    missing = sorted(
        name
        for name in ENGINEERING_OWNED_SKILLS
        if not (package / "skills" / name / "SKILL.md").is_file()
    )
    if claimed or missing:
        details = []
        if claimed:
            details.append(f"claimed by vendir: {', '.join(claimed)}")
        if missing:
            details.append(f"missing: {', '.join(missing)}")
        raise ConfigurationError(
            "engineering repository-owned skill policy violated: " + "; ".join(details)
        )


def _source_commit(package: Path) -> str:
    commits = []
    try:
        lock = _mapping(yaml.safe_load((package / VENDIR_LOCK).read_text()), VENDIR_LOCK)
        directories = _sequence(lock.get("directories"), f"{VENDIR_LOCK} directories")
        for raw_directory in directories:
            directory = _mapping(raw_directory, f"{VENDIR_LOCK} directory")
            for raw_content in _sequence(directory.get("contents"), f"{VENDIR_LOCK} contents"):
                content = _mapping(raw_content, f"{VENDIR_LOCK} content")
                if "git" in content:
                    git = _mapping(content["git"], f"{VENDIR_LOCK} git lock")
                    commits.append(git.get("sha"))
    except (OSError, yaml.YAMLError) as error:
        raise ConfigurationError(f"invalid vendir lock {VENDIR_LOCK}: {error}") from error
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


def _apply_patches(stage: Path, repository_root: Path) -> None:
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
            environment = os.environ.copy()
            environment["GIT_CEILING_DIRECTORIES"] = str(repository_root)
            subprocess.run(
                ["git", "apply", "--check", str(patch)],
                cwd=stage,
                env=environment,
                check=True,
                timeout=30,
            )
            subprocess.run(
                ["git", "apply", str(patch)],
                cwd=stage,
                env=environment,
                check=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise QualificationError(f"patch failed: {value}: {error}") from error


def _manifest_files(root: Path) -> list[Path]:
    return [path for path in root.rglob("*") if path.is_file() and not path.is_symlink()]


def _managed_skills(config: dict) -> tuple[str, ...]:
    return tuple(
        sorted(
            parts[1]
            for directory in config["directories"]
            for parts in (PurePosixPath(directory["path"]).parts,)
            if len(parts) == 2 and parts[0] == "skills"
        )
    )


def _excluded_skills(config: dict) -> tuple[str, ...]:
    aliases = set()
    managed = set(_managed_skills(config))
    for directory in config["directories"]:
        destination = PurePosixPath(directory["path"])
        if len(destination.parts) != 2 or destination.parts[0] != "skills":
            continue
        for content in directory["contents"]:
            source = PurePosixPath(content.get("newRootPath", ""))
            if source.parts and source.name != destination.name and source.name not in managed:
                aliases.add(source.name)
    return tuple(sorted(aliases))


def _git_output(arguments: list[str], *, cwd: Path | None = None) -> str:
    try:
        return subprocess.run(
            ["git", *arguments],
            cwd=cwd,
            check=True,
            text=True,
            capture_output=True,
            timeout=120,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as error:
        raise QualificationError(f"Git command failed: {error}") from error


def _reconcile_inventory(
    stage: Path,
    config: dict,
    owned: tuple[str, ...],
) -> tuple[dict, str | None]:
    git_sources = {
        (git.get("url"), git.get("ref"))
        for directory in config["directories"]
        for content in directory["contents"]
        if isinstance((git := content.get("git")), dict)
    }
    if not git_sources:
        return config, None
    if len(git_sources) != 1:
        raise ConfigurationError("vendir inventory sources must use one Git repository and ref")
    repository, ref = next(iter(git_sources))
    if not isinstance(repository, str) or not isinstance(ref, str):
        raise ConfigurationError("vendir inventory Git repository and ref must be strings")

    temporary = Path(tempfile.mkdtemp(prefix=".engineering-inventory-"))
    checkout = temporary / "upstream"
    try:
        _git_output(["init", "--quiet", str(checkout)])
        fetch_ref = ref.removeprefix("origin/")
        _git_output(
            [
                "fetch",
                "--quiet",
                "--depth=1",
                "--filter=blob:none",
                "--no-tags",
                repository,
                fetch_ref,
            ],
            cwd=checkout,
        )
        candidate = _git_output(["rev-parse", "FETCH_HEAD^{commit}"], cwd=checkout)
        upstream_names = set(
            _git_output(
                ["ls-tree", "-d", "--name-only", f"{candidate}:skills/engineering"],
                cwd=checkout,
            ).splitlines()
        )
        upstream_names = {
            name
            for name in upstream_names
            if name
            and subprocess.run(
                [
                    "git",
                    "cat-file",
                    "-e",
                    f"{candidate}:skills/engineering/{name}/SKILL.md",
                ],
                cwd=checkout,
                check=False,
                capture_output=True,
                timeout=30,
            ).returncode
            == 0
        }
    finally:
        shutil.rmtree(temporary)

    configured: dict[str, str] = {}
    template: dict | None = None
    for directory in config["directories"]:
        destination = PurePosixPath(directory["path"])
        if len(destination.parts) != 2 or destination.parts[0] != "skills":
            continue
        for content in directory["contents"]:
            source = PurePosixPath(content.get("newRootPath", ""))
            if source.parts[:2] != ("skills", "engineering"):
                continue
            configured[source.name] = destination.name
            if source.name == destination.name and template is None:
                template = directory

    missing = sorted(set(configured) - upstream_names)
    if missing:
        raise BreakingDriftError(
            "removed or renamed configured upstream leaf(s) "
            f"{', '.join(missing)} at candidate {candidate}"
        )
    collisions = sorted(upstream_names & set(owned) - set(configured))
    if collisions:
        raise BreakingDriftError(
            "upstream leaf collides with repository-owned skill(s) "
            f"{', '.join(collisions)} at candidate {candidate}"
        )
    additions = sorted(upstream_names - set(configured) - set(owned))
    if additions and template is None:
        raise ConfigurationError("no ordinary engineering leaf available as inventory template")

    committed = copy.deepcopy(config)
    for name in additions:
        directory = copy.deepcopy(template)
        directory["path"] = f"skills/{name}"
        content = directory["contents"][0]
        content["newRootPath"] = f"skills/engineering/{name}"
        content["includePaths"] = [f"skills/engineering/{name}/**/*"]
        committed["directories"].append(directory)
    committed["directories"].sort(
        key=lambda item: (
            not str(item["path"]).startswith("skills/"),
            str(item["path"]),
        )
    )

    pinned = copy.deepcopy(committed)
    for directory in pinned["directories"]:
        for content in directory["contents"]:
            if isinstance(content.get("git"), dict):
                content["git"]["ref"] = candidate
    (stage / VENDIR_MANIFEST).write_text(yaml.safe_dump(pinned, sort_keys=False))
    return committed, candidate


def _source_mappings(
    config: dict, source_commit: str, inventory: tuple[str, ...]
) -> tuple[SourceMapping, ...]:
    mappings: list[SourceMapping] = []
    for directory in config["directories"]:
        destination = PurePosixPath(directory["path"])
        if len(destination.parts) != 2 or destination.parts[0] != "skills":
            continue
        git_contents = [content for content in directory["contents"] if "git" in content]
        if len(git_contents) != 1:
            raise QualificationError(
                f"source mapping for {destination.as_posix()} must have exactly one Git source"
            )
        content = git_contents[0]
        git = content.get("git")
        repository = git.get("url") if isinstance(git, dict) else None
        source = content.get("newRootPath")
        if not isinstance(repository, str) or not repository:
            raise QualificationError(
                f"source mapping for {destination.as_posix()} has no repository URL"
            )
        if not isinstance(source, str) or not source:
            raise QualificationError(
                f"source mapping for {destination.as_posix()} has no source path"
            )
        source_path = _validate_relative_path(source, label="source mapping path")
        mappings.append(
            SourceMapping(
                source_repository=repository,
                source_commit=source_commit,
                source_path=source_path.as_posix(),
                destination_path=destination.as_posix(),
            )
        )

    destinations = [item.destination_path for item in mappings]
    sources = [(item.source_repository, item.source_path) for item in mappings]
    expected = {f"skills/{name}" for name in inventory}
    if len(destinations) != len(set(destinations)) or set(destinations) != expected:
        raise QualificationError(
            "source mapping destinations must match the imported skill inventory"
        )
    if len(sources) != len(set(sources)):
        raise QualificationError("source mapping source paths must be unique")
    return tuple(sorted(mappings, key=lambda item: item.destination_path))


def _owned_skills(package: Path, managed: tuple[str, ...]) -> tuple[str, ...]:
    skills = package / "skills"
    return tuple(
        sorted(
            path.name
            for path in skills.iterdir()
            if path.is_dir() and path.name not in managed and (path / "SKILL.md").is_file()
        )
    )


def _inventory(stage: Path, managed: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(name for name in managed if (stage / "skills" / name / "SKILL.md").is_file())


def _sync_manifest(stage: Path, mode: Literal["update", "locked"]) -> None:
    command = ["vendir", "sync"]
    if mode == "locked":
        command.append("--locked")
    command.extend(["--chdir", str(stage)])
    try:
        subprocess.run(command, check=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as error:
        raise QualificationError(f"vendir sync failed for {VENDIR_MANIFEST}: {error}") from error


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
    try:
        lines = series.read_text().splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise QualificationError("unreadable patch series: patches/series") from error
    for line in lines:
        value = line.strip()
        if value and not value.startswith("#"):
            relative = _validate_relative_path(value, label="patch series path")
            patch = stage.joinpath(*relative.parts)
            if not patch.is_file():
                raise QualificationError(f"missing patch file: {value}")
            patches.append(patch)
    try:
        return hash_files(stage, patches)
    except OSError as error:
        path = Path(error.filename) if error.filename else None
        label = path.relative_to(stage).as_posix() if path and _is_below(path, stage) else "unknown"
        raise QualificationError(f"unreadable patch file: {label}") from error


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
    old = {item.path: (item.sha256, item.mode) for item in previous.output_files}
    new = {item.path: (item.sha256, item.mode) for item in proposed.output_files}
    names = {
        PurePosixPath(path).parts[1]
        for path in old.keys() | new.keys()
        if old.get(path) != new.get(path) and len(PurePosixPath(path).parts) > 2
    }
    return tuple(sorted(names))


def _setup_contract_changed(previous: Provenance | None, proposed: Provenance) -> bool:
    if previous is None:
        return False
    prefix = "skills/setup-engineering-workflow-for-apm/"
    old = tuple(item for item in previous.output_files if item.path.startswith(prefix))
    new = tuple(item for item in proposed.output_files if item.path.startswith(prefix))
    return old != new


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
    env = os.environ.copy()
    env["CAPABILITY_PACK_QUALIFICATION_STAGE_ROOT"] = str(stage.resolve())
    try:
        subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-m", "not live_agent", "tests"],
            cwd=stage,
            env=env,
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
    config = _load_manifest(package / VENDIR_MANIFEST)
    _validate_source_policy(package, config)
    _source_commit(package)
    original_managed = _managed_skills(config)
    owned = _owned_skills(package, original_managed)
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
        committed_config = config
        if mode == "update":
            committed_config, _ = _reconcile_inventory(staged, config, owned)
        managed = _managed_skills(committed_config)
        _sync_manifest(staged, mode)
        if mode == "update":
            (staged / VENDIR_MANIFEST).write_text(yaml.safe_dump(committed_config, sort_keys=False))
        _validate_symlinks(staged)
        if _owned_manifest(staged, owned) != original_owned:
            raise QualificationError("vendir changed a repository-owned skill")
        inventory = _inventory(staged, managed)
        source_files = _output_manifest(staged, inventory)
        removed = tuple(sorted(set(previous.included_skills if previous else ()) - set(inventory)))
        if removed:
            old_commit = previous.source_commit if previous else "unknown"
            raise BreakingDriftError(
                f"removed or renamed imported skill(s) {', '.join(removed)} from {old_commit}"
            )
        source_commit = _source_commit(staged)
        source_mappings = _source_mappings(committed_config, source_commit, inventory)
        license_files = _license_manifest(staged, previous, (committed_config,))
        patch_files: tuple[FileHash, ...] = ()
        try:
            patch_files = _patch_manifest(staged)
            _apply_patches(staged, package.parent)
        except QualificationError as error:
            if summary_path:
                partial = Provenance(
                    source_commit=source_commit,
                    included_skills=inventory,
                    excluded_skills=_excluded_skills(committed_config),
                    source_mappings=source_mappings,
                    source_files=source_files,
                    patch_files=patch_files,
                    license_files=license_files,
                    output_files=(),
                )
                message = str(error)
                failure = (
                    message.split(":", 2)[1].strip()
                    if message.startswith("patch failed:")
                    else message
                )
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
            excluded_skills=_excluded_skills(committed_config),
            source_mappings=source_mappings,
            source_files=source_files,
            patch_files=patch_files,
            license_files=license_files,
            output_files=_output_manifest(staged, inventory),
        )
        added = tuple(sorted(set(inventory) - set(previous.included_skills if previous else ())))
        changed_skills = _changed_skills(previous, proposed)
        write_provenance(staged / "provenance.yml", proposed)
        test_command, test_result = _run_package_tests(staged)
        summary = render_summary(
            previous,
            proposed,
            changed_skills=changed_skills,
            patch_failures=(),
            test_command=test_command,
            test_result=test_result,
            setup_contract_changed=_setup_contract_changed(previous, proposed),
        )
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
