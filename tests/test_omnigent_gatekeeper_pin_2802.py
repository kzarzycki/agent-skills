"""#2802: the installed omnigent skill runs against the installed gatekeeper that apm.yml pins beside it.

The tagged omnigent calls `gk.<name>` on its sibling gatekeeper and loads `denylist.py` from it. Gatekeeper 0.1.5, the one
the engineering pack brings, has neither, so the omnigent pin alone broke report collection, a locked-gate wait and the
supervisor's claim updates. The guard reads the committed installed trees, so a pin that drifts apart fails here."""

import re
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[1]
ROOTS = [".agents/skills", ".claude/skills"]


@pytest.mark.parametrize("root", ROOTS)
def test_installed_gatekeeper_has_what_installed_omnigent_calls(root: str) -> None:
    skills = REPOSITORY / root
    omnigent = (skills / "omnigent-agents/scripts/omnigent_agent.py").read_text()
    gatekeeper = (skills / "gatekeeper/scripts/gatekeeper.py").read_text()
    called = set(re.findall(r"\bgk\.([A-Za-z_]\w*)", omnigent))
    assert {"tree_policy", "timeouts", "issue_field", "set_issue_field"} <= called
    missing = sorted(
        n
        for n in called
        if not re.search(rf"^(?:def |class |(?:\w+, )*){n}\b", gatekeeper, re.MULTILINE)
    )
    assert not missing, f"{root}: installed gatekeeper lacks {missing}"
    assert (skills / "gatekeeper/scripts/denylist.py").is_file(), (
        f"{root}: no denylist.py beside gatekeeper.py"
    )


def test_apm_pins_gatekeeper_with_omnigent() -> None:
    manifest = (REPOSITORY / "apm.yml").read_text()
    assert re.search(
        r"kzarzycki/agent-skills/gatekeeper\n\s+ref: gatekeeper-v\d+\.\d+\.\d+-next", manifest
    )
