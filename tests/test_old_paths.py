"""Every script `engineering/` held before the package split (#615) still runs at its old path in a checkout of
this repo, since a manager, a lead or a verifier start runs them there (`approvals.py ...`) until the release that
drops engineering's dependencies on the packages split out of it. A script forwards to the new one with the same
arguments, input and exit code. The role docs left that folder (#2232): they live only in
`loop/skills/engineering-loop/`, so a rule edit is made once."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[1]
SKILLS = REPOSITORY / "engineering" / "skills"

# the scripts at the base tree (engineering 0.34.0), each with the exit code its `--help` gave there
SCRIPTS = {
    "engineering-loop/scripts/acceptance.py": 0,
    "engineering-loop/scripts/approvals.py": 0,
    "engineering-loop/scripts/board.py": 2,
    "engineering-loop/scripts/browse.py": 0,
    "engineering-loop/scripts/cloud_verifier.py": 0,
    "engineering-loop/scripts/events.py": 0,
    "engineering-loop/scripts/gatekeeper.py": 0,
    "engineering-loop/scripts/labels.py": 0,
    "engineering-loop/scripts/mutate.py": 0,
    "engineering-loop/scripts/nightly.py": 0,
    "engineering-loop/scripts/rulesets.py": 0,
    "chief-of-staff/scripts/cos_page.py": 0,
    "chief-of-staff/scripts/memory.py": 2,
    "omnigent-telemetry/scripts/omnigent_telemetry.py": 0,
    "orchestrating-agents/scripts/claude_cloud.py": 0,
    "orchestrating-agents/scripts/claude_environments.py": 0,
    "orchestrating-agents/scripts/omnigent_agent.py": 0,
}


@pytest.mark.parametrize(("script", "code"), SCRIPTS.items())
def test_an_old_script_path_runs_as_it_did(script: str, code: int) -> None:
    path = SKILLS / script
    assert path.is_file(), f"{path} is gone"
    done = subprocess.run(
        [sys.executable, str(path), "--help"], capture_output=True, text=True, check=False
    )
    assert done.returncode == code, done.stdout + done.stderr


def test_the_old_loop_folder_holds_only_forwarders() -> None:
    """A SKILL.md there would make the engineering plugin ship an `engineering-loop` skill beside the loop package's,
    and a role doc there is a second copy of one in `loop/skills/engineering-loop/` that an edit must keep in step
    (#2232)."""
    assert not list((SKILLS / "engineering-loop").glob("*.md"))


def test_the_project_docs_name_the_loop_at_its_current_path() -> None:
    """docs/agents/ points at `loop/skills/engineering-loop/` (#2257), since the role docs live only there (#2232)."""
    stale = [
        f"{doc.relative_to(REPOSITORY)}:{number}"
        for doc in sorted((REPOSITORY / "docs" / "agents").glob("*.md"))
        for number, line in enumerate(doc.read_text().splitlines(), 1)
        if "engineering/skills/engineering-loop/" in line
    ]
    assert not stale, f"old engineering-loop path in {stale}; name loop/skills/engineering-loop/"
