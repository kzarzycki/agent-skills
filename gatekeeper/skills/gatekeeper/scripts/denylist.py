"""denylist.py: the local deny list, one check for every script that posts to GitHub (gatekeeper.py, engineering-loop's
nightly.py, omnigent_agent.py), so the rule is stated once.

The file the environment variable `LOOP_DENY_LIST` names holds one term per line (a name, a repo slug, a hostname; `#`
starts a comment). `check(text)` raises `Denied` when a line of `text` names a listed term, ignoring case, at word
boundaries, since a public repo's comment keeps its first text in GitHub's edit history for good. An Omnigent session
link (`<scheme>://<host>[:port]/c/<32 hex id>`) may be posted, so a term that appears only inside one is not a match;
the same term anywhere else in the text still is. Without the variable nothing is checked; a list it names that can't
be read raises `Denied`, since an unread list would let every post through.
"""

import os
import re
from pathlib import Path

DENY_LIST = "LOOP_DENY_LIST"
# an Omnigent session link, which the public-repo rule allows: scheme, host, optional port, `/c/` and the 32 hex id
SESSION_LINK = re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s/<>()\[\]]+/c/[0-9a-f]{32}\b", re.IGNORECASE)


class Denied(Exception):
    """A post refused: the message says why, and nothing was posted."""


def check(text: str) -> None:
    """Raise `Denied` when `text` names a term of the deny list outside an Omnigent session link."""
    if not (where := os.environ.get(DENY_LIST)):
        return
    try:
        listed = Path(where).expanduser().read_text().splitlines()
    except OSError as exc:
        raise Denied(
            f"{DENY_LIST} names {where}, which can't be read ({exc.strerror}): nothing posted"
        ) from exc
    terms = [term for line in listed if (term := line.split("#", 1)[0].strip())]
    for number, line in enumerate(text.splitlines(), 1):
        line = SESSION_LINK.sub(" ", line)
        for term in terms:
            if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", line, re.IGNORECASE):
                raise Denied(
                    f"refused to post: line {number} names `{term}` from the deny list ({DENY_LIST}); nothing posted"
                )
