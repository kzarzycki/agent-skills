from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from engineering.tests.test_consumer_e2e import (
    PACKAGE,
    _expected_skills,
    _file_manifest,
    _isolated_env,
    _run,
    _write_manifest,
)

FIXTURE_REPOSITORY = Path(__file__).parent / "fixture-repository"
LOCAL_MARKDOWN_REFERENCE = re.compile(r"\[[^\]]+\]\(([^)]+\.md)(?:#[^)]+)?\)")


@dataclass(frozen=True)
class TargetAdapter:
    name: str
    catalog_path: Path


CLAUDE = TargetAdapter("claude", Path(".claude/skills"))
CODEX = TargetAdapter("codex", Path(".agents/skills"))


def file_manifest(root: Path) -> dict[str, str]:
    return _file_manifest(root)


@dataclass(frozen=True)
class SkillCatalog:
    root: Path

    @property
    def skill_names(self) -> set[str]:
        return {path.parent.name for path in self.root.glob("*/SKILL.md")}

    @property
    def script_manifest(self) -> dict[str, str]:
        return {
            path: digest
            for path, digest in file_manifest(self.root).items()
            if "/scripts/" in f"/{path}"
        }

    def skill_root(self, skill_name: str) -> Path:
        return self.root / skill_name

    def file_bytes(self, skill_name: str, relative_path: str = "SKILL.md") -> bytes:
        return (self.skill_root(skill_name) / relative_path).read_bytes()


@dataclass(frozen=True)
class InstalledFixture:
    consumer: Path
    expected_skills: set[str]
    global_catalogs_before: dict[str, tuple[tuple[str, int, int], ...]]
    global_catalogs_after: dict[str, tuple[tuple[str, int, int], ...]]

    def catalog(self, adapter: TargetAdapter) -> SkillCatalog:
        return SkillCatalog(self.consumer / adapter.catalog_path)


def _catalog_state(root: Path) -> tuple[tuple[str, int, int], ...]:
    if not root.exists():
        return ()
    return tuple(
        sorted(
            (
                path.relative_to(root).as_posix(),
                path.stat().st_size,
                path.stat().st_mtime_ns,
            )
            for path in root.rglob("*")
            if path.is_file()
        )
    )


def _global_catalogs() -> dict[str, tuple[tuple[str, int, int], ...]]:
    home = Path.home()
    codex_home = Path(os.environ.get("CODEX_HOME", home / ".codex"))
    roots = {
        "claude": home / ".claude" / "skills",
        "agents": home / ".agents" / "skills",
        "codex": codex_home / "skills",
    }
    return {name: _catalog_state(root) for name, root in roots.items()}


def install_fixture(tmp_path: Path) -> InstalledFixture:
    global_catalogs_before = _global_catalogs()
    env = _isolated_env(tmp_path)
    package_copy = tmp_path / "engineering"
    shutil.copytree(PACKAGE, package_copy, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    consumer = tmp_path / "consumer"
    shutil.copytree(FIXTURE_REPOSITORY, consumer)
    _write_manifest(consumer / "apm.yml", {"path": str(package_copy)})

    _run(["apm", "install"], cwd=consumer, env=env)
    _run(["apm", "compile", "--validate"], cwd=consumer, env=env)

    return InstalledFixture(
        consumer=consumer,
        expected_skills=_expected_skills(),
        global_catalogs_before=global_catalogs_before,
        global_catalogs_after=_global_catalogs(),
    )


def local_reference_failures(catalog_root: Path) -> list[str]:
    failures: list[str] = []
    for document in catalog_root.rglob("*.md"):
        for match in LOCAL_MARKDOWN_REFERENCE.finditer(document.read_text()):
            target = match.group(1)
            if target.startswith(("http://", "https://", "./src/")) or "<" in target:
                continue
            if not (document.parent / target).resolve().is_file():
                failures.append(f"{document.relative_to(catalog_root)} -> {target}")
    return sorted(failures)
