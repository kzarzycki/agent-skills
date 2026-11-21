"""Agent-facing text names one route per GitHub operation (#1637). A cloud agent told to run a `gh pr` or `gh issue`
subcommand, or `gh api graphql`, gets the proxy's 403 and rebuilds the call by hand; told "try X, else Y" or "if your
checkout has it", it probes. The role files, github.md's Review trail and every preamble a started agent reads name
engineering-loop's `approvals.py` verbs instead, which are one command on a host and in a cloud session."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

SKILLS = Path(__file__).resolve().parents[1] / "skills"
LOOP = SKILLS / "engineering-loop"
ROLES = ("lead.md", "worker.md", "verifier.md")
# every preamble or note omnigent_agent.py puts before a started agent's brief, or sends it as a nudge
PREAMBLES = (
    "PREAMBLE",
    "PR_PREAMBLE",
    "HELD_POST",
    "LEAD_PREAMBLE",
    "DELEGATION",
    "CLOUD_NOTE",
    "CLOUD_BRANCHES",
    "CLOUD_NO_PUSH",
    "HOST_RUN_NOTE",
    "CLOUD_RUN_LINE",
    "CLOUD_RUN_BRIEF",
    "CLOUD_RUN_NUDGE",
    "CLOUD_NUDGE",
    "HELD_NUDGE",
    "LEAD_NUDGE_CLOUD",
)
# a call that answers 403 in a cloud VM, and the phrasings of a probe: a second route tried after the first fails
PROBES = {
    "a GraphQL call": re.compile(r"gh api graphql"),
    "a `gh pr` or `gh issue` subcommand, which runs through GraphQL": re.compile(
        r"\bgh (pr|issue) [a-z]"
    ),
    "an optional helper": re.compile(r"if your checkout has", re.IGNORECASE),
    "a rules-dependent route": re.compile(r"where your rules refuse", re.IGNORECASE),
    "a try-else fallback": re.compile(r"\btry\b[^.\n]*\belse\b", re.IGNORECASE),
    "a fallback to REST": re.compile(
        r"\b(else|fall(s|ing)? back to)( through| over| to)? REST\b", re.IGNORECASE
    ),
    "a fallback on failure": re.compile(r"\bif (it|that|this) fails\b", re.IGNORECASE),
}


def review_trail() -> str:
    text = (LOOP / "github.md").read_text()
    start = text.index("## Review trail")
    return text[start : text.index("\n## ", start + 1)]


def texts() -> list[tuple[str, str]]:
    found = [(name, (LOOP / name).read_text()) for name in ROLES]
    found.append(("github.md, Review trail", review_trail()))
    path = SKILLS / "orchestrating-agents" / "scripts" / "omnigent_agent.py"
    spec = importlib.util.spec_from_file_location("omnigent_agent_text", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    found += [(f"omnigent_agent.py's {name}", getattr(module, name)) for name in PREAMBLES]
    return found


@pytest.mark.parametrize(
    ("where", "text"), texts(), ids=lambda value: value if len(value) < 60 else ""
)
def test_agent_facing_text_names_one_route_per_github_call(where: str, text: str) -> None:
    hits = [
        f"{what}: {line.strip()[:160]}"
        for line in text.splitlines()
        for what, pattern in PROBES.items()
        if pattern.search(line)
    ]
    assert not hits, f"{where} names a probe; name an approvals.py verb instead:\n" + "\n".join(
        hits
    )


@pytest.mark.parametrize(
    "line",
    [
        "List the threads: `gh api graphql -f query=...`",
        "Then `gh pr ready --undo` first.",
        "close it (`gh issue close <n>`)",
        "use `resolve` if your checkout has it, else REST",
        "Try the helper; else call the route by hand.",
        "It falls back to REST where GraphQL is refused.",
        "where your rules refuse `gh` beyond search, use curl",
    ],
)
def test_each_probe_shape_is_caught(line: str) -> None:
    assert any(pattern.search(line) for pattern in PROBES.values())


def test_a_policy_default_is_no_probe() -> None:
    """`X's line, else Y` names the project's setting and its default, one route either way."""
    line = "the gate of step 2 (`affected-tests` with an `Affected tests:` line, else `mise run check`)"
    assert not any(pattern.search(line) for pattern in PROBES.values())
