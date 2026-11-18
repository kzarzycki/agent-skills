"""approvals.py: a cloud land is the default, and needs no `land` section on a merge-queue base (#1356)."""

from __future__ import annotations

import pytest
from approvals_harness import approvals

NO_LAND = "# Loop facts\n\n## Settings\n\n```yaml\npractice:\n  spec: to-spec\n```\n"


def test_a_cloud_land_on_a_merge_queue_base_needs_no_land_section(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`where` unset is `both` and GitHub's queue merges and signs, so a cloud session needs no section nor key."""
    monkeypatch.setenv(approvals.CLOUD, "true")
    with approvals.placed(NO_LAND, True):
        assert approvals.SIGNING == []
    with (
        pytest.raises(approvals.Refused, match="needs loop.md's `land` section"),
        approvals.placed(NO_LAND, False),
    ):
        pass


def test_land_where_host_still_refuses_a_cloud_session_on_a_merge_queue_base(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(approvals.CLOUD, "true")
    loop = NO_LAND.replace("practice:", "land:\n  where: host\npractice:")
    with (
        pytest.raises(
            approvals.Refused, match="`land.where` is `host`, so land does not run in a cloud session"
        ),
        approvals.placed(loop, True),
    ):
        pass
