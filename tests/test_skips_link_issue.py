"""A test known red is skipped with its issue linked, never listed as an expected failure (#1820).

An unconditional `skip`, and any `xfail`, keeps a test out of the blocking gate, so the reason must
link the issue that tracks the fix: `#<n>` or an issue URL. A conditional skip (`skipif`,
`pytest.skip` in a body, `importorskip`) names an environment, not a defect, and needs none.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[1]
LINK = re.compile(r"#\d+|/issues/\d+")
MARKS = {"skip", "xfail"}


def unlinked(source: str) -> list[tuple[int, str]]:
    """(line, mark) of each `pytest.mark.skip` or `xfail` in `source` whose reason links no issue."""
    found = []
    tree = ast.parse(source)
    called = {id(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)}
    for node in ast.walk(tree):
        if id(node) in called:
            continue
        target = node.func if isinstance(node, ast.Call) else node
        if not (
            isinstance(target, ast.Attribute)
            and target.attr in MARKS
            and isinstance(target.value, ast.Attribute)
            and target.value.attr == "mark"
        ):
            continue
        reasons = []
        if isinstance(node, ast.Call):
            # `skip(reason)` takes it first; `xfail`'s first positional is a condition
            parts = [k.value for k in node.keywords if k.arg == "reason"]
            if target.attr == "skip":
                parts += node.args[:1]
            reasons = [p.value for p in parts if isinstance(p, ast.Constant) and isinstance(p.value, str)]
        if not any(LINK.search(reason) for reason in reasons):
            found.append((node.lineno, target.attr))
    return sorted(set(found))


@pytest.mark.parametrize(
    "source",
    [
        "@pytest.mark.skip\ndef test_a(): ...\n",
        "@pytest.mark.skip(reason='broken')\ndef test_a(): ...\n",
        "@pytest.mark.xfail(run=False, reason='broken, no link')\ndef test_a(): ...\n",
        "@pytest.mark.xfail\ndef test_a(): ...\n",
    ],
)
def test_a_skip_or_xfail_without_an_issue_link_is_found(source: str) -> None:
    assert unlinked(source)


@pytest.mark.parametrize(
    "source",
    [
        "@pytest.mark.skip(reason='Flaky: #591')\ndef test_a(): ...\n",
        "@pytest.mark.skip('see https://github.com/o/r/issues/7')\ndef test_a(): ...\n",
        "@pytest.mark.xfail(run=False, reason='#12')\ndef test_a(): ...\n",
        "@pytest.mark.skipif(True, reason='needs a tool')\ndef test_a(): ...\n",
        "def test_a():\n    pytest.skip('needs GNU date')\n",
    ],
)
def test_a_linked_or_conditional_skip_passes(source: str) -> None:
    assert unlinked(source) == []


def test_every_skip_and_xfail_in_the_repository_links_its_issue() -> None:
    tracked = [
        path
        for path in REPOSITORY.rglob("test_*.py")
        if not {".venv", "apm_modules", ".claude", "node_modules", ".git"} & set(path.relative_to(REPOSITORY).parts)
    ]
    bad = [
        f"{path.relative_to(REPOSITORY)}:{line}: pytest.mark.{mark} without an issue link"
        for path in sorted(tracked)
        for line, mark in unlinked(path.read_text())
    ]
    assert not bad, "\n".join(bad)
