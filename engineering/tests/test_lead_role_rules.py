from __future__ import annotations

from pathlib import Path

LEAD = Path(__file__).parents[1] / "skills" / "engineering-loop" / "lead.md"


def test_lead_never_merges_main_into_a_pr_unless_the_gate_forces_it() -> None:
    text = " ".join(LEAD.read_text().split())
    assert "never merge `origin/main` into one, stacked or not, unless the gate forces it" in text
    assert "voids the verifier's verdict" in text
    assert "merge `origin/main` into its branch only when `land` reports a conflict" in text
