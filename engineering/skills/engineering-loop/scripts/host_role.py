"""Whether this host is marked orchestration-only, and the refusal a heavy run gets there (#1651).

An orchestration host runs leads, bridges and posting, never a suite, build or gate. The owner marks one with a file,
``~/.agents/orchestration-only`` (``AGENT_ORCHESTRATION_ONLY`` names another path); its text, if any, is the reason
shown. A file, not an env var, since every process of the host's user sees it with no setup, whichever launcher started
it. gatekeeper.py and the engineering pack's ``heavy_run_guard.py`` hook both read it here, so the rule has one copy.
Stdlib only and Python 3.9, since the hook imports it on a consumer's own ``python3``.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

MARKER = "~/.agents/orchestration-only"
OVERRIDE = "AGENT_ORCHESTRATION_ONLY"
CLOUD_RUN = "omnigent_agent.py claude-cloud-run -- <command>"


def marker_path(env: Mapping[str, str] | None = None) -> str | None:
    """The marker file's path: ``AGENT_ORCHESTRATION_ONLY``'s value, else ``MARKER`` under ``HOME``, both read from
    ``env`` (else this process's environment); None when that leaves no home to look in."""
    env = os.environ if env is None else env
    path = env.get(OVERRIDE) or MARKER
    if not path.startswith("~"):
        return path
    home = env.get("HOME")
    return os.path.join(home, path[2:]) if home and path.startswith("~/") else None


def orchestration_only(env: Mapping[str, str] | None = None) -> str | None:
    """The marker's reason (its first non-blank line, ``marked orchestration-only`` when it has none) when this host is
    marked; None when the file is absent or can't be read."""
    path = marker_path(env)
    if path is None:
        return None
    try:
        with open(path, encoding="utf-8", errors="replace") as text:
            lines = [line.strip() for line in text]
    except OSError:
        return None
    return next((line for line in lines if line), "marked orchestration-only")


def refusal(what: str, reason: str) -> str:
    """Why ``what`` (a command or a verb) is refused on a host marked for ``reason``, naming the cloud route."""
    return (
        f"`{what}` refused: this host is orchestration-only ({MARKER}: {reason}), so no test suite, build or gate"
        " runs here, whoever starts it and whatever prefix it carries (`LOOP_HOST_RUN` included). Run it in a Claude"
        f" cloud session: from a host, `{CLOUD_RUN}` on a pushed head; in a cloud session, run this same command"
        " there, since approvals.py reads GitHub through REST where GraphQL answers 403 (engineering-loop's SKILL.md,"
        " Where heavy steps run). Never start a child session for it: a cloud session's child lands on this host."
    )
