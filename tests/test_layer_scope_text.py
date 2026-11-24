"""R2 of #2143 (#2175): a change that can't reach the product runs no product suite."""

from __future__ import annotations

import re
from pathlib import Path

LOOP = Path(__file__).resolve().parents[1] / "loop/skills/engineering-loop"
RULE = "A check runs only if it can fail because of the change"


def flat(name: str) -> str:
    """A file with line breaks and indentation folded to single spaces."""
    return re.sub(r"\s+", " ", (LOOP / name).read_text())


def test_instructions_pass_runs_the_layers_checks_not_the_product_suite() -> None:
    text = flat("lead.md")
    assert "the full verifier pass (tests, proof and repros)" not in text
    assert "`checks` entries of gatekeeper.md's `select`" in text
    assert "only when a file is a build input" in text
    assert "review, repros and mutation runs stay" in text
    assert f"{RULE}, R2" in text


def test_ci_runs_no_layers_tests() -> None:
    text = flat("SKILL.md")
    assert "which runs every `check:` part" not in text
    assert f"CI, which runs no layer's tests ({RULE}, R2)" in text


def test_unclassified_file_runs_the_products_affected_tests() -> None:
    text = flat("SKILL.md")
    assert "A file `select` doesn't classify counts as a build input" in text
    assert "so the product's affected tests run for it" in text
