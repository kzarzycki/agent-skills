from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

import pytest
import yaml

from tools.capability_pack.provenance import load_provenance
from tools.capability_pack.qualify import (
    BreakingDriftError,
    ConfigurationError,
    PortRequiredError,
    qualify,
    upstream_deltas,
)

NEW_COMMIT = "2" * 40
TUNED = "# Alpha, tuned\n"


def _tune(package: Path, name: str = "alpha") -> None:
    overlay = package / "overlays" / "skills" / name
    overlay.mkdir(parents=True)
    (overlay / "SKILL.md").write_text(TUNED)
    policy_path = package / "upstream.yml"
    policy = yaml.safe_load(policy_path.read_text())
    policy["owned_overlays"] = [
        {"source": f"overlays/skills/{name}", "destination": f"skills/{name}"}
    ]
    policy_path.write_text(yaml.safe_dump(policy, sort_keys=False))


def _decide(package: Path, skill: str, upstream: str = NEW_COMMIT) -> None:
    entry = {"upstream": upstream, "skill": skill, "decision": "ported", "note": "kept intent"}
    (package / "upstream-intake.yml").write_text(yaml.safe_dump([entry]))


def test_tuned_skill_ships_overlay_and_tracks_upstream_hashes(
    package: Path, upstream: Path, fake_vendir: Path
) -> None:
    """Catch the overlay leaking into the upstream baseline, or upstream leaking into the output."""
    _tune(package)

    qualify(package, "update")

    assert (package / "skills" / "alpha" / "SKILL.md").read_text() == TUNED
    source = {item.path: item for item in load_provenance(package / "provenance.yml").source_files}
    upstream_skill = upstream / "skills" / "engineering" / "alpha" / "SKILL.md"
    assert (
        source["skills/alpha/SKILL.md"].sha256
        == hashlib.sha256(upstream_skill.read_bytes()).hexdigest()
    )


def test_upstream_change_under_tuned_skill_requires_a_decision(
    package: Path, upstream: Path, fake_vendir: Path
) -> None:
    """Catch an intake that moves the baseline without anyone porting the delta."""
    _tune(package)
    (upstream / "skills" / "engineering" / "alpha" / "SKILL.md").write_text("# Alpha v2\n")

    with pytest.raises(PortRequiredError) as raised:
        qualify(package, "update")

    assert raised.value.skills == (("alpha", "skills/engineering/alpha"),)
    assert raised.value.new_commit == NEW_COMMIT


def test_recorded_decision_lets_the_baseline_move(
    package: Path, upstream: Path, fake_vendir: Path
) -> None:
    _tune(package)
    (upstream / "skills" / "engineering" / "alpha" / "SKILL.md").write_text("# Alpha v2\n")
    _decide(package, "alpha")

    qualify(package, "update")

    assert load_provenance(package / "provenance.yml").source_commit == NEW_COMMIT
    assert (package / "skills" / "alpha" / "SKILL.md").read_text() == TUNED


def test_decision_for_another_commit_does_not_count(
    package: Path, upstream: Path, fake_vendir: Path
) -> None:
    _tune(package)
    (upstream / "skills" / "engineering" / "alpha" / "SKILL.md").write_text("# Alpha v2\n")
    _decide(package, "alpha", upstream="3" * 40)

    with pytest.raises(PortRequiredError):
        qualify(package, "update")


def test_upstream_removal_of_tuned_skill_still_blocks(
    package: Path, upstream: Path, fake_vendir: Path
) -> None:
    """Catch the tuned overlay masking an upstream deletion."""
    _tune(package)
    for path in (upstream / "skills" / "engineering" / "alpha").iterdir():
        path.unlink()

    with pytest.raises(BreakingDriftError, match="alpha"):
        qualify(package, "update")


def test_malformed_ledger_fails_the_locked_check(
    package: Path, upstream: Path, fake_vendir: Path
) -> None:
    """Catch a bad ledger row merging unnoticed until the next intake."""
    _tune(package)
    qualify(package, "update")
    (package / "upstream-intake.yml").write_text(yaml.safe_dump([{"skill": "alpha"}]))

    with pytest.raises(ConfigurationError, match="upstream-intake.yml"):
        qualify(package, "locked")


def test_upstream_deltas_diff_only_the_pending_skill(tmp_path: Path) -> None:
    repository = tmp_path / "upstream"
    env = os.environ | {
        "GIT_AUTHOR_NAME": "Fixture",
        "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
        "GIT_COMMITTER_NAME": "Fixture",
        "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
        "GIT_CONFIG_GLOBAL": "/dev/null",
    }

    def commit(message: str) -> str:
        subprocess.run(["git", "add", "."], cwd=repository, check=True)
        subprocess.run(["git", "commit", "-qm", message], cwd=repository, env=env, check=True)
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repository, check=True, text=True, capture_output=True
        ).stdout.strip()

    for name in ("alpha", "beta"):
        (repository / "skills" / name).mkdir(parents=True)
        (repository / "skills" / name / "SKILL.md").write_text(f"# {name}\n")
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repository, check=True)
    old = commit("initial")
    (repository / "skills" / "alpha" / "SKILL.md").write_text("# alpha\nnew rule\n")
    (repository / "skills" / "beta" / "SKILL.md").write_text("# beta\nunrelated\n")
    new = commit("change both")

    deltas = upstream_deltas(
        PortRequiredError(str(repository), old, new, (("alpha", "skills/alpha"),))
    )

    assert list(deltas) == ["alpha"]
    assert deltas["alpha"].startswith(f"# {new[:7]} change both")
    assert "+new rule" in deltas["alpha"]
    assert "unrelated" not in deltas["alpha"]


def test_regenerate_ships_an_overlay_edit_at_the_lock_with_upstream_ahead(
    package: Path,
    upstream: Path,
    fake_vendir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catch an overlay edit that can only be regenerated by taking in upstream's newer commit."""
    _tune(package)
    qualify(package, "update")
    lock = (package / "vendir.lock.yml").read_text()
    (package / "overlays" / "skills" / "alpha" / "SKILL.md").write_text("# Alpha, tuned again\n")
    argv = tmp_path / "vendir-argv.log"
    monkeypatch.setenv("FAKE_VENDIR_ARGV_LOG", str(argv))
    monkeypatch.setenv("FAKE_VENDIR_COMMIT", "3" * 40)  # where an unlocked sync would move

    qualify(package, "regenerate")

    assert (package / "skills" / "alpha" / "SKILL.md").read_text() == "# Alpha, tuned again\n"
    assert (package / "vendir.lock.yml").read_text() == lock
    assert all("--locked" in line for line in argv.read_text().splitlines())
    assert qualify(package, "locked").changed is False
