"""A package script's module docstring stays short (#2834).

A docstring is the script's `--help` and the first thing an agent reads, so it says what the script is and points to
its docs. A rule goes in the docs and in a test, never only in `--help`: gatekeeper.py's docstring grew to 72 KB
because each change wrote its rule there. Files already over the cap are listed with their size: each may shrink, never grow.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tools.script_docstring_size import ALLOWED, CAP, ROOT, docstring_size, oversize

GATEKEEPER = ROOT / "gatekeeper/skills/gatekeeper/scripts/gatekeeper.py"


def test_no_package_script_docstring_is_over_the_cap():
    assert oversize(ROOT, CAP, ALLOWED) == []


def test_an_allowlisted_size_is_a_ceiling_not_a_floor():
    """A listed file that shrank under the cap needs its line deleted, so the list only shrinks."""
    stale = [n for n in ALLOWED if docstring_size(ROOT / n) <= CAP]
    assert stale == [], f"under the cap now, remove from ALLOWED: {stale}"


def make_script(root: Path, name: str, size: int) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('"""' + "x" * size + '"""\n', encoding="utf-8")


def test_a_fixture_script_over_the_cap_fails_naming_file_size_and_cap(tmp_path):
    make_script(tmp_path, "pack/skills/s/scripts/big.py", CAP + 1)
    make_script(tmp_path, "pack/skills/s/scripts/small.py", CAP)
    (found,) = oversize(tmp_path, CAP, {})
    assert "pack/skills/s/scripts/big.py" in found
    assert str(CAP + 1) in found and str(CAP) in found
    assert "policy.md" in found and "help=" in found


def test_an_allowlisted_file_that_grows_fails(tmp_path):
    make_script(tmp_path, "pack/skills/s/scripts/old.py", 6000)
    name = "pack/skills/s/scripts/old.py"
    assert oversize(tmp_path, CAP, {name: 6000}) == []
    assert oversize(tmp_path, CAP, {name: 5000}) != []
    (found,) = oversize(tmp_path, CAP, {name: 5990})
    assert name in found and "6000" in found and "5990" in found


def run_help(*args: str) -> str:
    done = subprocess.run(
        [sys.executable, str(GATEKEEPER), *args, "--help"],
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout


def test_gatekeeper_docstring_is_under_the_cap():
    assert docstring_size(GATEKEEPER) <= CAP


def test_gatekeeper_help_is_a_short_summary():
    text = run_help()
    assert len(text) < 8000
    assert "policy.md" in text and "verbs.md" in text
    for verb in ("check", "land", "record", "claim", "overlap", "heavy"):
        assert verb in text


VERB_WORDS = {
    "check": "proofs",
    "land": "merge queue",
    "claim": "claim",
    "overlap": "same files",
    "heavy": "heavy wrapper",
    "timeouts": "limit",
    "record": "approval",
}


@pytest.mark.parametrize("verb", sorted(VERB_WORDS))
def test_each_gatekeeper_verb_has_its_own_help(verb):
    text = run_help(verb)
    assert "usage: gatekeeper.py " + verb in text
    assert VERB_WORDS[verb] in text
    assert len(text) < 3000


def test_help_says_the_policy_is_read_from_the_base_not_the_checkout():
    for text in (run_help(), (GATEKEEPER.parent.parent / "SKILL.md").read_text()):
        flat = " ".join(text.split())
        assert "origin/<base>" in flat or "origin/`<base>`" in flat
        assert "at the checkout's root" not in flat
        assert "GATEKEEPER_POLICY_FROM_WORKING_TREE" in flat  # the working-tree reads are named too


def test_verb_help_names_the_cases_the_runtime_tests_show():
    assert "whole selection" in " ".join(run_help("rerun-tests").split())
    assert "another tree whose configured inputs match" in " ".join(run_help("gate-record").split())
    assert "breakglass" in " ".join(run_help("record", "approval").split())


def test_every_place_that_states_rerun_s_exit_rule_matches_the_code():
    top = " ".join(run_help().split())
    assert (
        "check rerun` exits 0 once it has printed a state; a missing PR or an unloadable policy exits 1"
        in top
    )
    usage = " ".join((GATEKEEPER.parent.parent / "verbs.md").read_text().split())
    assert (
        "exit 0 once it has printed a state (a missing PR or an unloadable policy exits 1)" in usage
    )
    assert "rerun: not needed (<why>)" in usage and "rerun: needed|done|no" not in usage


def test_check_help_says_what_check_does():
    text = run_help("check")
    assert "proofs" in text and "build" in text and "merge" in text
    flat = " ".join(text.split())
    assert (
        "`rerun: not needed (<why>)`, and exits 0 once it has printed a state; a missing PR or an unloadable policy exits 1"
        in flat
    )  # not under the exit-1 rule
    assert "eligible to land" in flat and "no go or gate record" in flat  # stalled's two cases
    assert "an unsatisfied one once the cap is reached" in flat  # verified at the cap
