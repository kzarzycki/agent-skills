"""approvals.py land: after a landing that touches the cloud environment's setup script, the environment's copy is
checked and the stale line printed; a diff that leaves the script alone makes no environment call (#989)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from approvals_harness import approvals

FAKE = """import json, sys
open(sys.argv[0] + ".called", "w").write(json.dumps(sys.argv[1:]))
print("environment setup is stale: dev (env_1); apply it with: cloud_verifier.py env-sync --apply")
sys.exit(1)
"""


@pytest.fixture
def landed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    folder = tmp_path / "scripts"
    folder.mkdir()
    (folder / "cloud_verifier.py").write_text(FAKE)
    monkeypatch.setattr(approvals, "installed_scripts", lambda skill: folder)
    monkeypatch.setattr(approvals, "loop_md", lambda: "")
    monkeypatch.setattr(approvals, "land_event", lambda *a, **k: None)
    real = approvals.subprocess.Popen

    def popen(args, *a, **kw):  # land_ended's delayed ref clear: not started here
        return None if kw.get("start_new_session") else real(args, *a, **kw)

    monkeypatch.setattr(approvals.subprocess, "Popen", popen)
    approvals.landed_ok.clear()

    def pull(*paths: str) -> dict[str, Any]:
        return {
            "number": 7,
            "headRefName": "claude/x",
            "files": {"nodes": [{"path": path} for path in paths]},
        }

    return folder, pull


def test_a_landing_that_touches_the_setup_script_prints_the_stale_line(landed, capsys) -> None:
    folder, pull = landed
    approvals.land_ended(pull("README.md", ".claude/claude-cloud-setup.sh"))
    assert "environment setup is stale" in capsys.readouterr().out
    assert (folder / "cloud_verifier.py.called").is_file()


def test_a_landing_that_leaves_the_setup_script_alone_makes_no_environment_call(
    landed, capsys
) -> None:
    folder, pull = landed
    approvals.land_ended(pull("README.md", "src/app.py"))
    assert "stale" not in capsys.readouterr().out
    assert not (folder / "cloud_verifier.py.called").exists()


def test_a_project_names_its_setup_script_once_in_loop_md_and_a_failed_check_never_fails_the_landing(
    landed, monkeypatch, capsys
) -> None:
    folder, pull = landed
    monkeypatch.setattr(approvals, "loop_md", lambda: "Cloud setup script: ci/vm.sh\n")
    approvals.land_ended(pull(".claude/claude-cloud-setup.sh"))  # not the declared path
    assert not (folder / "cloud_verifier.py.called").exists()
    monkeypatch.setattr(
        approvals, "installed_scripts", lambda skill: (_ for _ in ()).throw(OSError("boom"))
    )
    approvals.landed_ok.clear()
    approvals.land_ended(pull("ci/vm.sh"))  # raises inside: reported, not raised
    assert "setup-script check failed" in capsys.readouterr().err
