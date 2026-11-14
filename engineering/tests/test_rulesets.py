"""scripts/rulesets.py: `check` reports each way a live ruleset differs from the one committed on the default branch,
one line each, and prints nothing when none does."""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "engineering-loop" / "scripts"
sys.path.insert(
    0, str(SCRIPTS)
)  # as when run: rulesets.py reads Refused from approvals.py beside it
SPEC = importlib.util.spec_from_file_location("rulesets", SCRIPTS / "rulesets.py")
assert SPEC and SPEC.loader
rulesets = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rulesets)

REPO = "o/r"
MAIN = {
    "name": "main",
    "target": "branch",
    "enforcement": "active",
    "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
    "rules": [
        {"type": "deletion"},
        {"type": "non_fast_forward"},
        {
            "type": "required_status_checks",
            "parameters": {"required_status_checks": [{"context": "check"}]},
        },
    ],
    "bypass_actors": [],
}
# what the API adds around the fields that count
LIVE_EXTRA = {"id": 7, "source_type": "Repository", "created_at": "x", "_links": {}}


class FakeGh:
    """The rulesets API of one repo: `committed` is what its default branch holds, `live` what GitHub enforces."""

    def __init__(self, committed: list[dict] | None, live: list[dict]):
        self.committed, self.live = committed, live

    def __call__(self, *args: str) -> str:
        path = args[-1]
        if path == f"repos/{REPO}/contents/.github/rulesets":
            if self.committed is None:
                raise subprocess.CalledProcessError(1, "gh", stderr="gh: Not Found (HTTP 404)")
            return json.dumps(
                [
                    {"name": f"{r['name']}.json", "path": f".github/rulesets/{r['name']}.json"}
                    for r in self.committed
                ]
            )
        if "/contents/.github/rulesets/" in path:
            name = path.rsplit("/", 1)[1].removesuffix(".json")
            return json.dumps(next(r for r in self.committed or [] if r["name"] == name))
        if path.startswith(f"repos/{REPO}/rulesets?"):
            return json.dumps([{"id": i} for i, _ in enumerate(self.live)])
        if path.startswith(f"repos/{REPO}/rulesets/"):
            return json.dumps({**LIVE_EXTRA, **self.live[int(path.rsplit("/", 1)[1])]})
        raise AssertionError(args)


def run(monkeypatch, capsys, committed, live) -> tuple[int, list[str]]:
    monkeypatch.setattr(rulesets, "gh", FakeGh(committed, live))
    code = rulesets.check([REPO])
    return code, capsys.readouterr().out.splitlines()


def changed(**edits) -> dict:
    return {**copy.deepcopy(MAIN), **edits}


def test_unchanged_prints_nothing(monkeypatch, capsys):
    assert run(monkeypatch, capsys, [MAIN], [MAIN]) == (0, [])


def test_rule_order_and_extra_api_fields_do_not_count(monkeypatch, capsys):
    reordered = changed(rules=list(reversed(MAIN["rules"])))
    assert run(monkeypatch, capsys, [MAIN], [reordered]) == (0, [])


def test_deleted_ruleset(monkeypatch, capsys):
    code, lines = run(monkeypatch, capsys, [MAIN], [])
    assert (code, lines) == (1, [f"{REPO}: ruleset main is missing"])


@pytest.mark.parametrize("enforcement", ["disabled", "evaluate"])
def test_enforcement_not_active(monkeypatch, capsys, enforcement):
    code, lines = run(monkeypatch, capsys, [MAIN], [changed(enforcement=enforcement)])
    assert code == 1
    assert lines == [f"{REPO}: ruleset main: enforcement is {enforcement}, expected active"]


def test_narrowed_include(monkeypatch, capsys):
    narrowed = changed(conditions={"ref_name": {"include": ["refs/heads/other"], "exclude": []}})
    code, lines = run(monkeypatch, capsys, [MAIN], [narrowed])
    assert code == 1
    assert len(lines) == 1 and "conditions changed" in lines[0] and "refs/heads/other" in lines[0]


def test_removed_rule(monkeypatch, capsys):
    fewer = changed(rules=[r for r in MAIN["rules"] if r["type"] != "non_fast_forward"])
    code, lines = run(monkeypatch, capsys, [MAIN], [fewer])
    assert (code, lines) == (1, [f"{REPO}: ruleset main: rule non_fast_forward removed"])


def test_changed_rule_parameters(monkeypatch, capsys):
    rules = copy.deepcopy(MAIN["rules"])
    rules[2]["parameters"]["required_status_checks"] = []
    code, lines = run(monkeypatch, capsys, [MAIN], [changed(rules=rules)])
    assert code == 1
    assert len(lines) == 1 and "rule required_status_checks parameters changed" in lines[0]


def test_added_bypass_actor(monkeypatch, capsys):
    actor = {"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"}
    code, lines = run(monkeypatch, capsys, [MAIN], [changed(bypass_actors=[actor])])
    assert code == 1
    assert len(lines) == 1 and lines[0].startswith(f"{REPO}: ruleset main: bypass actor added")


def test_each_difference_is_its_own_line(monkeypatch, capsys):
    actor = {"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"}
    broken = changed(enforcement="disabled", rules=MAIN["rules"][:1], bypass_actors=[actor])
    code, lines = run(monkeypatch, capsys, [MAIN], [broken])
    assert code == 1 and len(lines) == 4


def test_repo_without_committed_rulesets_is_skipped(monkeypatch, capsys):
    code, lines = run(monkeypatch, capsys, None, [])
    assert code == 0
    assert lines == [f"{REPO}: no .github/rulesets/ on its default branch, skipped"]


def test_snapshot_keeps_only_deciding_fields(monkeypatch, tmp_path):
    monkeypatch.setattr(rulesets, "gh", FakeGh(None, [{**MAIN, "name": "tags immutable"}]))
    monkeypatch.setattr(rulesets, "toplevel", lambda: tmp_path)
    assert rulesets.snapshot(REPO) == 0
    written = json.loads((tmp_path / ".github/rulesets/tags-immutable.json").read_text())
    assert (
        set(written) == {"name", "target", "enforcement", "conditions", "rules", "bypass_actors"}
        and written["name"] == "tags immutable"
    )
