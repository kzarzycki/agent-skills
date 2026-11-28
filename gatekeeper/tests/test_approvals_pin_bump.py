"""approvals.py: a PR that only bumps the engineering pack's pin to a released tag, byte for byte, is a pin target
(pin_target); any other change is not (#1218)."""

from __future__ import annotations

from typing import Any

import pytest
from approvals_harness import (
    HEAD,
    approvals,
    pull,
    writers,  # noqa: F401
)

TAG, TAGGED = "engineering-v0.99.0", "c" * 40
VENDORED = ".claude/skills/engineering-loop/scripts/gatekeeper.py"
SOURCE = "engineering/skills/engineering-loop/scripts/gatekeeper.py"
OLD = ".claude/skills/engineering-loop/scripts/old.py"  # vendored by the base's pin, gone from TAG
BLOB = "d" * 40
MID = "codex/terra-6.1/med"


def lock(ref: str = TAG, commit: str = TAGGED, repo: str = "kzarzycki/agent-skills") -> str:
    return f"""\
lockfile_version: '1'
dependencies:
- repo_url: {repo}
  name: engineering
  host: github.com
  resolved_commit: {commit}
  resolved_ref: {ref}
  virtual_path: engineering
  deployed_files:
  - .claude/skills/engineering-loop
  - {VENDORED}
"""


def manifest(ref: str = TAG) -> str:
    return f"dependencies:\n  apm:\n  - git: kzarzycki/agent-skills/engineering\n    ref: {ref}\n"


def change(path: str, sha: str = "e" * 40, status: str = "modified", **more: str) -> dict[str, str]:
    return {"filename": path, "status": status, "sha": sha, **more}


def bump(
    monkeypatch: pytest.MonkeyPatch,
    *,
    ref: str = TAG,
    blob: str = BLOB,
    extra: tuple[dict[str, str], ...] = (),
    pinned: str | None = None,
    head_lock: str | None = None,
    tags: dict[str, str] | None = None,
    placed: dict[str, tuple[str, str]] | None = None,
) -> tuple[str, ...]:
    """A pin bump to `ref` as GitHub would show it: the pin files, the vendored gatekeeper at `blob` and the `extra`
    changes, with apm.yml pinning `pinned` (`ref` when None) and the head's lock `head_lock` (lock(ref) when None);
    the pack's repository has each tag of `tags` (TAG alone when None) at TAGGED, its gatekeeper at BLOB, and the head's tree `placed` (the vendored gatekeeper at `blob` alone when None). The base's lock vendors VENDORED and OLD. Returns the changed paths, for the PR node."""
    changed = [change("apm.yml"), change("apm.lock.yaml"), change(VENDORED, blob), *extra]
    monkeypatch.setattr(approvals, "pr_changes", lambda _n: changed)
    base = lock("engineering-v0.1.0", "f" * 40).replace(
        f"  - {VENDORED}\n", f"  - {VENDORED}\n  - {OLD}\n"
    )

    def file_at(at: str, path: str, repo: str | None = None) -> str | None:
        if at != HEAD:
            return base if path == "apm.lock.yaml" else None
        return {"apm.lock.yaml": head_lock or lock(ref), "apm.yml": manifest(pinned or ref)}.get(
            path
        )

    monkeypatch.setattr(approvals, "file_at", file_at)
    monkeypatch.setattr(
        approvals,
        "tag_tree",
        lambda repo, tag: (
            (TAGGED, {SOURCE: ("100644", BLOB)})
            if repo == approvals.PACK_REPO and tag in (tags or [TAG])
            else None
        ),
    )
    monkeypatch.setattr(
        approvals,
        "tree",
        lambda sha: placed if placed is not None else {VENDORED: ("100644", blob)},
    )
    monkeypatch.setattr(
        approvals,
        "repo_tags",
        lambda repo: dict(tags or {TAG: TAGGED}) if repo == approvals.PACK_REPO else {},
    )
    paths = [found["filename"] for found in changed]
    paths += [found["previous_filename"] for found in changed if "previous_filename" in found]
    return tuple(paths)


