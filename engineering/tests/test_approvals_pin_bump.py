"""approvals.py: a PR that only bumps the engineering pack's pin to a released tag has its verifier pass's tier judged by
the tag's rule, read from the tag; anything else keeps main's rule (#1218)."""

from __future__ import annotations

from typing import Any

import pytest
from approvals_harness import (
    HEAD,
    add,
    added,  # noqa: F401
    approvals,
    approved,
    assigned,  # noqa: F401
    attached,  # noqa: F401
    board_risks,  # noqa: F401
    graphql_answers,  # noqa: F401
    hub,  # noqa: F401
    loop_md,
    others_open,  # noqa: F401
    pull,
    pushed,  # noqa: F401
    refs,  # noqa: F401
    required,  # noqa: F401
    verdict_on,
    writers,  # noqa: F401
)

TAG, TAGGED = "engineering-v0.99.0", "c" * 40
VENDORED = ".claude/skills/engineering-loop/scripts/gatekeeper.py"
SOURCE = "engineering/skills/engineering-loop/scripts/gatekeeper.py"
BLOB = "d" * 40
# a tag whose rule counts a same-family pass as a lower tier, as releases before #1115 did
STRICT = """\
import re
LOWER_TIER = re.compile(r"(mid|small|same-family)")


def lower(verdicts: list[tuple[str, int, dict[str, str]]] | str) -> str | None:
    found = LOWER_TIER.search(verdicts[-1][2]["Family"])
    return found[1] if found else None
"""
# a tag whose rule names no tier at all
LENIENT = "def lower(verdicts):\n    return None\n"


def lock(ref: str = TAG, commit: str = TAGGED) -> str:
    return f"""\
lockfile_version: '1'
dependencies:
- repo_url: kzarzycki/agent-skills
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


def bump(
    monkeypatch: pytest.MonkeyPatch,
    *,
    rule: str = LENIENT,
    ref: str = TAG,
    blob: str = BLOB,
    extra: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """A pin bump to `ref` as GitHub would show it: the pin files, the vendored gatekeeper at `blob` and `extra`
    files; the pack's repository has TAG at TAGGED, its gatekeeper at BLOB with `rule` as its text."""
    changed = ["apm.yml", "apm.lock.yaml", VENDORED, *extra]
    sha = {VENDORED: blob}
    monkeypatch.setattr(
        approvals,
        "pr_changes",
        lambda _n: [
            {"filename": path, "status": "modified", "sha": sha.get(path, "e" * 40)}
            for path in changed
        ],
    )

    def file_at(at: str, path: str, repo: str | None = None) -> str | None:
        if repo == approvals.PACK_REPO:
            assert at == TAG, "the rule is read from the tag"
            return rule if path == SOURCE else None
        return (
            {"apm.lock.yaml": lock(ref), "apm.yml": manifest(ref)}.get(path)
            if at == HEAD
            else lock("engineering-v0.1.0", "f" * 40)
        )

    monkeypatch.setattr(approvals, "file_at", file_at)
    monkeypatch.setattr(
        approvals,
        "tag_tree",
        lambda repo, tag: (
            (TAGGED, {SOURCE: ("100644", BLOB)})
            if (repo, tag) == (approvals.PACK_REPO, TAG)
            else None
        ),
    )
    return tuple(changed)


def gate(family: str, files: tuple[str, ...], monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """check merge's proofs on a high-risk PR whose one satisfied verdict came from `family`."""
    monkeypatch.setattr(approvals, "writer", lambda _login: False)
    judged = add(loop_md("spec:\n  auto: true\n"), "risk", "verifier: true\n")
    heading = f"Verifier ({family}), pass 1"
    review: dict[str, Any] = verdict_on(HEAD, "0 blocker, 0 major, 0 minor", heading=heading) | {
        "body": f"{heading} on {HEAD[:7]}.\n\nVERDICT: 0 blocker, 0 major, 0 minor\nSATISFIED: yes\nRisk: high — the pin\n"
    }
    return approvals.proofs(
        "merge",
        pull(reviews=[review], labels=("approved:merge",), files=files),
        [approved(1, "kind:bug")],
        judged,
    )


def refused(found: list[str]) -> str | None:
    lines = [line for line in found if "lower tier" in line]
    return lines[0] if lines else None


def test_a_pin_only_bump_is_judged_by_the_tags_rule_both_ways(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # main refuses a mid-tier pass on a high-risk change; the tag's rule names no tier, so it lands
    assert refused(gate("codex/terra-6.1/med mid", ("src/app.py",), monkeypatch))
    assert gate("codex/terra-6.1/med mid", bump(monkeypatch, rule=LENIENT), monkeypatch) == []
    # main lands a same-family pass; the tag's rule counts it as a lower tier, so it is refused
    assert gate("claude, same-family", ("src/app.py",), monkeypatch) == []
    found = refused(gate("claude, same-family", bump(monkeypatch, rule=STRICT), monkeypatch))
    assert found and "lower tier (same-family)" in found


def test_an_extra_file_keeps_mains_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    files = bump(monkeypatch, rule=LENIENT, extra=("src/app.py",))
    assert refused(gate("codex/terra-6.1/med mid", files, monkeypatch))


def test_an_extra_dotted_skill_file_the_lock_does_not_vendor_keeps_mains_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    files = bump(monkeypatch, rule=LENIENT, extra=(".claude/skills/own-skill/SKILL.md",))
    assert refused(gate("codex/terra-6.1/med mid", files, monkeypatch))


@pytest.mark.parametrize("ref", ["9" * 40, "main", "engineering-v0.98.0"])
def test_a_target_that_is_not_a_released_tag_keeps_mains_rule(
    monkeypatch: pytest.MonkeyPatch, ref: str
) -> None:
    # an untagged commit, a branch, and a tag-shaped name the pack's repository has no tag for
    assert refused(
        gate("codex/terra-6.1/med mid", bump(monkeypatch, rule=LENIENT, ref=ref), monkeypatch)
    )


def test_an_edited_vendored_file_keeps_mains_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    files = bump(monkeypatch, rule=LENIENT, blob="0" * 40)
    assert refused(gate("codex/terra-6.1/med mid", files, monkeypatch))


def test_a_tag_without_the_rule_keeps_mains_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    # an old tag's file shape: no lower() to read, so main's rule judges
    files = bump(monkeypatch, rule="def other():\n    return None\n")
    assert refused(gate("codex/terra-6.1/med mid", files, monkeypatch))


def test_the_lock_must_name_the_tags_own_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    files = bump(monkeypatch, rule=LENIENT)
    monkeypatch.setattr(
        approvals, "tag_tree", lambda _repo, _tag: ("1" * 40, {SOURCE: ("100644", BLOB)})
    )
    assert refused(gate("codex/terra-6.1/med mid", files, monkeypatch))


def test_a_rule_read_from_a_real_release_shape_is_rebuilt() -> None:
    # the module-level names lower() reads come with it, in the file's order, and annotations stay unevaluated
    source = "import re\nA = 'x'\nB = re.compile(A)\n\ndef lower(verdicts: list[int] | str) -> str | None:\n    return B.pattern\n"
    rule = approvals.rule_in(source)
    assert rule is not None and rule([]) == "x"
    assert approvals.rule_in("def lower(a, b):\n    return None\n") is None
    assert approvals.rule_in("not python (") is None
