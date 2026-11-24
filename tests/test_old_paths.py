"""Every script and role doc `engineering/` held before the package split (#615) still resolves at its old path in a
checkout of this repo, since a manager, a lead or a verifier start runs them there (`approvals.py ...`, `--role
engineering/skills/engineering-loop/verifier.md`) until the release that drops engineering's dependencies on the
packages split out of it. A script forwards to the new one with the same arguments, input and exit code; a doc is a
copy of the moved file (the capability-pack check refuses a link out of the package), which this test holds
identical."""

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
# the docs at the base tree that a start names by path, and the file each moved to
DOCS = {
    "engineering-loop/verifier.md": "loop/skills/engineering-loop/verifier.md",
    "engineering-loop/worker.md": "loop/skills/engineering-loop/worker.md",
    "engineering-loop/lead.md": "loop/skills/engineering-loop/lead.md",
    "engineering-loop/proof-run.md": "loop/skills/engineering-loop/proof-run.md",
    "engineering-loop/coding-standards.md": "loop/skills/engineering-loop/coding-standards.md",
    "engineering-loop/issues.md": "loop/skills/engineering-loop/issues.md",
}


@pytest.mark.parametrize(("script", "code"), SCRIPTS.items())
def test_an_old_script_path_runs_as_it_did(script: str, code: int) -> None:
    path = SKILLS / script
    assert path.is_file(), f"{path} is gone"
    done = subprocess.run(
        [sys.executable, str(path), "--help"], capture_output=True, text=True, check=False
    )
    assert done.returncode == code, done.stdout + done.stderr


@pytest.mark.parametrize(("doc", "moved"), DOCS.items())
def test_an_old_doc_path_reads_the_moved_file(doc: str, moved: str) -> None:
    assert (SKILLS / doc).read_text() == (REPOSITORY / moved).read_text()


def test_the_old_loop_folder_ships_no_second_skill() -> None:
    """A SKILL.md there would make the engineering plugin ship an `engineering-loop` skill beside the loop package's."""
    assert not (SKILLS / "engineering-loop" / "SKILL.md").exists()


def test_the_project_docs_name_the_loop_at_its_current_path() -> None:
    """docs/agents/ points at `loop/skills/engineering-loop/` (#2257): the old path is a copy kept only for starts
    that still name it, and #2232 removes it."""
    stale = [
        f"{doc.relative_to(REPOSITORY)}:{number}"
        for doc in sorted((REPOSITORY / "docs" / "agents").glob("*.md"))
        for number, line in enumerate(doc.read_text().splitlines(), 1)
        if "engineering/skills/engineering-loop/" in line
    ]
    assert not stale, f"old engineering-loop path in {stale}; name loop/skills/engineering-loop/"
