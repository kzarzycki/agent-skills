from __future__ import annotations

from pathlib import Path

import pytest

from tools.capability_pack import cli
from tools.capability_pack.model import QualificationResult
from tools.capability_pack.qualify import BreakingDriftError, QualificationError


@pytest.mark.parametrize(
    ("command", "mode"),
    [("update", "update"), ("check", "locked")],
)
def test_cli_maps_commands_to_qualification_modes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    command: str,
    mode: str,
) -> None:
    """Catch update resolving a lock or check mutating through refresh mode."""
    package = tmp_path / "engineering"
    package.mkdir()
    seen = []

    def fake_qualify(root: Path, selected_mode: str, summary_path: Path | None = None):
        seen.append((root, selected_mode, summary_path))
        return QualificationResult(False, "1" * 40, (), (), "current")

    monkeypatch.setattr(cli, "qualify", fake_qualify)

    assert cli.main([command, str(package), "--summary", str(tmp_path / "summary.txt")]) == 0
    assert seen == [(package, mode, tmp_path / "summary.txt")]


@pytest.mark.parametrize(
    ("error", "exit_code"),
    [
        (BreakingDriftError("removed alpha"), 3),
        (QualificationError("patch failed"), 4),
    ],
)
def test_cli_maps_qualification_failures_to_stable_exit_codes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    exit_code: int,
) -> None:
    """Catch automation treating breaking drift or reproduction failure as usage errors."""
    package = tmp_path / "engineering"
    package.mkdir()

    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(cli, "qualify", fail)

    assert cli.main(["check", str(package)]) == exit_code


def test_cli_returns_usage_exit_for_bad_syntax() -> None:
    """Catch argparse terminating the host process instead of returning the contract code."""
    assert cli.main(["unknown", "engineering"]) == 2


def test_cli_returns_configuration_exit_for_missing_package(tmp_path: Path) -> None:
    """Catch a bad package path being reported as a reproduction failure."""
    assert cli.main(["check", str(tmp_path / "missing")]) == 2


@pytest.mark.parametrize(
    "malformed",
    [
        "[]\n",
        "directories:\n  - contents: invalid\n",
        "directories:\n  - contents:\n      - legalPaths: invalid\n",
    ],
)
def test_cli_maps_malformed_vendir_and_license_structures_to_configuration_exit(
    package: Path, fake_vendir: Path, malformed: str
) -> None:
    """Catch malformed YAML structures leaking AttributeError or returning exit 4."""
    (package / "vendir.yml").write_text(malformed)

    assert cli.main(["check", str(package)]) == 2
