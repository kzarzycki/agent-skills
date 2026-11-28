"""verifier_pass.py: the one predicate of a Codex verifier pass the repeat-pass guards share, with gatekeeper's rules (#3003)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "gatekeeper" / "scripts"))
import verifier_pass as vp

HEAD = "a" * 40
HEADING = "**Verifier (codex/terra-6.1/med), pass 1** on abc"


def review(body: str, who: str = "OWNER", head: str = HEAD, login: str = "someone") -> dict:
    return {
        "commit_id": head,
        "body": body,
        "author_association": who,
        "user": {"login": login},
    }


def test_a_review_that_only_quotes_a_verdict_is_no_pass() -> None:
    quoted = review("Looks fine to me.\n\n> Verifier (codex/terra-6.1/med), pass 1\n")
    assert vp.earlier_codex_pass([quoted], [], HEAD) is None


def test_an_untrusted_account_with_the_heading_is_no_pass() -> None:
    assert vp.earlier_codex_pass([review(HEADING, who="NONE")], [], HEAD) is None
    assert vp.earlier_codex_pass([review(HEADING, who="CONTRIBUTOR")], [], HEAD) is None


def test_a_real_pass_from_a_writer_the_pr_author_or_the_runner_counts() -> None:
    assert vp.earlier_codex_pass([review(HEADING)], [], HEAD) == ("codex/terra-6.1/med", "1")
    mine = review(HEADING, who="NONE", login="me")
    assert vp.earlier_codex_pass([mine], [], HEAD, {"me"}) == ("codex/terra-6.1/med", "1")
    assert vp.earlier_codex_pass([mine], [], HEAD, {"you"}) is None
    assert vp.earlier_codex_pass([review(HEADING)], [], "b" * 40) is None  # a fix was pushed


def test_a_comment_counts_only_in_the_scripts_own_format_from_a_trusted_author() -> None:
    own = f"Head: {HEAD}\nVERDICT: 0 blocker\n\nVerifier: codex/sol-6.1/high, pass 2\n"
    assert vp.earlier_codex_pass([], [review(own)], HEAD) == ("codex/sol-6.1/high", "2")
    assert vp.earlier_codex_pass([], [review(own, who="NONE")], HEAD) is None
    late = f"I reran it.\nHead: {HEAD}\n\nVerifier: codex/sol-6.1/high, pass 2\n"
    assert vp.earlier_codex_pass([], [review(late)], HEAD) is None
    mid = f"Head: {HEAD}\n\nsee: Verifier: codex/sol-6.1/high, pass 2 above\n"
    assert vp.earlier_codex_pass([], [review(mid)], HEAD) is None


def test_another_family_is_no_codex_pass() -> None:
    claude = review("Verifier (claude, same-family), pass 1")
    assert vp.earlier_codex_pass([claude], [], HEAD) is None
