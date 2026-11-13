"""github-project-board-setup's new-board template: the `Risk` field beside `Priority` (#929)."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

SETUP = (
    Path(__file__).resolve().parents[1]
    / "utilities/skills/github-project-board-setup/references/new-board-setup.md"
).read_text()


def created(name: str) -> list[str]:
    """The options, in order, of the single-select field the template's createProjectV2Field call makes."""
    call = re.search(
        rf'createProjectV2Field\(input:\{{[^}}]*name:"{name}",singleSelectOptions:\[(.*?)\]\}}\)',
        SETUP,
        re.DOTALL,
    )
    assert call, f"the template creates no {name} field"
    return re.findall(r'\{name:"([^"]+)"', call.group(1))


def test_the_template_creates_the_risk_field_with_low_medium_high_in_order() -> None:
    assert created("Risk") == ["Low", "Medium", "High"]
    assert created("Priority") == ["P0", "P1", "P2", "P3"]


def test_every_view_that_shows_priority_shows_risk() -> None:
    assert "R=$(f Risk)" in SETUP
    views = re.findall(r"^view '(.*)'$", SETUP, re.MULTILINE)
    shown = [re.search(r'"visible_fields":\[([^\]]*)\]', view).group(1) for view in views]
    with_priority = [fields for fields in shown if "$P," in fields]
    assert with_priority
    assert all("$R" in fields for fields in with_priority)


def test_every_shell_block_of_the_template_parses() -> None:
    """A block copied from the template runs as written: a quote inside a single-quoted query ends it."""
    blocks = re.findall(r"^```bash\n(.*?)^```", SETUP, re.DOTALL | re.MULTILINE)
    assert any('name:"Risk"' in block for block in blocks)
    for block in blocks:
        parsed = subprocess.run(["bash", "-n"], input=block, capture_output=True, text=True)
        assert parsed.returncode == 0, (parsed.stderr, block)
