"""R4 (#2176): a fix round runs only what the round's diff reaches. The worker selects tests against the last head
its run passed on, the lead judges a proof stale by its inputs, a later verifier pass reruns what the delta reaches
plus every repro still NOT FIXED, and the acceptance budget's reason is run time."""

from __future__ import annotations

import re
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
SKILL = REPOSITORY / "loop" / "skills" / "engineering-loop"
OLD = REPOSITORY / "engineering" / "skills" / "engineering-loop"
POINTER = "SKILL.md, A check runs only if it can fail because of the change"


def text(name: str) -> str:
    return " ".join((SKILL / name).read_text().split())


def test_worker_selects_a_fix_round_against_the_last_passed_head():
    body = text("worker.md")
    assert "approvals.py affected-tests --base <the last head its run passed on>" in body
    assert "a fix round's too" not in body


def test_lead_judges_a_proof_stale_by_its_inputs_not_its_sha():
    body = text("lead.md")
    assert "whose log names another commit" not in body
    assert 'head -1 "$f" | grep -qx "$(git rev-parse HEAD)"' not in body
    assert "whose inputs the round changed" in body
    assert POINTER in body


def test_later_verifier_pass_reruns_what_the_delta_reaches_and_open_repros():
    for name in ("verifier.md", "SKILL.md"):
        body = text(name)
        assert "reruns all of its repros" not in body and "reruns its repros." not in body, name
    verifier = text("verifier.md")
    assert "every repro still `NOT FIXED`" in verifier
    assert "never skipped" in verifier
    assert POINTER in verifier
    skill = text("SKILL.md")
    assert (
        "reruns the acceptance checks and repros the round's diff reaches, plus every repro still `NOT FIXED`"
        in skill
    )


def test_acceptance_budget_stays_with_run_time_as_its_reason():
    skill = text("SKILL.md")
    assert "Acceptance budget: <spec minutes>, <nightly minutes>" in skill
    assert "reruns them on every pass" not in skill
    assert re.search(r"since the spec's and the nightly's run time", skill)


def test_old_path_copies_match():
    for name in ("lead.md", "worker.md", "verifier.md"):
        assert (SKILL / name).read_text() == (OLD / name).read_text(), name