def gate(
    family: str, files: tuple[str, ...], monkeypatch: pytest.MonkeyPatch, total: int = 0
) -> list[str]:
    """What holds a PR changing `files` (of `total`, when more): nothing when it is a pin target, else a line."""
    node = pull(files=files)
    if total:
        node["files"]["totalCount"] = total
    return [] if approvals.pin_target(node) else ["not a pin target"]


def refused(found: list[str]) -> str | None:
    return found[0] if found else None


def test_a_vendored_file_the_tag_dropped_may_go(monkeypatch: pytest.MonkeyPatch) -> None:
    files = bump(monkeypatch, extra=(change(OLD, status="removed"),))
    assert gate(MID, files, monkeypatch) == []


def test_an_extra_file_is_no_pin_target(monkeypatch: pytest.MonkeyPatch) -> None:
    files = bump(monkeypatch, extra=(change("src/app.py"),))
    assert refused(gate(MID, files, monkeypatch))


def test_a_pr_touching_other_files_reads_nothing_more(monkeypatch: pytest.MonkeyPatch) -> None:
    def unread(*_args: Any) -> None:
        raise AssertionError("no forge read for a PR that is no pin bump")

    for name in ("pr_changes", "file_at", "tag_tree", "tree", "repo_tags"):
        monkeypatch.setattr(approvals, name, unread)
    assert refused(gate(MID, ("apm.lock.yaml", "src/app.py"), monkeypatch))
    assert refused(gate(MID, (), monkeypatch))


@pytest.mark.parametrize(
    "extra",
    [
        # a skill of the project's own, not one the pack's lock vendors, though the tag holds no such file either
        change(".claude/skills/own-skill/SKILL.md", status="removed"),
        # a vendored file the tag still ships, removed
        change(VENDORED.replace("gatekeeper", "kept"), status="removed"),
        # a rename onto a vendored path whose old path the tag still ships
        change(VENDORED, BLOB, "renamed", previous_filename=OLD),
        # a pin file moved
        change("apm.yml", status="renamed", previous_filename="apm.yaml"),
    ],
    ids=["not-vendored", "removed-but-shipped", "renamed-from-shipped", "pin-renamed"],
)
def test_a_change_the_tag_does_not_make_is_no_pin_target(
    monkeypatch: pytest.MonkeyPatch, extra: dict[str, str]
) -> None:
    files = bump(monkeypatch, extra=(extra,))
    shipped = {
        SOURCE: ("100644", BLOB),
        "engineering/skills/engineering-loop/scripts/kept.py": ("100644", BLOB),
        "engineering/skills/engineering-loop/scripts/old.py": ("100644", BLOB),
    }
    base = approvals.file_at

    def file_at(at: str, path: str, repo: str | None = None) -> str | None:
        found = base(at, path, repo)
        kept = VENDORED.replace("gatekeeper", "kept")
        return (
            found.replace(f"  - {VENDORED}\n", f"  - {VENDORED}\n  - {kept}\n") if found else found
        )

    monkeypatch.setattr(approvals, "file_at", file_at)
    monkeypatch.setattr(approvals, "tag_tree", lambda _repo, _tag: (TAGGED, shipped))
    # the head holds every file the lock lists, so the diff's own change is what keeps main's rule
    kept = VENDORED.replace("gatekeeper", "kept")
    monkeypatch.setattr(
        approvals, "tree", lambda _sha: {VENDORED: ("100644", BLOB), kept: ("100644", BLOB)}
    )
    assert refused(gate(MID, files, monkeypatch))


@pytest.mark.parametrize("ref", ["9" * 40, "main", "engineering-v0.98.0"])
def test_a_target_that_is_not_a_released_tag_is_no_pin_target(
    monkeypatch: pytest.MonkeyPatch, ref: str
) -> None:
    # an untagged commit, a branch, and a tag-shaped name the pack's repository has no tag for
    assert refused(gate(MID, bump(monkeypatch, ref=ref), monkeypatch))


