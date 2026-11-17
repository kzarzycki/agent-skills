"""approvals.py: loop.md's `land.where: claude-cloud` is the new name of `cloud`, which stays accepted (#1278)."""

from __future__ import annotations

import pytest
from approvals_harness import (
    added,  # noqa: F401
    approvals,
    assigned,  # noqa: F401
    attached,  # noqa: F401
    board_risks,  # noqa: F401
    graphql_answers,  # noqa: F401
    hub,  # noqa: F401
    others_open,  # noqa: F401
    pushed,  # noqa: F401
    refs,  # noqa: F401
    required,  # noqa: F401
)


def loop_md(settings: str) -> str:
    return f"# Loop facts\n\n## Settings\n\n```yaml\n{settings}```\n"


def test_claude_cloud_is_cloud_and_other_names_are_still_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    land = "land:\n  signed_squash_to: main\n  allowed_signers: s\n  where: {}\n"
    for name in ("cloud", "claude-cloud"):
        assert approvals.settings(loop_md(land.format(name)))["land"]["where"] == name
    with pytest.raises(
        approvals.Refused, match="must be one of host, cloud, both, not 'everywhere'"
    ):
        approvals.settings(loop_md(land.format("everywhere")))
    # on a host, either name is refused alike; the VM's marker would let both through
    monkeypatch.delenv(approvals.CLOUD, raising=False)
    for name in ("cloud", "claude-cloud"):
        with (
            pytest.raises(
                approvals.Refused, match="`land.where` is `cloud`, so land does not run in a host"
            ),
            approvals.placed(loop_md(land.format(name))),
        ):
            pass
