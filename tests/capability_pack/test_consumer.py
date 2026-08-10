from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tools.capability_pack import consumer
from tools.capability_pack.consumer import ConsumerSyncError, prepare_consumer


def _repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "apm.yml").write_text(
        yaml.safe_dump(
            {
                "dependencies": {
                    "apm": [
                        {
                            "git": "kzarzycki/agent-skills/engineering",
                            "ref": "engineering-v0.2.0",
                        }
                    ]
                }
            },
            sort_keys=False,
        )
    )
    (repository / "apm.lock.yaml").write_text(
        yaml.safe_dump(
            {
                "dependencies": [
                    {
                        "name": "engineering",
                        "version": "0.2.0",
                        "resolved_commit": "1" * 40,
                        "resolved_ref": "engineering-v0.2.0",
                        "resolved_tag": "engineering-v0.2.0",
                    }
                ]
            }
        )
    )
    return repository


def _git_outputs(monkeypatch, source_commit: str = "2" * 40) -> None:
    def output(*arguments, cwd=None):
        if arguments[1] == "rev-parse":
            return source_commit
        if arguments[1] == "show":
            return "name: engineering\nversion: 0.3.0\n"
        raise AssertionError(arguments)

    monkeypatch.setattr(consumer, "_output", output)


def test_active_target_names_accepts_apm_026_shape() -> None:
    assert consumer._active_target_names(
        [
            {"target": "claude", "status": "active"},
            {"target": "codex", "status": "active"},
            {"target": "cursor", "status": "inactive"},
        ]
    ) == {"claude", "codex"}


def test_lock_identity_accepts_apm_026_without_resolved_tag() -> None:
    dependency = {
        "resolved_ref": "engineering-v0.3.0",
        "resolved_commit": "2" * 40,
        "version": "0.3.0",
    }
    consumer._validate_lock_identity(dependency, "engineering-v0.3.0", "2" * 40)


def test_lock_identity_rejects_inconsistent_optional_resolved_tag() -> None:
    dependency = {
        "resolved_ref": "engineering-v0.3.0",
        "resolved_tag": "engineering-v0.2.0",
        "resolved_commit": "2" * 40,
        "version": "0.3.0",
    }
    with pytest.raises(ConsumerSyncError, match="resolved_tag"):
        consumer._validate_lock_identity(dependency, "engineering-v0.3.0", "2" * 40)


def test_consumer_update_requires_forward_version_and_both_ancestry_guards(
    tmp_path, monkeypatch
) -> None:
    repository = _repository(tmp_path)
    _git_outputs(monkeypatch)
    ancestry = []

    def ancestor(_repository, older, newer):
        ancestry.append((older, newer))
        return True

    monkeypatch.setattr(consumer, "_is_ancestor", ancestor)
    assert prepare_consumer(repository, "engineering-v0.3.0", "2" * 40) == "0.3.0"
    dependency = yaml.safe_load((repository / "apm.yml").read_text())["dependencies"]["apm"][0]
    assert dependency["ref"] == "engineering-v0.3.0"
    assert ancestry == [
        ("2" * 40, "origin/main"),
        ("1" * 40, "2" * 40),
    ]


@pytest.mark.parametrize("failure", ["same_version", "off_main", "not_descendant"])
def test_consumer_rejects_nonforward_release_without_editing_manifest(
    tmp_path, monkeypatch, failure
) -> None:
    repository = _repository(tmp_path)
    before = (repository / "apm.yml").read_bytes()
    _git_outputs(monkeypatch)
    if failure == "same_version":
        (repository / "apm.lock.yaml").write_text(
            (repository / "apm.lock.yaml").read_text().replace("0.2.0", "0.3.0")
        )
        monkeypatch.setattr(consumer, "_is_ancestor", lambda *_: True)
    elif failure == "off_main":
        monkeypatch.setattr(consumer, "_is_ancestor", lambda *_: False)
    else:
        monkeypatch.setattr(
            consumer,
            "_is_ancestor",
            lambda _repository, older, newer: newer == "origin/main",
        )
    with pytest.raises(ConsumerSyncError):
        prepare_consumer(repository, "engineering-v0.3.0", "2" * 40)
    assert (repository / "apm.yml").read_bytes() == before
