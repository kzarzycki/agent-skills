"""verifier_pass.py: the one predicate of a Codex verifier pass the repeat-pass guards share, with gatekeeper's rules (#3003)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "gatekeeper" / "scripts"))
import verifier_pass as vp

HEAD = "a" * 40
HEADING = "Verifier (codex/terra-6.1/med), pass 1 on abc"
WRITERS = {"writer"}


def writes(login: str) -> bool:
    return login in WRITERS


def review(body: str, login: str = "writer", head: str = HEAD) -> dict:
    return {"commit_id": head, "body": body, "user": {"login": login}}


def found(reviews: list, comments: list = (), logins=(), head: str = HEAD):
    return vp.earlier_codex_pass(list(reviews), list(comments), head, logins, writes)


def test_a_review_that_only_quotes_a_verdict_is_no_pass() -> None:
    assert found([review(f"Looks fine to me.\n\n{HEADING}\n")]) is None
    assert found([review(f"> {HEADING}\n")]) is None
    assert (
        found([review(f"**{HEADING}**")]) is None
    )  # gatekeeper's passes() reads a bare heading too


def test_an_untrusted_account_with_the_heading_is_no_pass() -> None:
    assert found([review(HEADING, login="stranger")]) is None
    assert found([review(HEADING, login="reader")]) is None  # an org member who only reads


def test_a_real_pass_from_a_writer_the_pr_author_or_the_runner_counts() -> None:
    assert found([review(HEADING)]) == ("codex/terra-6.1/med", "1")
    mine = review(HEADING, login="me")
    assert found([mine], logins={"me"}) == ("codex/terra-6.1/med", "1")
    assert found([mine], logins={"you"}) is None
    assert found([review(HEADING)], head="b" * 40) is None  # a fix was pushed


def test_a_comment_counts_only_in_the_scripts_own_format_from_a_trusted_author() -> None:
    own = f"Head: {HEAD}\nVERDICT: 0 blocker\n\nVerifier: codex/sol-6.1/high, pass 2\n"
    assert found([], [review(own)]) == ("codex/sol-6.1/high", "2")
    assert found([], [review(own, login="stranger")]) is None
    folded = (
        f"## Verifier report\nHead: {HEAD}\nVERDICT: 0 blocker\n\n<details><summary>Details</summary>\n\n"
        f"Head: {HEAD}\nVerifier: codex/sol-6.1/high, pass 2\n\n</details>\n"
    )
    assert found([], [review(folded)]) == ("codex/sol-6.1/high", "2")
    late = f"I reran it.\nHead: {HEAD}\n\nVerifier: codex/sol-6.1/high, pass 2\n"
    assert found([], [review(late)]) is None


def test_another_family_is_no_codex_pass() -> None:
    assert found([review("Verifier (claude, same-family), pass 1")]) is None


def test_can_write_reads_collaborator_permissions() -> None:
    assert [vp.can_write(p) for p in ("admin\n", "maintain", "write", "triage", "read", "")] == [
        True,
        True,
        True,
        False,
        False,
        False,
    ]
