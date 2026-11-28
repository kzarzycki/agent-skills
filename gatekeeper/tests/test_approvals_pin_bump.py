"""approvals.py: pin_target names the released tag a PR that only bumps the engineering pack's pin pins, from the pin files
and the vendored skill files byte for byte; any other PR names none (#1218)."""

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
        if repo == approvals.PACK_REPO:
            raise AssertionError("pin_target reads the tag's tree, never a file of it")
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


def target(files: tuple[str, ...], monkeypatch: pytest.MonkeyPatch, total: int = 0) -> str | None:
    """The released tag pin_target reads from a PR changing `files` (of `total`, when more), None for no pin bump."""
    monkeypatch.setattr(approvals, "writer", lambda _login: False)
    node = pull(labels=("approved:merge",), files=files)
    if total:
        node["files"]["totalCount"] = total
    return approvals.pin_target(node)


def test_a_pin_only_bump_names_its_tag_and_another_pr_names_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert target(("src/app.py",), monkeypatch) is None
    assert target(bump(monkeypatch), monkeypatch) == TAG


def test_a_vendored_file_the_tag_dropped_may_go(monkeypatch: pytest.MonkeyPatch) -> None:
    files = bump(monkeypatch, extra=(change(OLD, status="removed"),))
    assert target(files, monkeypatch) == TAG


def test_an_extra_file_keeps_mains_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    files = bump(monkeypatch, extra=(change("src/app.py"),))
    assert target(files, monkeypatch) is None


def test_a_pr_touching_other_files_reads_nothing_more(monkeypatch: pytest.MonkeyPatch) -> None:
    def unread(*_args: Any) -> None:
        raise AssertionError("no forge read for a PR that is no pin bump")

    for name in ("pr_changes", "file_at", "tag_tree", "tree", "repo_tags"):
        monkeypatch.setattr(approvals, name, unread)
    assert target(("apm.lock.yaml", "src/app.py"), monkeypatch) is None
    assert target((), monkeypatch) is None


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
def test_a_change_the_tag_does_not_make_keeps_mains_rule(
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
    assert target(files, monkeypatch) is None


@pytest.mark.parametrize("ref", ["9" * 40, "main", "engineering-v0.98.0"])
def test_a_target_that_is_not_a_released_tag_keeps_mains_rule(
    monkeypatch: pytest.MonkeyPatch, ref: str
) -> None:
    # an untagged commit, a branch, and a tag-shaped name the pack's repository has no tag for
    assert target(bump(monkeypatch, ref=ref), monkeypatch) is None


def test_a_tag_of_another_package_keeps_mains_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    files = bump(monkeypatch, ref="research-v1.0.0", tags={"research-v1.0.0": TAGGED})
    assert target(files, monkeypatch) is None


def test_a_manifest_pinning_another_ref_keeps_mains_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    assert target(bump(monkeypatch, pinned="engineering-v0.1.0"), monkeypatch) is None


def test_a_lock_of_another_repository_keeps_mains_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    files = bump(monkeypatch, head_lock=lock(repo="someone/agent-skills"))
    assert target(files, monkeypatch) is None


def test_an_edited_vendored_file_keeps_mains_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    files = bump(monkeypatch, blob="0" * 40)
    assert target(files, monkeypatch) is None


def test_a_file_list_past_what_rest_gives_keeps_mains_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    assert target(bump(monkeypatch), monkeypatch, total=4000) is None


def test_the_lock_must_name_the_tags_own_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    files = bump(monkeypatch)
    monkeypatch.setattr(
        approvals, "tag_tree", lambda _repo, _tag: ("1" * 40, {SOURCE: ("100644", BLOB)})
    )
    assert target(files, monkeypatch) is None


OWN = ".claude/skills/own-skill/SKILL.md"


def test_a_removal_only_the_head_lock_lists_keeps_mains_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # the head lock is the PR author's: a path only it lists as the pack's is not one the PR may delete
    listed = lock().replace(f"  - {VENDORED}\n", f"  - {VENDORED}\n  - {OWN}\n")
    files = bump(monkeypatch, head_lock=listed, extra=(change(OWN, status="removed"),))
    assert target(files, monkeypatch) is None
    renamed = change(VENDORED, BLOB, status="renamed", previous_filename=OWN)
    files = bump(monkeypatch, head_lock=listed, extra=(renamed,))
    assert target(files, monkeypatch) is None


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
def test_a_pin_file_that_is_not_a_mapping_keeps_mains_rule(
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
    assert target(files, monkeypatch) is None


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


def test_a_deployed_file_outside_the_diff_that_is_the_tags_keeps_the_pin_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert target(whole_lock(monkeypatch, head=BLOB), monkeypatch) == TAG


def test_a_deployed_file_outside_the_diff_that_differs_from_the_tag_keeps_mains_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # a half-applied sync: the file stayed at the old tag's bytes, so it is not in the diff
    assert target(whole_lock(monkeypatch, head="1" * 40), monkeypatch) is None


def test_a_deployed_file_the_head_tree_lacks_keeps_mains_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert target(whole_lock(monkeypatch, head=None), monkeypatch) is None


def test_a_file_the_tag_adds_that_the_head_lacks_keeps_mains_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # the tag ships KEPT; the lock does not list it and the head tree does not hold it
    assert target(whole_lock(monkeypatch, head=None, listed=False), monkeypatch) is None


def test_a_head_tree_that_cannot_be_read_keeps_mains_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    files = bump(monkeypatch)
    monkeypatch.setattr(approvals, "tree", lambda _sha: None)
    assert target(files, monkeypatch) is None


def test_a_lock_entry_that_names_no_file_anywhere_keeps_mains_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # a hand-edited lock lists a file neither the head tree nor the tag has
    gone = VENDORED.replace("gatekeeper", "gone")
    text = lock().replace(f"  - {VENDORED}\n", f"  - {VENDORED}\n  - {gone}\n")
    files = bump(monkeypatch, head_lock=text)
    assert target(files, monkeypatch) is None


def test_a_file_the_tag_ships_that_the_lock_does_not_list_keeps_mains_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # a lock that lists files one by one, omitting KEPT, which the tag ships and the head tree holds
    text = lock().replace("  - .claude/skills/engineering-loop\n", "")
    placed = {VENDORED: ("100644", BLOB), KEPT: ("100644", BLOB)}
    files = bump(monkeypatch, head_lock=text, placed=placed)
    shipped = {SOURCE: ("100644", BLOB), KEPT_SOURCE: ("100644", BLOB)}
    monkeypatch.setattr(approvals, "tag_tree", lambda _repo, _tag: (TAGGED, shipped))
    assert target(files, monkeypatch) is None


def test_a_skill_the_tag_adds_that_the_lock_does_not_deploy_keeps_mains_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    files = bump(monkeypatch)
    shipped = {SOURCE: ("100644", BLOB), "engineering/skills/brand-new/SKILL.md": ("100644", BLOB)}
    monkeypatch.setattr(approvals, "tag_tree", lambda _repo, _tag: (TAGGED, shipped))
    assert target(files, monkeypatch) is None


def test_a_stale_file_the_tag_dropped_keeps_mains_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    # the sync left a file the tag no longer ships under the lock's skill directory, outside the diff
    stale = ".claude/skills/engineering-loop/scripts/old.py"
    placed = {VENDORED: ("100644", BLOB), stale: ("100644", "a" * 40)}
    files = bump(monkeypatch, placed=placed)
    assert target(files, monkeypatch) is None
