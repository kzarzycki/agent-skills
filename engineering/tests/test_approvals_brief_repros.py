"""A pass's brief carries the previous findings' repro commands, read from each finding's collapsed `<details>` block on
the PR (#1595), so no report file is handed between passes: a verifier on any host reruns them."""

from __future__ import annotations

from pathlib import Path

import pytest
from approvals_harness import LOOP, approvals, pull, verdict_on

FINDING = (
    "**Verifier (codex), pass 1 · F1** (major): a gap\n\nit fails\n\n"
    "<details>\n<summary>Repro</summary>\n\n```sh\nuv run pytest tests/test_x.py -k gap\n```\n\n"
    "```text\n$ uv run pytest tests/test_x.py -k gap\nFAILED\nexit 1\n```\n\n</details>"
)


def test_the_brief_prints_a_findings_repro_commands_not_its_log(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    found = pull(
        body="Closes #12.\n",
        reviews=(verdict_on("c" * 40, heading="Verifier (codex), pass 1"),),
    )
    found["reviewThreads"] = {
        "nodes": [{"isResolved": False, "comments": {"nodes": [{"body": FINDING}]}}]
    }
    monkeypatch.setattr(approvals, "pull_request", lambda _n: found)
    monkeypatch.setattr(approvals, "merge_base", lambda base, head: "b" * 40)
    monkeypatch.setattr(approvals, "project", lambda: (None, LOOP))
    assert approvals.main(["brief", "7"]) == 0
    out = capsys.readouterr().out
    assert "     Repro 1:\n       uv run pytest tests/test_x.py -k gap\n" in out
    assert "FAILED" not in out and "<details>" not in out
    assert "1. **Verifier (codex), pass 1 · F1** (major): a gap" in out
