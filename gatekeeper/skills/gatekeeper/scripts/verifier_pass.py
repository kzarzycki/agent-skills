"""verifier_pass.py: the one predicate for "this is a Codex verifier pass on this head", read from a PR's REST reviews and
issue comments, so the guards that refuse a repeat Codex pass (cloud_verifier.py's `verify` and `thread`, and
omnigent_agent.py's `start`) cannot drift from each other or from gatekeeper's `passes()` (#3003).

The rules are `passes()`'s: the verifier heading is the start of the body (a review that only quotes or discusses an
earlier verdict is no pass) and the author is trusted, since anyone can review a public repo: the PR's author, the
account running the guard, or a writer (a collaborator permission of write or more, which the caller reads). A
comment of cloud_verifier.py's own counts on its own format: a body that starts `## Verifier report` (its folded
report) or `Head:` (a thread's), with a `Head: <sha>` line and a `Verifier: codex/..., pass <n>` line in it.
No imports beyond the standard library and folding.py, so a VM that has the gatekeeper scripts can run it.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from typing import Any

from folding import machine

# gatekeeper.py's PASS, with the Codex family: a review's heading, which is the start of the body
HEADING = re.compile(r"Verifier \((codex[^,)\n]*)\), pass (\d+)")
# cloud_verifier.py's comment: its folded report's heading, or a thread's `Head:` line, first
OWN_START = re.compile(r"## Verifier report\s*$|Head: ", re.MULTILINE)
SIGNATURE = re.compile(r"^Verifier: (codex[^,\n]*), pass (\d+)\s*$", re.MULTILINE)
# GitHub's collaborator permissions that write
WRITE = ("admin", "maintain", "write")


def can_write(permission: str) -> bool:
    """Whether a collaborator permission (`gh api .../collaborators/<login>/permission --jq .permission`) writes."""
    return permission.strip() in WRITE


def trusted(item: Any, logins: Iterable[str], writer: Callable[[str], bool]) -> bool:
    """Whether the review or comment `item` is by the PR's author or the account running the guard (`logins`), or by
    a login `writer` says can write."""
    user = item.get("user") if isinstance(item, dict) else None
    login = user.get("login") if isinstance(user, dict) else None
    return bool(login) and (login in set(logins) or writer(login))


def codex_pass(
    item: Any,
    head: str,
    logins: Iterable[str],
    writer: Callable[[str], bool],
    comment: bool = False,
) -> tuple[str, int] | None:
    """The (family, pass number) of the Codex verifier pass that `item` (a review, or with `comment` an issue
    comment) is on `head`, else None."""
    if not isinstance(item, dict):
        return None
    body = item.get("body") or ""
    if comment:
        text = machine(body)
        found = (
            OWN_START.match(text)
            and re.search(rf"^Head: {re.escape(head)}\s*$", text, re.MULTILINE)
            and SIGNATURE.search(text)
        )
    else:
        found = HEADING.match(body) if item.get("commit_id") == head else None
    # the cheap reads first: the writer lookup is a request
    if not found or not trusted(item, logins, writer):
        return None
    return found[1], int(found[2])


def earlier_codex_pass(
    reviews: list[Any],
    comments: list[Any],
    head: str,
    logins: Iterable[str] = (),
    writer: Callable[[str], bool] = lambda login: False,
) -> tuple[str, str] | None:
    """The (family, pass) of the newest Codex verifier pass already on `head`, else None. A second pass on an
    unchanged head repeats the first one's reading at the same cost, so the lead pushes a fix, or starts another
    route, instead (#2870). `logins` are the PR's author and the account running the guard."""
    logins = set(logins)
    found = [codex_pass(r, head, logins, writer) for r in reviews] + [
        codex_pass(c, head, logins, writer, comment=True) for c in comments
    ]
    best = max((f for f in found if f), key=lambda f: f[1], default=None)
    return (best[0], str(best[1])) if best else None
