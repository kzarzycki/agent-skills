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


def test_release_candidate_accepts_other_manifest_tagged_on_the_commit(tmp_path: Path) -> None:
    """One release commit may cut several packages, each with its own tag on it (#1861)."""
    repo = _repository(tmp_path)
    manifest = repo / "research" / ".claude-plugin" / "plugin.json"
    manifest.write_text(json.dumps({"name": "research", "version": "1.0.1"}))
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "two-package release")
    _git(repo, "tag", "research-v1.0.0")  # a wrong version's tag still refuses

    with pytest.raises(ConfigurationError, match="research-v1.0.1 is not tagged"):
        validate_release_candidate(repo / "engineering", "engineering-v0.2.0")

    _git(repo, "tag", "research-v1.0.1")
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


def test_release_check_passes_with_neither_smoke_variable_set(monkeypatch, capsys) -> None:
    from tools.capability_pack import cli

    monkeypatch.setattr(cli, "validate_release_candidate", lambda *_a: None)
    for name in SMOKE:
        monkeypatch.delenv(name, raising=False)
    assert cli.main(["release-check", "engineering", "engineering-v0.0.0"]) == 0
    assert "smoke" not in capsys.readouterr().out
    assert (
        cli.main(["release-check", "engineering", "engineering-v0.0.0", "--skip-smoke"]) == 2
    )  # flag is gone


def test_release_check_does_not_consult_the_smoke_run_even_when_configured(monkeypatch) -> None:
    from tools.capability_pack import cli

    monkeypatch.setattr(cli, "validate_release_candidate", lambda *_a: None)
    monkeypatch.setattr(
        cli, "run_smoke", lambda *_a, **_k: pytest.fail("release-check must not run the smoke")
    )
    for name, value in SMOKE.items():
        monkeypatch.setenv(name, value)
    assert cli.main(["release-check", "engineering", "engineering-v0.0.0"]) == 0


def test_smoke_run_command_fails_clearly_when_the_variables_are_unset(monkeypatch, capsys) -> None:
    from tools.capability_pack import cli

    for name in SMOKE:
        monkeypatch.delenv(name, raising=False)
    assert cli.main(["smoke-run", HEAD]) == 2
    assert "RELEASE_SMOKE_REPOSITORY" in capsys.readouterr().err


def _smoke_gh(conclusion: str, calls: list[list[str]]) -> Callable[[list[str]], str]:
    listings = iter([[], [{"databaseId": 7, "displayTitle": f"smoke {HEAD}"}]])

    def run(arguments: list[str]) -> str:
        calls.append(arguments)
        if arguments[:2] == ["run", "list"]:
            return json.dumps(next(listings))
        if arguments[:2] == ["run", "view"]:
            return json.dumps({"conclusion": conclusion, "status": "completed", "url": "u-run"})
        return ""

    return run


def test_run_smoke_dispatches_for_the_commit_and_reports_the_runs_result() -> None:
    from tools.capability_pack.qualify import run_smoke

    calls: list[list[str]] = []
    env = {**SMOKE, "RELEASE_SMOKE_PR": "5"}
    assert run_smoke(HEAD, env, _smoke_gh("success", calls), sleep=lambda _s: None) == (
        "u-run",
        "success",
    )
    dispatch = next(c for c in calls if c[:2] == ["workflow", "run"])
    assert f"ref={HEAD}" in dispatch and "pr=5" in dispatch and "org/private" in dispatch
    assert run_smoke(HEAD, SMOKE, _smoke_gh("failure", []), sleep=lambda _s: None) == (
        "u-run",
        "failure",
    )


def test_run_smoke_reports_its_own_dispatch_when_another_run_for_the_commit_exists() -> None:
    from tools.capability_pack.qualify import run_smoke

    listings = iter(
        [
            [],
            [
                {"databaseId": 7, "displayTitle": f"s {HEAD}"},
                {"databaseId": 8, "displayTitle": f"s {HEAD}"},
            ],
        ]
    )
    viewed: list[str] = []

    def run(arguments: list[str]) -> str:
        if arguments[:2] == ["workflow", "run"]:
            return (
                "Created workflow_dispatch event\nhttps://github.com/org/private/actions/runs/7\n"
            )
        if arguments[:2] == ["run", "list"]:
            return json.dumps(next(listings))
        if arguments[:2] == ["run", "view"]:
            viewed.append(arguments[2])
            return json.dumps({"conclusion": "failure", "status": "completed", "url": "u-7"})
        return ""

    assert run_smoke(HEAD, SMOKE, run, sleep=lambda _s: None) == ("u-7", "failure")
    assert viewed == ["7"]


def test_run_smoke_refuses_a_result_when_the_watch_broke_before_the_run_finished() -> None:
    from tools.capability_pack.qualify import run_smoke

    seen: list[list[str]] = []

    def run(arguments: list[str]) -> str:
        seen.append(arguments)
        if arguments[:2] == ["workflow", "run"]:
            return "https://github.com/org/private/actions/runs/7"
        if arguments[:2] == ["run", "list"]:
            return "[]"
        if arguments[:2] == ["run", "watch"]:
            raise ConfigurationError("gh: HTTP 403")
        return json.dumps({"status": "in_progress", "url": "u-7"})

    with pytest.raises(ConfigurationError, match="has not finished"):
        run_smoke(HEAD, SMOKE, run, sleep=lambda _s: None)
    assert "--exit-status" in next(c for c in seen if c[:2] == ["run", "watch"])


def test_smoke_run_command_resolves_an_annotated_tag_to_its_commit(monkeypatch) -> None:
    from tools.capability_pack import cli

    asked: list[list[str]] = []
    monkeypatch.setattr(cli, "_git_output", lambda arguments, **_k: asked.append(arguments) or HEAD)
    monkeypatch.setattr(cli, "run_smoke", lambda head: ("u", "success" if head == HEAD else "x"))
    assert cli.main(["smoke-run", "chief-of-staff-v0.1.0"]) == 0
    assert asked == [["rev-parse", "chief-of-staff-v0.1.0^{commit}"]]


def test_smoke_run_command_exits_with_the_runs_result(monkeypatch, capsys) -> None:
    from tools.capability_pack import cli

    monkeypatch.setattr(
        cli, "run_smoke", lambda head: ("u-run", "success" if head == HEAD else "x")
    )
    assert cli.main(["smoke-run", HEAD]) == 0
    assert "smoke run: success: u-run" in capsys.readouterr().out
    monkeypatch.setattr(cli, "run_smoke", lambda head: ("u-run", "failure"))
    assert cli.main(["smoke-run", HEAD]) == 1


def test_smoke_run_refuses_a_short_head() -> None:
    from tools.capability_pack.qualify import run_smoke

    with pytest.raises(ConfigurationError, match="full commit sha"):
        run_smoke(HEAD[:7], SMOKE, _runs())


def test_smoke_workflow_in_releasing_md_requires_the_verdict_line() -> None:
    text = (Path(__file__).parents[2] / "engineering" / "RELEASING.md").read_text()
    block = text.split("```yaml")[1].split("```")[0]
    assert "grep -q '^gh: '" in block
    assert "risk: .*; merge: " in block
