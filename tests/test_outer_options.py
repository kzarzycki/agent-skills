"""tools/outer_options.py (#1609): a pytest a test starts never inherits the outer run's PYTEST_ADDOPTS, so the
nightly's coverage flags stay with the run that builds the test map."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_a_nested_pytest_does_not_inherit_the_outer_runs_addopts(tmp_path: Path) -> None:
    (tmp_path / "test_inner.py").write_text(
        "import os\n\n\ndef test_inner():\n    assert 'PYTEST_ADDOPTS' not in os.environ\n"
    )
    done = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "-c",
            str(ROOT / "pyproject.toml"),
        ]
        + [str(tmp_path / "test_inner.py")],
        env={**os.environ, "PYTEST_ADDOPTS": "-q"},
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr


def test_this_run_does_not_hand_its_addopts_on() -> None:
    assert "PYTEST_ADDOPTS" not in os.environ
