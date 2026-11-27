"""scripts/loop.py brief lists a spec's `Host:` Before merge lines under their own heading, so a cloud verifier doesn't
stop on a check only a host can run (#962). Stands in for the gatekeeper's ports as test_loop_brief_2870 does."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_loop import loop
from test_loop_brief_2870 import clone, stand_in  # noqa: F401  (clone is a fixture)

SPEC = """## Acceptance

### Before merge

- The library installs mise through npm. Check: `tests/test_cloud_setup.py::test_mise_comes_from_npm`.
- Host: `mise run lint` exits 0 on a host with the full toolchain.
- Manual: on a real cloud worker, the setup log shows every step exit 0.
* Host: the nightly's run of the whole suite is green.

### After merge

- Host: after merge only, `claude-cloud-run -- 'mise install'` exits 0.
"""


def test_brief_names_host_only_lines(
    clone: tuple[Path, str, str],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, base, head = clone
    stand_in(monkeypatch, base, head, "Closes #962\n")
    pull = loop.gatekeeper.pull_request(7)
    pull["closingIssuesReferences"]["nodes"][0]["body"] = SPEC
    assert loop.brief(7, None, []) == 0
    out = capsys.readouterr().out
    assert "- Host-only lines" in out
    assert "  - Host: `mise run lint` exits 0 on a host with the full toolchain." in out
    assert "  - Host: the nightly's run of the whole suite is green." in out
    # no other line: not a Manual or a plain check, and not an After merge line, which runs after the merge
    assert "Manual: on a real cloud worker" not in out
    assert "test_mise_comes_from_npm" not in out
    assert "after merge only" not in out


def test_a_spec_with_no_host_line_adds_no_heading(
    clone: tuple[Path, str, str],  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, base, head = clone
    stand_in(monkeypatch, base, head, "Closes #962\n")
    pull = loop.gatekeeper.pull_request(7)
    pull["closingIssuesReferences"]["nodes"][0]["body"] = "## Acceptance\n\n- Manual: look.\n"
    assert loop.brief(7, None, []) == 0
    assert "Host-only" not in capsys.readouterr().out
