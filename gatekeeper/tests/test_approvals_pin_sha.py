"""approvals.py: a pin bump that pins the engineering pack by a commit SHA equal to a release tag's commit is a pin
target, as a pin by the tag is; a SHA no release tag points at is none (#1296)."""

from __future__ import annotations

import subprocess
from typing import Any

import pytest
from approvals_harness import approvals, writers  # noqa: F401
from test_approvals_pin_bump import (
    MID,
    TAG,
    TAGGED,
    bump,
    change,
    gate,
    lock,
    refused,
)

UNTAGGED = "b" * 40  # letters: YAML reads an all-digit SHA as a number


def test_an_uppercase_sha_pin_at_a_tags_commit_is_a_pin_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert gate(MID, bump(monkeypatch, ref=TAGGED.upper()), monkeypatch) == []


def test_a_sha_no_release_tag_points_at_is_no_pin_target(monkeypatch: pytest.MonkeyPatch) -> None:
    files = bump(monkeypatch, ref=UNTAGGED, head_lock=lock(UNTAGGED, UNTAGGED))
    assert refused(gate(MID, files, monkeypatch))


def test_a_sha_ref_other_than_the_tags_commit_is_no_pin_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # the lock's resolved_commit is the tag's, but the ref it pins is a SHA no release tag points at
    files = bump(monkeypatch, ref=UNTAGGED, head_lock=lock(UNTAGGED, TAGGED))
    assert refused(gate(MID, files, monkeypatch))


def test_a_sha_only_another_packages_tag_points_at_is_no_pin_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    files = bump(monkeypatch, ref=TAGGED, tags={"research-v1.0.0": TAGGED})
    assert refused(gate(MID, files, monkeypatch))


def test_two_tags_on_one_commit_are_one_pin_target(monkeypatch: pytest.MonkeyPatch) -> None:
    tags = {
        "engineering-v0.100.0": TAGGED,
        "engineering-v0.99.0": TAGGED,
        "research-v9.0.0": TAGGED,
    }
    assert gate(MID, bump(monkeypatch, ref=TAGGED, tags=tags), monkeypatch) == []


def test_a_sha_pin_with_an_extra_file_is_no_pin_target(monkeypatch: pytest.MonkeyPatch) -> None:
    files = bump(monkeypatch, ref=TAGGED, extra=(change("src/app.py"),))
    assert refused(gate(MID, files, monkeypatch))


def test_a_sha_pin_with_an_edited_vendored_file_is_no_pin_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert refused(gate(MID, bump(monkeypatch, ref=TAGGED, blob="0" * 40), monkeypatch))


@pytest.mark.parametrize("pinned", [TAG, UNTAGGED], ids=["the-tag", "another-sha"])
def test_a_manifest_pinning_another_ref_than_the_locks_sha_is_no_pin_target(
    monkeypatch: pytest.MonkeyPatch, pinned: str
) -> None:
    assert refused(gate(MID, bump(monkeypatch, ref=TAGGED, pinned=pinned), monkeypatch))


def test_a_tag_list_that_cannot_be_read_is_no_pin_target(monkeypatch: pytest.MonkeyPatch) -> None:
    files = bump(monkeypatch, ref=TAGGED)

    def failing(_repo: str) -> Any:
        raise subprocess.CalledProcessError(1, ["gh"], stderr="HTTP 502")

    monkeypatch.setattr(approvals, "repo_tags", failing)
    assert refused(gate(MID, files, monkeypatch))


def test_a_tag_pin_reads_no_tag_list(monkeypatch: pytest.MonkeyPatch) -> None:
    files = bump(monkeypatch)

    def unread(_repo: str) -> Any:
        raise AssertionError("a pin by tag needs no tag list")

    monkeypatch.setattr(approvals, "repo_tags", unread)
    assert gate(MID, files, monkeypatch) == []
