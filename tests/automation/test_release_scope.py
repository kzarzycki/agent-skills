from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml

from tools.capability_pack.qualify import ConfigurationError, validate_release_candidate


def _git(repo: Path, *arguments: str) -> None:
    environment = os.environ | {
        "GIT_AUTHOR_NAME": "Fixture",
        "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
        "GIT_COMMITTER_NAME": "Fixture",
        "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
    }
    subprocess.run(["git", *arguments], cwd=repo, env=environment, check=True)


def _repository(tmp_path: Path) -> Path:
    repo = tmp_path / "repository"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    engineering = repo / "engineering"
    (engineering / ".claude-plugin").mkdir(parents=True)
    (engineering / "apm.yml").write_text(
        yaml.safe_dump({"name": "engineering", "version": "0.2.0"})
    )
    (engineering / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "engineering", "version": "0.2.0"})
    )
    for package in ("research", "workflow"):
        manifest = repo / package / ".claude-plugin" / "plugin.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text(json.dumps({"name": package, "version": "1.0.0"}))
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")
    return repo


def test_release_candidate_accepts_matching_package_tag(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    marker = repo / "engineering" / "release.txt"
    marker.write_text("candidate\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "engineering release")

    validate_release_candidate(repo / "engineering", "engineering-v0.2.0")


@pytest.mark.parametrize("manifest", ["apm.yml", ".claude-plugin/plugin.json"])
def test_release_candidate_rejects_manifest_version_mismatch(
    tmp_path: Path,
    manifest: str,
) -> None:
    repo = _repository(tmp_path)
    path = repo / "engineering" / manifest
    if path.suffix == ".json":
        data = json.loads(path.read_text())
        data["version"] = "0.2.1"
        path.write_text(json.dumps(data))
    else:
        data = yaml.safe_load(path.read_text())
        data["version"] = "0.2.1"
        path.write_text(yaml.safe_dump(data))

    with pytest.raises(ConfigurationError, match=Path(manifest).name):
        validate_release_candidate(repo / "engineering", "engineering-v0.2.0")


@pytest.mark.parametrize("other_package", ["research", "workflow"])
def test_release_candidate_rejects_other_package_manifest_change(
    tmp_path: Path,
    other_package: str,
) -> None:
    repo = _repository(tmp_path)
    manifest = repo / other_package / ".claude-plugin" / "plugin.json"
    data = json.loads(manifest.read_text())
    data["version"] = "1.0.1"
    manifest.write_text(json.dumps(data))
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "mixed release")

    with pytest.raises(ConfigurationError, match=other_package):
        validate_release_candidate(repo / "engineering", "engineering-v0.2.0")


@pytest.mark.parametrize(
    "tag",
    [
        "v0.2.0",
        "engineering-0.2.0",
        "engineering-v0.2",
        "engineering-v0.2.0-beta",
        "engineering-v00.2.0",
        "engineering-v0.02.0",
        "engineering-v0.2.00",
    ],
)
def test_release_candidate_rejects_invalid_tag_shape(tmp_path: Path, tag: str) -> None:
    repo = _repository(tmp_path)

    with pytest.raises(ConfigurationError, match="tag"):
        validate_release_candidate(repo / "engineering", tag)


@pytest.mark.parametrize("version", ["00.2.0", "0.02.0", "0.2.00"])
def test_release_candidate_rejects_leading_zero_versions(tmp_path: Path, version: str) -> None:
    repo = _repository(tmp_path)
    engineering = repo / "engineering"
    (engineering / "apm.yml").write_text(
        yaml.safe_dump({"name": "engineering", "version": version})
    )
    (engineering / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "engineering", "version": version})
    )

    with pytest.raises(ConfigurationError, match="tag"):
        validate_release_candidate(engineering, f"engineering-v{version}")


HEAD = "a" * 40
SMOKE = {"RELEASE_SMOKE_REPOSITORY": "org/private", "RELEASE_SMOKE_WORKFLOW": "smoke.yml"}


def _runs(*runs: dict) -> Callable[[list[str]], str]:
    return lambda _arguments: json.dumps(list(runs))


def test_release_check_refuses_without_a_smoke_run_for_the_release_head() -> None:
    from tools.capability_pack.qualify import require_smoke_run

    other = {"conclusion": "success", "displayTitle": f"smoke {'b' * 40}", "url": "u-other"}
    failed = {"conclusion": "failure", "displayTitle": f"smoke {HEAD}", "url": "u-failed"}
    for runs in ((), (other,), (failed,)):
        with pytest.raises(ConfigurationError, match="no passing"):
            require_smoke_run(HEAD, SMOKE, _runs(*runs))
    with pytest.raises(ConfigurationError, match="RELEASE_SMOKE_REPOSITORY"):
        require_smoke_run(HEAD, {}, _runs())
    passed = {"conclusion": "success", "displayTitle": f"smoke {HEAD}", "url": "u-ok"}
    assert require_smoke_run(HEAD, SMOKE, _runs(other, failed, passed)) == "u-ok"


def test_release_check_command_is_off_without_the_smoke_repository_and_prints_a_skip(
    monkeypatch, capsys
) -> None:
    from tools.capability_pack import cli

    monkeypatch.setattr(cli, "validate_release_candidate", lambda *_a: None)
    monkeypatch.setattr(cli, "_git_output", lambda *_a, **_k: HEAD)
    for name in SMOKE:
        monkeypatch.delenv(name, raising=False)
    argv = ["release-check", "engineering", "engineering-v0.0.0"]
    assert cli.main(argv) == 0
    assert "smoke run: off (RELEASE_SMOKE_REPOSITORY unset)" in capsys.readouterr().out
    monkeypatch.setenv("RELEASE_SMOKE_REPOSITORY", "org/private")
    assert cli.main(argv) == 2
    assert "RELEASE_SMOKE_WORKFLOW" in capsys.readouterr().err
    assert cli.main([*argv, "--skip-smoke"]) == 0
    assert "smoke run: skipped" in capsys.readouterr().out


def test_release_check_asks_about_the_head_it_checked_out(monkeypatch, capsys) -> None:
    from tools.capability_pack import cli

    asked: list[str] = []
    monkeypatch.setenv("RELEASE_SMOKE_REPOSITORY", "org/private")
    monkeypatch.setattr(cli, "validate_release_candidate", lambda *_a: None)
    monkeypatch.setattr(cli, "_git_output", lambda *_a, **_k: HEAD)
    monkeypatch.setattr(cli, "require_smoke_run", lambda head: asked.append(head) or "u-ok")
    assert cli.main(["release-check", "engineering", "engineering-v0.0.0"]) == 0
    assert asked == [HEAD]
    assert "smoke run: u-ok" in capsys.readouterr().out


def test_smoke_run_refuses_a_short_head() -> None:
    from tools.capability_pack.qualify import require_smoke_run

    with pytest.raises(ConfigurationError, match="full commit sha"):
        require_smoke_run(HEAD[:7], SMOKE, _runs())


def test_smoke_workflow_in_releasing_md_requires_the_verdict_line() -> None:
    text = (Path(__file__).parents[2] / "engineering" / "RELEASING.md").read_text()
    block = text.split("```yaml")[1].split("```")[0]
    assert "grep -q '^gh: '" in block
    assert "risk: .*; merge: " in block