def test_a_tag_of_another_package_is_no_pin_target(monkeypatch: pytest.MonkeyPatch) -> None:
    files = bump(monkeypatch, ref="research-v1.0.0", tags={"research-v1.0.0": TAGGED})
    assert refused(gate(MID, files, monkeypatch))


def test_a_manifest_pinning_another_ref_is_no_pin_target(monkeypatch: pytest.MonkeyPatch) -> None:
    assert refused(gate(MID, bump(monkeypatch, pinned="engineering-v0.1.0"), monkeypatch))


def test_a_lock_of_another_repository_is_no_pin_target(monkeypatch: pytest.MonkeyPatch) -> None:
    files = bump(monkeypatch, head_lock=lock(repo="someone/agent-skills"))
    assert refused(gate(MID, files, monkeypatch))


def test_an_edited_vendored_file_is_no_pin_target(monkeypatch: pytest.MonkeyPatch) -> None:
    files = bump(monkeypatch, blob="0" * 40)
    assert refused(gate(MID, files, monkeypatch))


def test_a_file_list_past_what_rest_gives_is_no_pin_target(monkeypatch: pytest.MonkeyPatch) -> None:
    assert refused(gate(MID, bump(monkeypatch), monkeypatch, total=4000))


def test_the_lock_must_name_the_tags_own_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    files = bump(monkeypatch)
    monkeypatch.setattr(
        approvals, "tag_tree", lambda _repo, _tag: ("1" * 40, {SOURCE: ("100644", BLOB)})
    )
    assert refused(gate(MID, files, monkeypatch))


OWN = ".claude/skills/own-skill/SKILL.md"


def test_a_removal_only_the_head_lock_lists_is_no_pin_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # the head lock is the PR author's: a path only it lists as the pack's is not one the PR may delete
    listed = lock().replace(f"  - {VENDORED}\n", f"  - {VENDORED}\n  - {OWN}\n")
    files = bump(monkeypatch, head_lock=listed, extra=(change(OWN, status="removed"),))
    assert refused(gate(MID, files, monkeypatch))
    renamed = change(VENDORED, BLOB, status="renamed", previous_filename=OWN)
    files = bump(monkeypatch, head_lock=listed, extra=(renamed,))
    assert refused(gate(MID, files, monkeypatch))


@pytest.mark.parametrize(
    ("head_lock", "pinned", "base_lock"),
    [
        ("- a\n- b\n", None, None),
        ("just a string\n", None, None),
        (None, "- a\n", None),
        (None, "dependencies: [x]\n", None),
        (None, None, "- a\n"),
    ],
    ids=["lock-list", "lock-string", "manifest-list", "deps-list", "base-lock-list"],
)
def test_a_pin_file_that_is_not_a_mapping_is_no_pin_target(
    monkeypatch: pytest.MonkeyPatch,
    head_lock: str | None,
    pinned: str | None,
    base_lock: str | None,
) -> None:
    files = bump(monkeypatch, head_lock=head_lock)
    real = approvals.file_at

    def file_at(at: str, path: str, repo: str | None = None) -> str | None:
        if repo is None and path == "apm.yml" and pinned and at == HEAD:
            return pinned
        if repo is None and path == "apm.lock.yaml" and base_lock and at != HEAD:
            return base_lock
        return real(at, path, repo)

    monkeypatch.setattr(approvals, "file_at", file_at)
    assert refused(gate(MID, files, monkeypatch))


KEPT = VENDORED.replace("gatekeeper", "kept")
KEPT_SOURCE = SOURCE.replace("gatekeeper", "kept")


