"""verifier_pass.py: the one predicate for "this is a Codex verifier pass on this head", read from a PR's REST reviews and
issue comments, so the guards that refuse a repeat Codex pass (cloud_verifier.py's `verify` and `thread`, and
omnigent_agent.py's `start`) cannot drift from each other or from gatekeeper's `passes()` (#3003).

The rules are `passes()`'s: the verifier heading starts the body (a review that only quotes or discusses an earlier
verdict is no pass) and the author is trusted, since anyone can review a public repo: the PR's author, the account
running the guard, or a writer. A comment of cloud_verifier.py's own counts on its own format only: a `Head: <sha>`
line first (folded lines read in place), its `Verifier: codex/..., pass <n>` line below, from a trusted author.
No imports beyond the standard library and folding.py, so a VM that has the gatekeeper scripts can run it.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from folding import machine

# gatekeeper.py's PASS, with the Codex family: a review's heading, at the start of the body
HEADING = re.compile(r"\W*Verifier \((codex[^,)\n]*)\), pass (\d+)")
# cloud_verifier.py's comment: `Head:` first, then its folded `Verifier:` line
SIGNATURE = re.compile(r"^Verifier: (codex[^,\n]*), pass (\d+)\s*$", re.MULTILINE)
# GitHub's own word for a login that can write or own the repo; ponytail: an org MEMBER may only read, and counts
# here, which can only refuse a pass (the safe side); gatekeeper asks the permission API per login instead
WRITER_ASSOCIATIONS = ("OWNER", "MEMBER", "COLLABORATOR")


def trusted(item: Any, logins: Iterable[str]) -> bool:
    """Whether the review or comment `item` is by the PR's author or the account running the guard (`logins`), or by a
    writer by its `author_association`."""
    if not isinstance(item, dict):
        return False
    user = item.get("user")
    login = user.get("login") if isinstance(user, dict) else None
    return (login is not None and login in set(logins)) or (
        item.get("author_association") in WRITER_ASSOCIATIONS
    )


def codex_pass(
    item: Any, head: str, logins: Iterable[str], comment: bool = False
) -> tuple[str, int] | None:
    """The (family, pass number) of the Codex verifier pass that `item` (a review, or with `comment` an issue
    comment) is on `head`, else None."""
    if not trusted(item, logins):
        return None
    body = item.get("body") or ""
    if not comment:
        found = HEADING.match(body) if item.get("commit_id") == head else None
        return (found[1], int(found[2])) if found else None
    text = machine(body)  # the folded lines, in place
    if not re.match(rf"Head: {re.escape(head)}\s*$", text, re.MULTILINE):
        return None
    found = SIGNATURE.search(text)
    return (found[1], int(found[2])) if found else None


def earlier_codex_pass(
    reviews: list[Any], comments: list[Any], head: str, logins: Iterable[str] = ()
) -> tuple[str, str] | None:
    """The (family, pass) of the newest Codex verifier pass already on `head`, else None. A second pass on an
    unchanged head repeats the first one's reading at the same cost, so the lead pushes a fix, or starts another
    route, instead (#2870). `logins` are the PR's author and the account running the guard."""
    logins = set(logins)
    found = [codex_pass(r, head, logins) for r in reviews] + [
        codex_pass(c, head, logins, comment=True) for c in comments
    ]
    best = max((f for f in found if f), key=lambda f: f[1], default=None)
    return (best[0], str(best[1])) if best else None
