from __future__ import annotations

import json
import subprocess
from pathlib import Path

from tools.capability_pack import refresh as refresh_module
from tools.capability_pack.model import Provenance, QualificationResult
from tools.capability_pack.provenance import write_provenance
from tools.capability_pack.qualify import PatchError
from tools.capability_pack.releases import ReleaseSelection


def package(tmp_path: Path) -> Path:
    root = tmp_path / "engineering"
    root.mkdir()
    write_provenance(
        root / "provenance.yml",
        Provenance("1" * 40, (), (), (), (), (), (), ()),
    )
    (root / "upstream.yml").write_text(
        "repository: https://example.test/upstream.git\n"
        "stable_tag_pattern: '^v(0|[1-9]\\d*)\\.(0|[1-9]\\d*)\\.(0|[1-9]\\d*)$'\n"
    )
    return root


def test_no_eligible_update_does_not_enter_qualification(tmp_path, monkeypatch) -> None:
    root = package(tmp_path)
    called = False

    monkeypatch.setattr(
        refresh_module,
        "resolve_release",
        lambda *_: ReleaseSelection("no_eligible_update", "v1.2.3", "2" * 40, "1" * 40),
    )

    def forbidden(*_args, **_kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(refresh_module, "qualify", forbidden)
    result, status = refresh_module.refresh(root, tmp_path / "artifacts")
    assert status == 0
    assert result["code"] == "no_eligible_update"
    assert called is False


def test_patch_rejection_is_externalized_without_mutating_package(tmp_path, monkeypatch) -> None:
    root = package(tmp_path)
    before = (root / "provenance.yml").read_bytes()
    monkeypatch.setattr(
        refresh_module,
        "resolve_release",
        lambda *_: ReleaseSelection("candidate", "v1.2.4", "2" * 40, "1" * 40),
    )
    monkeypatch.setattr(
        refresh_module,
        "qualify",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            PatchError("patches/reference.patch", "error: token=do-not-emit")
        ),
    )
    result, status = refresh_module.refresh(root, tmp_path / "artifacts")
    stored = json.loads((tmp_path / "artifacts" / "result.json").read_text())
    assert status == 1
    assert result["code"] == "patch_rejected"
    assert stored["diagnostics"][0]["path"] == "patches/reference.patch"
    assert "do-not-emit" not in json.dumps(stored)
    assert (root / "provenance.yml").read_bytes() == before


def test_candidate_runs_every_gate_before_qualified_result(tmp_path, monkeypatch) -> None:
    root = package(tmp_path)
    monkeypatch.setattr(
        refresh_module,
        "resolve_release",
        lambda *_: ReleaseSelection("candidate", "v1.2.4", "2" * 40, "1" * 40),
    )
    monkeypatch.setattr(
        refresh_module,
        "qualify",
        lambda *_args, **_kwargs: QualificationResult(
            True, "2" * 40, ("beta",), (), "summary", "0.4.0", ("alpha",)
        ),
    )
    commands = []

    def pass_gate(_repository, command):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    result, status = refresh_module.refresh(root, tmp_path / "artifacts", gate_runner=pass_gate)
    assert status == 0
    assert result["outcome"] == "qualified"
    assert [gate["name"] for gate in result["gates"]] == [name for name, _ in refresh_module.GATES]
    assert all(gate["status"] == "pass" for gate in result["gates"])
    assert commands == [command for _, command in refresh_module.GATES]


def test_first_failed_gate_blocks_and_records_sanitized_detail(tmp_path, monkeypatch) -> None:
    root = package(tmp_path)
    before = {
        path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()
    }
    monkeypatch.setattr(
        refresh_module,
        "resolve_release",
        lambda *_: ReleaseSelection("candidate", "v1.2.4", "2" * 40, "1" * 40),
    )

    def promote(*_args, **_kwargs):
        (root / "candidate.txt").write_text("candidate\n")
        return QualificationResult(True, "2" * 40, (), (), "summary", "0.3.1", ("alpha",))

    monkeypatch.setattr(refresh_module, "qualify", promote)

    def fail_gate(_repository, command):
        return subprocess.CompletedProcess(command, 1, "", "token=secret-value")

    result, status = refresh_module.refresh(root, tmp_path / "artifacts", gate_runner=fail_gate)
    stored = json.loads((tmp_path / "artifacts" / "result.json").read_text())
    assert (status, result["code"]) == (1, "gate_failed")
    assert stored["gates"][0]["status"] == "fail"
    assert [gate["name"] for gate in stored["gates"]] == [name for name, _ in refresh_module.GATES]
    assert "secret-value" not in json.dumps(stored)
    assert {
        path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()
    } == before


def test_gate_exception_restores_promoted_package_byte_for_byte(tmp_path, monkeypatch) -> None:
    root = package(tmp_path)
    before = {
        path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()
    }
    monkeypatch.setattr(
        refresh_module,
        "resolve_release",
        lambda *_: ReleaseSelection("candidate", "v1.2.4", "2" * 40, "1" * 40),
    )

    def promote(*_args, **_kwargs):
        (root / "candidate.txt").write_text("candidate\n")
        return QualificationResult(True, "2" * 40, (), (), "summary", "0.3.1", ("alpha",))

    monkeypatch.setattr(refresh_module, "qualify", promote)

    def explode(_repository, _command):
        raise RuntimeError("runner exploded")

    result, status = refresh_module.refresh(root, tmp_path / "artifacts", gate_runner=explode)
    after = {
        path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()
    }
    assert (status, result["code"]) == (1, "gate_failed")
    assert [gate["status"] for gate in result["gates"]] == ["fail" for _ in refresh_module.GATES]
    assert after == before
