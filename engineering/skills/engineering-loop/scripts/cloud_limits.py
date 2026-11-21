"""Cloud limits (engineering-loop): the writes a cloud session's GitHub proxy is known to refuse, in one table.

A script that would make one of these writes in a cloud VM skips it, makes no call, and prints the entry's line,
which names what stands in for it; a skipped write is no failure, so the step's exit code is what it would have
been had the write gone through. A new refusal is one entry here and one `skip()` at its write. No dependencies:
events.py, which needs only git, loads this file by path, as github_adapter.py does.
"""

from __future__ import annotations

import os
import subprocess

# the variable Claude Code sets to `true` in a cloud session's VM
CLOUD = "CLAUDE_CODE_REMOTE"

# write -> the line said instead of it, formatted with the write's own fields; each says what stands in
REFUSED = {
    # POST repos/<repo>/statuses/<sha>: HTTP 403
    "gate status": (
        "cloud VM: the `gate` status on {head} is not written; the record ref {ref} stands in, and the host posts the"
        " status with `local-ci <pr>`"
    ),
    "gate failure status": (
        "cloud VM: the `gate` failure status on {head} is not written; the report's gate log stands in, and the host"
        " posts the status"
    ),
    "proof status": (
        "cloud VM: the `{context}` status on {head} is not written; the record ref stands in, and the host posts the"
        " status with `local-ci <pr>`"
    ),
    "status": "cloud VM: the `{context}` status on {head} is not written; the host writes it",
    # git push of a ref outside refs/heads/: `RPC failed; HTTP 403`
    "events": "cloud VM: events stay local (events.md); {ref} is written here, not pushed",
    "events clear": "cloud VM: events stay local (events.md); origin's refs of {branch} are the host's to remove",
}


# what a failed GitHub call of approvals.py adds in a cloud VM: the call already went the VM's way, so the lead fixes
# the cause GitHub names here instead of looking for a host or a bridge session to run it (#1637)
FAILED_CALL = (
    "cloud VM: approvals.py made this GitHub call over REST, the route it takes here by itself (GraphQL answers 403, so"
    " every read falls back to REST or the proxy's routes), and the command runs in this cloud session as it is: no"
    " host helper or bridge session is needed. The line above is GitHub's answer to that REST call."
)


def failed_call(exc: BaseException) -> str | None:
    """In a cloud VM, FAILED_CALL for a `gh` call that failed (not a skipped write, which says its own line); else None."""
    command = getattr(exc, "cmd", None)
    first = command[0] if isinstance(command, (list, tuple)) and command else command
    if not in_cloud() or isinstance(exc, Skipped) or first != "gh":
        return None
    return FAILED_CALL


def in_cloud() -> bool:
    return os.environ.get(CLOUD) == "true"


def skip(write: str, **fields: str) -> str | None:
    """In a cloud VM, the line `write`'s entry says instead of the write; elsewhere None, and the caller writes."""
    return REFUSED[write].format(**fields) if in_cloud() else None


class Skipped(subprocess.CalledProcessError):
    """A known-refused write skipped in a cloud VM, raised where a caller already catches a failed call; its stderr is
    the entry's line, which the caller prints as it is."""

    def __init__(self, line: str) -> None:
        super().__init__(0, "skipped", stderr=line)
