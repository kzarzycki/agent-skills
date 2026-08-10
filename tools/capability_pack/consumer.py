from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import yaml

TAG = re.compile(r"^engineering-v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


class ConsumerSyncError(RuntimeError):
    pass


def _version(value: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"(?:engineering-v)?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", value)
    if not match:
        raise ConsumerSyncError(f"version is not canonical SemVer: {value}")
    return tuple(int(item) for item in match.groups())


def _is_ancestor(repository: Path, older: str, newer: str) -> bool:
    return (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", older, newer],
            cwd=repository,
            check=False,
            capture_output=True,
            timeout=120,
        ).returncode
        == 0
    )


def _output(*arguments: str, cwd: Path | None = None) -> str:
    return subprocess.run(
        list(arguments), cwd=cwd, check=True, capture_output=True, text=True, timeout=120
    ).stdout.strip()


def prepare_consumer(repository: Path, source_tag: str, source_commit: str) -> str:
    match = TAG.fullmatch(source_tag)
    if not match:
        raise ConsumerSyncError(f"noncanonical engineering release tag: {source_tag}")
    peeled = _output("git", "rev-parse", f"{source_tag}^{{commit}}", cwd=repository)
    if peeled != source_commit:
        raise ConsumerSyncError("triggering tag does not peel to the supplied commit")
    if not _is_ancestor(repository, source_commit, "origin/main"):
        raise ConsumerSyncError("release candidate is not contained in origin/main")
    package_manifest = yaml.safe_load(
        _output("git", "show", f"{source_commit}:engineering/apm.yml", cwd=repository)
    )
    version = ".".join(match.groups())
    if package_manifest.get("version") != version:
        raise ConsumerSyncError("release tag and engineering package version disagree")
    lock = yaml.safe_load((repository / "apm.lock.yaml").read_text())
    locked = [item for item in lock["dependencies"] if item.get("name") == "engineering"]
    if len(locked) != 1:
        raise ConsumerSyncError("root lock must contain exactly one engineering dependency")
    old = locked[0]
    if _version(version) <= _version(str(old.get("version", ""))):
        raise ConsumerSyncError("consumer sync must move to a newer engineering SemVer")
    old_commit = old.get("resolved_commit")
    if not isinstance(old_commit, str) or not _is_ancestor(repository, old_commit, source_commit):
        raise ConsumerSyncError("consumer release is not a descendant of the locked commit")
    root_path = repository / "apm.yml"
    root = yaml.safe_load(root_path.read_text())
    dependencies = root.setdefault("dependencies", {}).setdefault("apm", [])
    matches = [
        item for item in dependencies if item.get("git") == "kzarzycki/agent-skills/engineering"
    ]
    if len(matches) != 1:
        raise ConsumerSyncError("root must declare exactly one engineering dependency")
    matches[0]["ref"] = source_tag
    root_path.write_text(yaml.safe_dump(root, sort_keys=False))
    return version


def assert_codex_inventory(repository: Path, source_tag: str, source_commit: str) -> None:
    targets = json.loads(_output("apm", "targets", "--json", cwd=repository))
    names = {
        item if isinstance(item, str) else item.get("name")
        for item in (targets if isinstance(targets, list) else targets.get("targets", []))
    }
    if "codex" not in names:
        raise ConsumerSyncError("Codex is not an active APM target")
    provenance = yaml.safe_load(
        _output("git", "show", f"{source_commit}:engineering/provenance.yml", cwd=repository)
    )
    policy = yaml.safe_load(
        _output("git", "show", f"{source_commit}:engineering/upstream.yml", cwd=repository)
    )
    overlay_names = {Path(item["destination"]).name for item in policy.get("owned_overlays", [])}
    expected = set(provenance["included_skills"]) | set(policy["owned_skills"]) | overlay_names
    lock = yaml.safe_load((repository / "apm.lock.yaml").read_text())
    matches = [item for item in lock["dependencies"] if item.get("name") == "engineering"]
    if len(matches) != 1:
        raise ConsumerSyncError("APM lock must contain exactly one engineering dependency")
    dependency = matches[0]
    required = {
        "resolved_ref": source_tag,
        "resolved_tag": source_tag,
        "resolved_commit": source_commit,
        "version": source_tag.removeprefix("engineering-v"),
    }
    for field, value in required.items():
        if dependency.get(field) != value:
            raise ConsumerSyncError(f"engineering lock {field} does not equal {value}")
    actual = {
        match.group(1)
        for path in dependency.get("deployed_files", [])
        if (match := re.fullmatch(r"\.agents/skills/([^/]+)/SKILL\.md", path))
    }
    if actual != expected:
        raise ConsumerSyncError(
            f"Codex engineering inventory differs: missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )
    for name in sorted(expected):
        found = " ".join(
            _output(
                "apm", "find", "--source", f".agents/skills/{name}/SKILL.md", cwd=repository
            ).split()
        )
        if "kzarzycki/agent-skills" not in found or source_tag not in found:
            raise ConsumerSyncError(f"APM source lookup does not prove {name} at {source_tag}")