def whole_lock(
    monkeypatch: pytest.MonkeyPatch, *, head: str | None, tag: bool = True, listed: bool = True
) -> tuple[str, ...]:
    """A bump whose diff is the gatekeeper alone, the lock listing KEPT (when `listed`), a file the diff leaves out:
    the head's tree holds it at `head` (absent when None), the tag ships it (when `tag`) at BLOB."""
    text = lock().replace(
        f"  - {VENDORED}\n", f"  - {VENDORED}\n" + (f"  - {KEPT}\n" if listed else "")
    )
    placed = {VENDORED: ("100644", BLOB)} | ({KEPT: ("100644", head)} if head else {})
    files = bump(monkeypatch, head_lock=text, placed=placed)
    shipped = {SOURCE: ("100644", BLOB)} | ({KEPT_SOURCE: ("100644", BLOB)} if tag else {})
    monkeypatch.setattr(approvals, "tag_tree", lambda _repo, _tag: (TAGGED, shipped))
    return files


def test_a_deployed_file_outside_the_diff_that_is_the_tags_is_a_pin_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert gate(MID, whole_lock(monkeypatch, head=BLOB), monkeypatch) == []


def test_a_deployed_file_outside_the_diff_that_differs_from_the_tag_is_no_pin_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # a half-applied sync: the file stayed at the old tag's bytes, so it is not in the diff
    assert refused(gate(MID, whole_lock(monkeypatch, head="1" * 40), monkeypatch))


def test_a_deployed_file_the_head_tree_lacks_is_no_pin_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert refused(gate(MID, whole_lock(monkeypatch, head=None), monkeypatch))


def test_a_file_the_tag_adds_that_the_head_lacks_is_no_pin_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # the tag ships KEPT; the lock does not list it and the head tree does not hold it
    assert refused(gate(MID, whole_lock(monkeypatch, head=None, listed=False), monkeypatch))


def test_a_head_tree_that_cannot_be_read_is_no_pin_target(monkeypatch: pytest.MonkeyPatch) -> None:
    files = bump(monkeypatch)
    monkeypatch.setattr(approvals, "tree", lambda _sha: None)
    assert refused(gate(MID, files, monkeypatch))


def test_a_lock_entry_that_names_no_file_anywhere_is_no_pin_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # a hand-edited lock lists a file neither the head tree nor the tag has
    gone = VENDORED.replace("gatekeeper", "gone")
    text = lock().replace(f"  - {VENDORED}\n", f"  - {VENDORED}\n  - {gone}\n")
    files = bump(monkeypatch, head_lock=text)
    assert refused(gate(MID, files, monkeypatch))


def test_a_file_the_tag_ships_that_the_lock_does_not_list_is_no_pin_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # a lock that lists files one by one, omitting KEPT, which the tag ships and the head tree holds
    text = lock().replace("  - .claude/skills/engineering-loop\n", "")
    placed = {VENDORED: ("100644", BLOB), KEPT: ("100644", BLOB)}
    files = bump(monkeypatch, head_lock=text, placed=placed)
    shipped = {SOURCE: ("100644", BLOB), KEPT_SOURCE: ("100644", BLOB)}
    monkeypatch.setattr(approvals, "tag_tree", lambda _repo, _tag: (TAGGED, shipped))
    assert refused(gate(MID, files, monkeypatch))


def test_a_skill_the_tag_adds_that_the_lock_does_not_deploy_is_no_pin_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    files = bump(monkeypatch)
    shipped = {SOURCE: ("100644", BLOB), "engineering/skills/brand-new/SKILL.md": ("100644", BLOB)}
    monkeypatch.setattr(approvals, "tag_tree", lambda _repo, _tag: (TAGGED, shipped))
    assert refused(gate(MID, files, monkeypatch))


def test_a_stale_file_the_tag_dropped_is_no_pin_target(monkeypatch: pytest.MonkeyPatch) -> None:
    # the sync left a file the tag no longer ships under the lock's skill directory, outside the diff
    stale = ".claude/skills/engineering-loop/scripts/old.py"
    placed = {VENDORED: ("100644", BLOB), stale: ("100644", "a" * 40)}
    files = bump(monkeypatch, placed=placed)
    assert refused(gate(MID, files, monkeypatch))
