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


def flat_text(text):
    return " ".join(text.split())


def test_the_three_policy_source_lists_name_the_same_cases():
    """Every read of the checkout's policy is named wherever the sources are listed (#2952)."""
    skill = flat_text((GATEKEEPER.parent.parent / "SKILL.md").read_text())
    usage = flat_text((GATEKEEPER.parent.parent / "verbs.md").read_text())
    for text in (flat_text(run_help()), skill, usage):
        text = text.replace("`", "")
        assert "no origin ref" in text
        assert "GATEKEEPER_POLICY_FROM_WORKING_TREE set" in text
        assert "queue-config" in text and "timeouts" in text
        assert "check setup's Mergify drift check" in text
    # a warning for a differing copy belongs where the base's copy is read, not to the explicit checkout readers
    assert "where the base's copy is read" in usage


def test_the_check_listing_gives_rerun_s_exit_rule():
    top = flat_text(run_help())
    assert (
        "waiting: exit 3; `rerun`: exit 0 once it has printed a state, 1 for a missing PR or an unloadable policy"
        in top
    )
    assert "exit 0 after reading the PR" not in top


def test_rerun_tests_says_when_the_whole_selection_runs_in_listing_description_and_usage():
    listing = flat_text(run_help())
    description = flat_text(run_help("rerun-tests"))
    usage = flat_text((GATEKEEPER.parent.parent / "verbs.md").read_text())
    for text in (listing, description, usage):
        assert "when the change since the red reselects every failed test" in text
        assert "else the red run's whole selection in its order" in text
        assert "a failed test that passes on the whole selection is a flake" in text.lower()
    assert "A pass is a flake only" not in description


def test_gate_record_says_it_finds_a_step_by_its_inputs_and_prints_a_missing_tree_alone():
    listing = flat_text(run_help())
    description = flat_text(run_help("gate-record"))
    usage = flat_text((GATEKEEPER.parent.parent / "verbs.md").read_text())
    for text in (listing, description, usage):
        assert "another tree whose configured inputs match" in text
        assert "a head with no tree or a policy refusal prints that problem alone" in text


def test_approval_help_says_breakglass_takes_a_head_even_when_withdrawn():
    listing = flat_text(run_help("record"))
    assert "breakglass" in listing and "owner only" in listing
    description = flat_text(run_help("record", "approval"))
    assert (
        "is the owner's alone: --by owner and --head, plus --reason unless --withdraw (see breakglass.md)"
        in description
    )
    usage = flat_text((GATEKEEPER.parent.parent / "verbs.md").read_text())
    assert (
        "approve breakglass <pr> --by owner --head <sha> (--reason <why>" in usage
        and "| --withdraw)" in usage
    )
